"""
SMC Dual-Agent Trading Bot — Risk Manager
Enforces FTMO constraints, calculates position sizes, and tracks drawdown.
"""

import logging
from datetime import datetime, timezone

from config import (
    ACCOUNT_BALANCE,
    MAX_DAILY_LOSS_PCT, MAX_TOTAL_DRAWDOWN_PCT,
    MAX_RISK_PER_TRADE_PCT, MAX_EXPOSURE_PCT,
    MAX_CONCURRENT_TRADES,
    DAILY_LOSS_BUFFER_PCT, TOTAL_DD_BUFFER_PCT,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """Enforces FTMO risk rules and calculates safe position sizes."""

    def __init__(self, mt5_bridge):
        self.mt5 = mt5_bridge
        self.starting_balance = ACCOUNT_BALANCE
        self.daily_start_balance = ACCOUNT_BALANCE
        self.last_reset_date = None
        self.high_water_mark = ACCOUNT_BALANCE
        self._sync_account()

    # ── Account Sync ───────────────────────────────────────────

    def _sync_account(self):
        """Sync balance from MT5."""
        info = self.mt5.get_account_info()
        if info:
            self.starting_balance = info["balance"]
            self.high_water_mark = max(self.high_water_mark, info["balance"])
            self._maybe_reset_daily(info["balance"])

    def _maybe_reset_daily(self, balance: float):
        """Reset daily tracking at the start of each new day."""
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date != today:
            self.daily_start_balance = balance
            self.last_reset_date = today
            logger.info(
                "Daily reset — Date: %s, Starting balance: %.2f",
                today, balance,
            )

    # ── FTMO Constraint Checks ─────────────────────────────────

    def get_risk_status(self) -> dict:
        """Calculate current risk metrics."""
        info = self.mt5.get_account_info()
        if not info:
            return {"can_trade": False, "reason": "Cannot reach MT5"}

        equity = info["equity"]
        balance = info["balance"]
        self._maybe_reset_daily(balance)
        self.high_water_mark = max(self.high_water_mark, balance)

        # Daily drawdown: from today's starting balance
        daily_pnl = self.mt5.get_daily_profit()
        daily_dd_pct = abs(min(0, daily_pnl)) / self.daily_start_balance * 100

        # Total drawdown: from high water mark
        total_dd = self.high_water_mark - equity
        total_dd_pct = total_dd / self.high_water_mark * 100

        # Open positions
        positions = self.mt5.get_open_positions()
        open_count = len(positions)
        total_exposure = sum(p["lot_size"] for p in positions)

        # Effective limits (with safety buffer)
        daily_limit = MAX_DAILY_LOSS_PCT - DAILY_LOSS_BUFFER_PCT
        total_limit = MAX_TOTAL_DRAWDOWN_PCT - TOTAL_DD_BUFFER_PCT

        can_trade = True
        reasons = []

        if daily_dd_pct >= daily_limit:
            can_trade = False
            reasons.append(
                f"Daily DD {daily_dd_pct:.2f}% >= limit {daily_limit:.1f}%"
            )

        if total_dd_pct >= total_limit:
            can_trade = False
            reasons.append(
                f"Total DD {total_dd_pct:.2f}% >= limit {total_limit:.1f}%"
            )

        if open_count >= MAX_CONCURRENT_TRADES:
            can_trade = False
            reasons.append(
                f"Max concurrent trades reached ({open_count}/{MAX_CONCURRENT_TRADES})"
            )

        return {
            "can_trade": can_trade,
            "reason": "; ".join(reasons) if reasons else "OK",
            "equity": equity,
            "balance": balance,
            "daily_pnl": daily_pnl,
            "daily_dd_pct": daily_dd_pct,
            "total_dd_pct": total_dd_pct,
            "open_positions": open_count,
            "total_exposure": total_exposure,
            "high_water_mark": self.high_water_mark,
            "daily_limit_pct": daily_limit,
            "total_limit_pct": total_limit,
        }

    def can_trade(self) -> tuple[bool, str]:
        """Quick check: are we allowed to open new trades?"""
        status = self.get_risk_status()
        return status["can_trade"], status["reason"]

    # ── Position Sizing ────────────────────────────────────────

    def calculate_lot_size(
        self,
        symbol: str,
        sl_distance_price: float,
    ) -> float | None:
        """
        Calculate safe lot size based on:
        - Max risk per trade (1% of equity)
        - Stop loss distance
        - Symbol contract specs

        Returns lot size or None if trade should be rejected.
        """
        info = self.mt5.get_account_info()
        if not info:
            return None

        sym_info = self.mt5.get_symbol_info(symbol)
        if not sym_info:
            return None

        equity = info["equity"]

        # Max dollar risk for this trade
        max_risk_dollars = equity * (MAX_RISK_PER_TRADE_PCT / 100)

        # Calculate tick value and distance
        tick_size = sym_info["trade_tick_size"]
        tick_value = sym_info["trade_tick_value"]
        contract_size = sym_info["trade_contract_size"]

        if tick_size == 0 or sl_distance_price == 0:
            logger.warning("Invalid tick_size or SL distance for %s", symbol)
            return None

        # Number of ticks in our SL
        sl_ticks = abs(sl_distance_price) / tick_size

        # Dollar risk per lot for this SL distance
        risk_per_lot = sl_ticks * tick_value

        if risk_per_lot == 0:
            return None

        # Lot size = max risk / risk per lot
        lot_size = max_risk_dollars / risk_per_lot

        # Enforce max exposure
        positions = self.mt5.get_open_positions()
        current_exposure = sum(p["lot_size"] for p in positions)
        max_additional = (equity * MAX_EXPOSURE_PCT / 100) - current_exposure

        if max_additional <= 0:
            logger.warning("Max exposure reached, cannot open new position")
            return None

        lot_size = min(lot_size, max_additional)

        # Clamp to symbol limits
        lot_size = max(sym_info["volume_min"], lot_size)
        lot_size = min(sym_info["volume_max"], lot_size)

        # Round to volume step
        vol_step = sym_info["volume_step"]
        lot_size = round(round(lot_size / vol_step) * vol_step, 8)

        logger.info(
            "Position size for %s: %.4f lots (risk $%.2f, SL %.5f, R/lot $%.2f)",
            symbol, lot_size, max_risk_dollars, sl_distance_price, risk_per_lot,
        )
        return lot_size

    # ── Trade Validation ───────────────────────────────────────

    def validate_trade(
        self,
        symbol: str,
        direction: str,
        sl_price: float,
        tp_price: float,
        entry_price: float,
    ) -> dict:
        """
        Full pre-trade validation. Returns dict with approval status and details.
        """
        result = {
            "approved": False,
            "reason": "",
            "lot_size": 0.0,
            "risk_reward": 0.0,
        }

        # 1. Can we trade at all?
        allowed, reason = self.can_trade()
        if not allowed:
            result["reason"] = f"FTMO block: {reason}"
            return result

        # 2. Validate SL/TP make sense
        if direction == "buy":
            if sl_price >= entry_price:
                result["reason"] = "SL must be below entry for buy"
                return result
            if tp_price <= entry_price:
                result["reason"] = "TP must be above entry for buy"
                return result
        elif direction == "sell":
            if sl_price <= entry_price:
                result["reason"] = "SL must be above entry for sell"
                return result
            if tp_price >= entry_price:
                result["reason"] = "TP must be below entry for sell"
                return result

        # 3. Check risk:reward
        sl_distance = abs(entry_price - sl_price)
        tp_distance = abs(tp_price - entry_price)

        if sl_distance == 0:
            result["reason"] = "SL distance is zero"
            return result

        rr = tp_distance / sl_distance
        result["risk_reward"] = round(rr, 2)

        # 4. Calculate position size
        lot_size = self.calculate_lot_size(symbol, sl_distance)
        if lot_size is None or lot_size <= 0:
            result["reason"] = "Cannot calculate valid lot size"
            return result

        result["lot_size"] = lot_size
        result["approved"] = True
        result["reason"] = "Trade approved"
        return result

    # ── Emergency Actions ──────────────────────────────────────

    def emergency_close_all(self, reason: str):
        """Close all open positions immediately."""
        logger.critical("EMERGENCY CLOSE ALL — Reason: %s", reason)
        positions = self.mt5.get_open_positions()
        for pos in positions:
            self.mt5.close_position(pos["ticket"])
        logger.info("Emergency close complete — %d positions closed", len(positions))
