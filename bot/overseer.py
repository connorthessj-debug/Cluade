"""
SMC Dual-Agent Trading Bot — Overseer Agent (MASTER CONTROL)

Acts as a hedge fund risk manager and market regime classifier.
Controls ALL trading decisions. When in doubt → DO NOT TRADE.

Each cycle:
1. Determine market condition (Trending / Ranging / High Vol / Low Vol)
2. Decide which agent to activate (Scalping / Swing / None)
3. Enforce FTMO rules strictly
4. Evaluate proposed trades against SMC criteria
5. Output decision with full reasoning
"""

import logging
from datetime import datetime, timezone

import pandas as pd

from config import (
    INSTRUMENTS, DUAL_AGENT_MODE, PAPER_TRADING,
    ADX_PERIOD, ADX_TRENDING_THRESHOLD, ADX_WEAK_THRESHOLD,
    ATR_PERIOD, ATR_HIGH_VOL_MULTIPLIER, ATR_LOW_VOL_MULTIPLIER,
    REGIME_TF, REGIME_HTF, REGIME_LOOKBACK,
    SCALP_SESSIONS, TRAIL_ACTIVATION_RR, TRAIL_STEP_PIPS,
    SCALP_MAX_HOLD_MINUTES, SWING_MAX_HOLD_HOURS,
)
from agents.scalping import ScalpingAgent
from agents.swing import SwingAgent

logger = logging.getLogger(__name__)


