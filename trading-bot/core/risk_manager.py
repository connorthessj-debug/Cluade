"""Centralised risk management for the trading bot system.

Enforces per-bot position limits, global drawdown constraints,
correlation checks, and a kill switch.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from .config import Config

logger = logging.getLogger(__name__)


class RiskManager:
    """Gate-keeper that must approve every trade before execution."""

    def __init__(self, config: Config, database) -> None:
        """
        Args:
            config: Fully loaded Config instance.
            database: Database instance for querying P&L and positions.
        """
        self._config = config
        self._db = database
        self._kill_switch_active = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def approve_trade(
        self,
        bot_name: str,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        entry_price: float,
    ) -> bool:
        """Run all risk checks and return True if the trade is approved.

        Checks executed (in order):
            1. Kill switch
            2. Per-bot max concurrent positions
            3. Per-bot max position size
            4. Global drawdown
            5. Correlation guard
        """
        # 1. Kill switch --------------------------------------------------
        if self._kill_switch_active:
            logger.warning("Trade REJECTED for %s: kill switch is active", bot_name)
            return False

        # 2. Per-bot max concurrent positions -----------------------------
        if not await self._check_max_positions(bot_name):
            return False

        # 3. Per-bot max position size ------------------------------------
        if not self._check_position_size(bot_name, amount, entry_price):
            return False

        # 4. Global drawdown ----------------------------------------------
        if not await self._check_global_drawdown():
            return False

        # 5. Correlation guard --------------------------------------------
        if not await self.check_correlation(bot_name, symbol, side):
            return False

        logger.info(
            "Trade APPROVED for %s: %s %s %.4f @ %.6f (SL %.6f)",
            bot_name, side, symbol, amount, entry_price, stop_loss,
        )
        return True

    def get_position_size(
        self,
        bot_name: str,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
    ) -> float:
        """Calculate position size based on the bot's risk percentage.

        Uses the formula:
            risk_amount = account_balance * max_risk_pct / 100
            distance    = |entry_price - stop_loss|
            size        = risk_amount / distance

        Returns:
            Position size in base-currency units.
        """
        risk_pct = self._get_bot_risk_pct(bot_name)
        risk_amount = account_balance * (risk_pct / 100.0)
        distance = abs(entry_price - stop_loss)
        if distance == 0:
            logger.error("Stop-loss distance is zero for %s – cannot size position", bot_name)
            return 0.0
        size = risk_amount / distance
        return size

    async def check_correlation(self, bot_name: str, symbol: str, side: str) -> bool:
        """Prevent all bots from piling into the same direction on the same asset.

        Returns False if another bot already has an open position on *symbol*
        in the same *side* direction.
        """
        if not self._config.risk.correlation_check:
            return True

        open_positions = await self._db.get_positions(status="open")
        for pos in open_positions:
            if pos["bot_name"] != bot_name and pos["symbol"] == symbol and pos["side"] == side:
                logger.warning(
                    "Trade REJECTED for %s: correlation conflict – %s already %s on %s",
                    bot_name, pos["bot_name"], side, symbol,
                )
                return False
        return True

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    async def _check_max_positions(self, bot_name: str) -> bool:
        """Verify the bot hasn't exceeded its max concurrent positions."""
        max_positions = self._get_bot_max_positions(bot_name)
        open_positions = await self._db.get_positions(bot_name=bot_name, status="open")
        if len(open_positions) >= max_positions:
            logger.warning(
                "Trade REJECTED for %s: max positions reached (%d/%d)",
                bot_name, len(open_positions), max_positions,
            )
            return False
        return True

    def _check_position_size(self, bot_name: str, amount: float, entry_price: float) -> bool:
        """Verify the notional value doesn't exceed the bot's max position."""
        max_position = self._get_bot_max_position_value(bot_name)
        if max_position is not None:
            notional = amount * entry_price
            if notional > max_position:
                logger.warning(
                    "Trade REJECTED for %s: notional %.2f exceeds max %.2f",
                    bot_name, notional, max_position,
                )
                return False
        return True

    async def _check_global_drawdown(self) -> bool:
        """Check whether the global drawdown limit has been breached.

        Sums realised P&L across all bots and compares against the
        configured maximum drawdown percentage.
        """
        max_dd = self._config.risk.global_max_drawdown_pct
        trades = await self._db.get_trades(limit=10000)
        total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)

        # We approximate drawdown as negative cumulative P&L.
        # In production this would use peak-equity tracking.
        if total_pnl < 0:
            # Rough check: treat initial equity as unknown, flag if loss is
            # present and kill_switch is enabled. A real implementation would
            # track starting equity; here we use a simplified metric via
            # performance_metrics or account balance queries.
            logger.debug("Global P&L: %.2f", total_pnl)

        # Activate kill switch if enabled and drawdown exceeded
        if self._config.risk.kill_switch_enabled and total_pnl < 0:
            # Use performance metrics to check against equity peak
            metrics = await self._db.get_performance_metrics(limit=1)
            if metrics:
                # Check if we have an equity_peak recorded
                peak_equity = None
                all_metrics = await self._db.get_performance_metrics(limit=10000)
                for m in all_metrics:
                    if m.get("metric_name") == "equity_peak":
                        peak_equity = m.get("metric_value")
                        break
                if peak_equity and peak_equity > 0:
                    drawdown_pct = (abs(total_pnl) / peak_equity) * 100
                    if drawdown_pct >= max_dd:
                        self._kill_switch_active = True
                        logger.critical(
                            "KILL SWITCH ACTIVATED: drawdown %.2f%% >= max %.2f%%",
                            drawdown_pct, max_dd,
                        )
                        return False

        return True

    # ------------------------------------------------------------------
    # Config lookups
    # ------------------------------------------------------------------

    def _get_bot_risk_pct(self, bot_name: str) -> float:
        """Return the max risk percentage for the given bot."""
        if "scalp" in bot_name.lower():
            return self._config.scalper.max_risk_pct
        if "swing" in bot_name.lower():
            return self._config.swing.max_risk_pct
        if "arb" in bot_name.lower():
            return 0.5  # conservative default for arbitrage
        return 0.5

    def _get_bot_max_positions(self, bot_name: str) -> int:
        """Return the max concurrent positions for the given bot."""
        if "scalp" in bot_name.lower():
            return self._config.scalper.max_positions
        if "swing" in bot_name.lower():
            return self._config.swing.max_positions
        if "arb" in bot_name.lower():
            return 5  # arbitrage can have more concurrent legs
        return 3

    def _get_bot_max_position_value(self, bot_name: str) -> Optional[float]:
        """Return the max notional position value, or None for no limit."""
        if "arb" in bot_name.lower():
            return self._config.arbitrage.max_position
        return None
