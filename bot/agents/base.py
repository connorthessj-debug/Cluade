"""
Base Trading Agent — Shared interface and logic for all agents.
"""

import logging
from abc import ABC, abstractmethod

import pandas as pd

from smc.structure import detect_structure, get_current_bias
from smc.liquidity import has_recent_sweep
from smc.zones import find_entry_zone
from smc.sentiment import sentiment_confirms

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for Scalping and Swing agents."""

    agent_name: str = "base"

    def __init__(self, mt5_bridge, risk_manager):
        self.mt5 = mt5_bridge
        self.risk = risk_manager

    @abstractmethod
    def get_timeframes(self) -> dict:
        """Return dict with 'entry', 'confirm', 'structure' timeframe strings."""

    @abstractmethod
    def get_min_rr(self) -> float:
        """Minimum risk:reward ratio for this agent."""

    @abstractmethod
    def calculate_sl_tp(self, df: pd.DataFrame, direction: str, entry_zone: dict, pip_size: float) -> dict | None:
        """Calculate SL and TP prices. Returns dict with 'sl', 'tp', 'entry' or None."""

    def analyze_symbol(self, symbol: str) -> dict | None:
        """
        Full SMC analysis pipeline for one symbol.

        Steps:
        1. Get candle data for all timeframes
        2. Detect structure (BOS/CHoCH) on structure TF
        3. Determine directional bias
        4. Check for liquidity sweep
        5. Find entry zone (OB or FVG)
        6. Confirm with sentiment
        7. Calculate SL/TP
        8. Validate with risk manager

        Returns trade proposal dict or None.
        """
        tfs = self.get_timeframes()

        # Get symbol info for pip calculations
        sym_info = self.mt5.get_symbol_info(symbol)
        if not sym_info:
            return None
        pip_size = sym_info["point"] * (10 if sym_info["digits"] in (3, 5) else 1)

        # ── Step 1: Fetch candle data ──────────────────────────
        df_structure = self.mt5.get_candles(symbol, tfs["structure"], 200)
        df_entry = self.mt5.get_candles(symbol, tfs["entry"], 200)
        df_confirm = self.mt5.get_candles(symbol, tfs["confirm"], 200)

        if df_structure is None or df_entry is None or df_confirm is None:
            logger.debug("No data for %s", symbol)
            return None

        # ── Step 2: Detect structure on higher TF ──────────────
        structure_breaks = detect_structure(df_structure)
        if not structure_breaks:
            logger.debug("%s: No structure breaks found", symbol)
            return None

        recent_break = structure_breaks[-1]
        has_bos_or_choch = recent_break.kind in ("bos", "choch")
        if not has_bos_or_choch:
            return None

        # ── Step 3: Determine directional bias ─────────────────
        bias = get_current_bias(df_structure)
        if bias == "neutral":
            logger.debug("%s: Neutral bias, skipping", symbol)
            return None

        direction = "buy" if bias == "bullish" else "sell"

        # ── Step 4: Check for liquidity sweep ──────────────────
        sweep = has_recent_sweep(df_entry, bias, pip_size)
        if sweep is None:
            logger.debug("%s: No recent liquidity sweep for %s", symbol, bias)
            return None

        # ── Step 5: Find entry zone (OB or FVG) ───────────────
        entry_zone = find_entry_zone(df_entry, bias, pip_size)
        if entry_zone is None:
            logger.debug("%s: No valid entry zone found", symbol)
            return None

        # ── Step 6: Sentiment confirmation ─────────────────────
        if not sentiment_confirms(df_confirm, bias):
            logger.debug("%s: Sentiment does not confirm %s", symbol, bias)
            return None

        # ── Step 7: Calculate SL/TP ────────────────────────────
        levels = self.calculate_sl_tp(df_entry, direction, entry_zone, pip_size)
        if levels is None:
            return None

        # ── Step 8: Check R:R ──────────────────────────────────
        sl_dist = abs(levels["entry"] - levels["sl"])
        tp_dist = abs(levels["tp"] - levels["entry"])
        if sl_dist == 0:
            return None
        rr = tp_dist / sl_dist

        if rr < self.get_min_rr():
            logger.debug(
                "%s: R:R %.2f below minimum %.2f", symbol, rr, self.get_min_rr()
            )
            return None

        # ── Step 9: Risk validation ────────────────────────────
        validation = self.risk.validate_trade(
            symbol=symbol,
            direction=direction,
            sl_price=levels["sl"],
            tp_price=levels["tp"],
            entry_price=levels["entry"],
        )

        if not validation["approved"]:
            logger.debug("%s: Risk rejected — %s", symbol, validation["reason"])
            return None

        # ── Build trade proposal ───────────────────────────────
        return {
            "symbol": symbol,
            "direction": direction,
            "entry": levels["entry"],
            "sl": levels["sl"],
            "tp": levels["tp"],
            "lot_size": validation["lot_size"],
            "risk_reward": round(rr, 2),
            "agent": self.agent_name,
            "structure": recent_break.kind,
            "structure_direction": recent_break.direction,
            "sweep_type": sweep.kind,
            "entry_zone_type": entry_zone["type"],
            "bias": bias,
        }

    def scan_instruments(self, instruments: list[str]) -> list[dict]:
        """Scan all instruments and return valid trade proposals."""
        proposals = []
        for symbol in instruments:
            try:
                proposal = self.analyze_symbol(symbol)
                if proposal:
                    proposals.append(proposal)
                    logger.info(
                        "%s SIGNAL — %s %s | Entry=%.5f SL=%.5f TP=%.5f | R:R=%.2f | %s %s",
                        self.agent_name.upper(), proposal["direction"].upper(),
                        symbol, proposal["entry"], proposal["sl"], proposal["tp"],
                        proposal["risk_reward"], proposal["structure"],
                        proposal["entry_zone_type"],
                    )
            except Exception as e:
                logger.error("Error analyzing %s: %s", symbol, e, exc_info=True)
        return proposals