class Overseer:
    """
    Master control agent. Classifies market regime, selects the active
    trading agent, enforces FTMO rules, and gates every trade.
    """

    def __init__(self, mt5_bridge, risk_manager):
        self.mt5 = mt5_bridge
        self.risk = risk_manager
        self.scalper = ScalpingAgent(mt5_bridge, risk_manager)
        self.swinger = SwingAgent(mt5_bridge, risk_manager)
        self.active_agent = None
        self.regime = "UNKNOWN"
        self.cycle_count = 0

    # ── Market Regime Detection ────────────────────────────────

    def _calc_adx(self, df: pd.DataFrame, period: int = ADX_PERIOD) -> float:
        """Calculate ADX (Average Directional Index)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # +DM / -DM
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        # Smoothed averages
        atr = tr.ewm(span=period).mean()
        plus_di = 100 * (plus_dm.ewm(span=period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period).mean() / atr)

        # ADX
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.ewm(span=period).mean()

        return adx.iloc[-1] if not adx.empty else 0

    def _calc_atr(self, df: pd.DataFrame, period: int = ATR_PERIOD) -> tuple[float, float]:
        """Calculate current ATR and average ATR for volatility comparison."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(span=period).mean()
        current_atr = atr.iloc[-1]
        avg_atr = atr.iloc[-REGIME_LOOKBACK:].mean()

        return current_atr, avg_atr

    def classify_regime(self, symbol: str = "EURUSD") -> str:
        """
        Classify the current market regime using ADX and ATR.

        Returns: "TRENDING", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY"
        """
        df = self.mt5.get_candles(symbol, REGIME_TF, REGIME_LOOKBACK + 50)
        if df is None or len(df) < 50:
            return "UNKNOWN"

        adx = self._calc_adx(df)
        current_atr, avg_atr = self._calc_atr(df)

        atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        # Classification logic
        if atr_ratio >= ATR_HIGH_VOL_MULTIPLIER:
            regime = "HIGH_VOLATILITY"
        elif atr_ratio <= ATR_LOW_VOL_MULTIPLIER:
            regime = "LOW_VOLATILITY"
        elif adx >= ADX_TRENDING_THRESHOLD:
            regime = "TRENDING"
        elif adx <= ADX_WEAK_THRESHOLD:
            regime = "LOW_VOLATILITY"
        else:
            regime = "RANGING"

        logger.info(
            "REGIME: %s (ADX=%.1f, ATR ratio=%.2f, Current ATR=%.5f)",
            regime, adx, atr_ratio, current_atr,
        )
        return regime

    # ── Agent Selection ────────────────────────────────────────

    def select_agents(self, regime: str) -> list[str]:
        """
        Decide which agent(s) to activate based on regime.

        In DUAL_AGENT_MODE: both agents run simultaneously (paper training).
        In single-agent mode: one agent selected by regime.

        TRENDING       → Swing (+ Scalping in dual mode)
        HIGH_VOLATILITY → Scalping (+ Swing in dual mode)
        RANGING        → Limited scalping OR none
        LOW_VOLATILITY → No trading
        """
        if DUAL_AGENT_MODE:
            # Both agents always active unless LOW_VOLATILITY
            if regime == "LOW_VOLATILITY":
                return []
            return ["scalping", "swing"]

        # Single-agent mode (production/FTMO)
        if regime == "TRENDING":
            return ["swing"]
        elif regime == "HIGH_VOLATILITY":
            return ["scalping"]
        elif regime == "RANGING":
            if self._in_active_session():
                return ["scalping"]
            return []
        else:
            return []

    def _in_active_session(self) -> bool:
        """Check if we're in an active trading session (London/NY overlap)."""
        now = datetime.now(timezone.utc)
        hour = now.hour

        # London open: 7-9 UTC
        if 7 <= hour <= 9:
            return True
        # NY open / London-NY overlap: 12-15 UTC
        if 12 <= hour <= 15:
            return True

        return False

    # ── Trade Gating ───────────────────────────────────────────

    def _validate_proposal(self, proposal: dict) -> dict:
        """
        Final gate for every trade. The Overseer is strict.
        Returns decision dict with ALLOW/BLOCK and reasoning.
        """
        decision = {
            "action": "BLOCK",
            "trade": proposal,
            "reason": "",
            "agent": proposal.get("agent", "unknown"),
        }

        # 1. Must have BOS or CHoCH
        if proposal.get("structure") not in ("bos", "choch"):
            decision["reason"] = "No BOS or CHoCH detected"
            return decision

        # 2. Must have liquidity sweep
        if not proposal.get("sweep_type"):
            decision["reason"] = "No liquidity sweep detected"
            return decision

        # 3. Must have OB or FVG entry
        if proposal.get("entry_zone_type") not in ("order_block", "fvg"):
            decision["reason"] = "No valid entry zone (OB/FVG)"
            return decision

        # 4. Must align with bias
        if not proposal.get("bias") or proposal["bias"] == "neutral":
            decision["reason"] = "No clear directional bias"
            return decision

        # 5. R:R check (agent-specific minimums already checked, but double-check)
        if proposal.get("risk_reward", 0) < 2.0:
            decision["reason"] = f"R:R too low: {proposal.get('risk_reward', 0)}"
            return decision

        # 6. Final FTMO check
        can_trade, ftmo_reason = self.risk.can_trade()
        if not can_trade:
            decision["reason"] = f"FTMO block: {ftmo_reason}"
            return decision

        # All checks passed
        decision["action"] = "ALLOW"
        decision["reason"] = "All SMC criteria met, FTMO compliant"
        return decision

    # ── Trade Management ───────────────────────────────────────

    def manage_open_trades(self):
        """
        Manage existing positions:
        - Trailing stop activation
        - Max hold time enforcement
        - Emergency close if FTMO limits approached
        """
        positions = self.mt5.get_open_positions()
        if not positions:
            return

        risk_status = self.risk.get_risk_status()

        # Emergency: approaching FTMO limits
        if risk_status["daily_dd_pct"] >= risk_status["daily_limit_pct"] * 0.9:
            logger.warning("Approaching daily DD limit! Closing all positions.")
            self.risk.emergency_close_all("Approaching daily DD limit")
            return

        now = datetime.now(timezone.utc)

        for pos in positions:
            symbol = pos["symbol"]
            sym_info = self.mt5.get_symbol_info(symbol)
            if not sym_info:
                continue

            pip_size = sym_info["point"] * (10 if sym_info["digits"] in (3, 5) else 1)

            # Check max hold time
            hold_time = now - pos["open_time"]
            is_scalp = "SCALP" in (pos.get("comment") or "").upper()
            max_hold_seconds = (
                SCALP_MAX_HOLD_MINUTES * 60 if is_scalp
                else SWING_MAX_HOLD_HOURS * 3600
            )

            if hold_time.total_seconds() > max_hold_seconds:
                logger.info(
                    "Max hold time exceeded for %s ticket %d — closing",
                    symbol, pos["ticket"],
                )
                self.mt5.close_position(pos["ticket"])
                continue

            # Trailing stop
            entry = pos["open_price"]
            current = pos["current_price"]
            sl = pos["sl"]

            if pos["direction"] == "buy":
                sl_distance = entry - sl
                profit_distance = current - entry
                if sl_distance > 0:
                    rr_current = profit_distance / sl_distance
                    if rr_current >= TRAIL_ACTIVATION_RR:
                        new_sl = current - (TRAIL_STEP_PIPS * pip_size)
                        if new_sl > sl:
                            self.mt5.modify_sl(pos["ticket"], new_sl)

            elif pos["direction"] == "sell":
                sl_distance = sl - entry
                profit_distance = entry - current
                if sl_distance > 0:
                    rr_current = profit_distance / sl_distance
                    if rr_current >= TRAIL_ACTIVATION_RR:
                        new_sl = current + (TRAIL_STEP_PIPS * pip_size)
                        if new_sl < sl:
                            self.mt5.modify_sl(pos["ticket"], new_sl)

    # ── Main Cycle ─────────────────────────────────────────────

    def run_cycle(self) -> dict:
        """
        Execute one complete Overseer cycle.
        In dual-agent mode, both agents run and proposals are deduplicated.

        Returns a summary dict with all decisions and reasoning.
        """
        self.cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        mode_label = "PAPER/DUAL" if (PAPER_TRADING and DUAL_AGENT_MODE) else "LIVE"

        summary = {
            "cycle": self.cycle_count,
            "timestamp": cycle_start.isoformat(),
            "mode": mode_label,
            "market_condition": "UNKNOWN",
            "active_agents": [],
            "trade_decision": "BLOCK",
            "trades_executed": [],
            "reasoning": "",
            "ftmo_status": {},
        }

        # ── Step 1: FTMO status check ─────────────────────────
        risk_status = self.risk.get_risk_status()
        summary["ftmo_status"] = risk_status

        if not risk_status["can_trade"]:
            summary["reasoning"] = f"Trading blocked: {risk_status['reason']}"
            summary["trade_decision"] = "BLOCK"
            logger.warning("OVERSEER CYCLE %d — BLOCKED: %s", self.cycle_count, risk_status["reason"])
            self.manage_open_trades()
            return summary

        # ── Step 2: Classify market regime ─────────────────────
        self.regime = self.classify_regime()
        summary["market_condition"] = self.regime

        # ── Step 3: Select agent(s) ────────────────────────────
        agent_choices = self.select_agents(self.regime)
        summary["active_agents"] = agent_choices

        if not agent_choices:
            summary["trade_decision"] = "BLOCK"
            summary["reasoning"] = f"No trading in {self.regime} conditions"
            logger.info(
                "OVERSEER CYCLE %d — %s | Agents: NONE | No trade",
                self.cycle_count, self.regime,
            )
            self.manage_open_trades()
            return summary

        # ── Step 4: Run all active agents ──────────────────────
        all_proposals = []
        agents_map = {"scalping": self.scalper, "swing": self.swinger}

        for agent_name in agent_choices:
            agent = agents_map[agent_name]
            proposals = agent.scan_instruments(INSTRUMENTS)
            for p in proposals:
                p["_agent_name"] = agent_name
            all_proposals.extend(proposals)
            logger.info(
                "CYCLE %d — %s agent found %d proposal(s)",
                self.cycle_count, agent_name.upper(), len(proposals),
            )

        if not all_proposals:
            summary["trade_decision"] = "BLOCK"
            agents_str = " + ".join(a.upper() for a in agent_choices)
            summary["reasoning"] = f"{agents_str} found no setups"
            logger.info(
                "OVERSEER CYCLE %d — %s | Agents: %s | No setups",
                self.cycle_count, self.regime, agents_str,
            )
            self.manage_open_trades()
            return summary

        # ── Step 4b: Deduplicate — if both agents signal the same
        # symbol in the same direction, keep the better R:R one.
        # If they conflict (buy vs sell on same symbol), block both.
        deduped = self._deduplicate_proposals(all_proposals)

        # ── Step 5: Gate each proposal ─────────────────────────
        for proposal in deduped:
            decision = self._validate_proposal(proposal)
            agent_name = proposal.get("_agent_name", proposal.get("agent", "unknown"))

            if decision["action"] == "ALLOW":
                comment = f"SMC_{agent_name.upper()}"
                result = self.mt5.place_order(
                    symbol=proposal["symbol"],
                    direction=proposal["direction"],
                    lot_size=proposal["lot_size"],
                    sl_price=proposal["sl"],
                    tp_price=proposal["tp"],
                    comment=comment,
                )

                if result:
                    summary["trades_executed"].append({
                        "symbol": proposal["symbol"],
                        "direction": proposal["direction"],
                        "lot_size": proposal["lot_size"],
                        "entry": result["price"],
                        "sl": proposal["sl"],
                        "tp": proposal["tp"],
                        "rr": proposal["risk_reward"],
                        "ticket": result["ticket"],
                        "agent": agent_name,
                    })
                    logger.info(
                        "OVERSEER CYCLE %d — TRADE EXECUTED [%s]: %s %s %.2f lots @ %.5f | R:R=%.2f",
                        self.cycle_count, agent_name.upper(),
                        proposal["direction"].upper(),
                        proposal["symbol"], proposal["lot_size"],
                        result["price"], proposal["risk_reward"],
                    )

                    # Re-check risk after each trade
                    can_continue, _ = self.risk.can_trade()
                    if not can_continue:
                        logger.info("Risk limit reached — stopping further entries this cycle")
                        break
            else:
                logger.info(
                    "OVERSEER CYCLE %d — BLOCKED [%s] %s %s: %s",
                    self.cycle_count, agent_name.upper(),
                    proposal["direction"].upper(),
                    proposal["symbol"], decision["reason"],
                )

        # Set final summary
        if summary["trades_executed"]:
            summary["trade_decision"] = "ALLOW"
            scalp_count = sum(1 for t in summary["trades_executed"] if t["agent"] == "scalping")
            swing_count = sum(1 for t in summary["trades_executed"] if t["agent"] == "swing")
            summary["reasoning"] = (
                f"Executed {len(summary['trades_executed'])} trade(s) — "
                f"Scalp: {scalp_count}, Swing: {swing_count}"
            )
        else:
            summary["trade_decision"] = "BLOCK"
            summary["reasoning"] = "All proposals blocked by Overseer validation"

        # ── Step 6: Manage open positions ──────────────────────
        self.manage_open_trades()

        # ── Log the cycle output ───────────────────────────────
        self._log_cycle_output(summary)

        return summary

    def _deduplicate_proposals(self, proposals: list[dict]) -> list[dict]:
        """
        Deduplicate proposals from both agents:
        - Same symbol, same direction: keep the one with better R:R
        - Same symbol, opposite direction: block both (conflicting signals)
        """
        by_symbol = {}
        for p in proposals:
            sym = p["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(p)

        result = []
        for sym, sym_proposals in by_symbol.items():
            if len(sym_proposals) == 1:
                result.append(sym_proposals[0])
                continue

            directions = set(p["direction"] for p in sym_proposals)
            if len(directions) > 1:
                # Conflicting signals — block both
                logger.info(
                    "DEDUP: %s has conflicting signals (buy + sell) — blocking both",
                    sym,
                )
                continue

            # Same direction — keep best R:R
            best = max(sym_proposals, key=lambda p: p.get("risk_reward", 0))
            logger.info(
                "DEDUP: %s has %d signals same direction — keeping %s (R:R=%.2f)",
                sym, len(sym_proposals), best.get("_agent_name", "?"),
                best.get("risk_reward", 0),
            )
            result.append(best)

        return result

    def _log_cycle_output(self, summary: dict):
        """Log the cycle output in the specified format."""
        ftmo = summary["ftmo_status"]
        agents = summary.get("active_agents", [])
        agents_str = " + ".join(a.upper() for a in agents) if agents else "NONE"

        logger.info(
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║  OVERSEER CYCLE #%-6d           [%-12s]   ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            "║ Market Condition : %-32s ║\n"
            "║ Active Agents    : %-32s ║\n"
            "║ Trade Decision   : %-32s ║\n"
            "║ Trades Executed  : %-32d ║\n"
            "║ Reasoning        : %-32s ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            "║ FTMO Status                                          ║\n"
            "║  Daily DD : %5.2f%% / %4.1f%%  |  Total DD : %5.2f%% / %4.1f%%  ║\n"
            "║  Open Pos : %-4d            |  Equity   : $%-12.2f ║\n"
            "║  FTMO Compliance : %-34s ║\n"
            "╚══════════════════════════════════════════════════════╝",
            summary["cycle"], summary.get("mode", "LIVE"),
            summary["market_condition"],
            agents_str,
            summary["trade_decision"],
            len(summary["trades_executed"]),
            summary["reasoning"][:32],
            ftmo.get("daily_dd_pct", 0), ftmo.get("daily_limit_pct", 4.5),
            ftmo.get("total_dd_pct", 0), ftmo.get("total_limit_pct", 9.0),
            ftmo.get("open_positions", 0), ftmo.get("equity", 0),
            "PASS" if ftmo.get("can_trade", False) else "FAIL",
        )
