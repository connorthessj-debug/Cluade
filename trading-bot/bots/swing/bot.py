"""Swing trading bot for OANDA forex using ICT/SMC methodology.

Operates on higher timeframes (W1/D1/H4/H1) with longer hold periods.
Manages partial take-profit at 1R and 2R, breakeven stop-loss management,
and trailing stops for the remaining runner position. Max 2 concurrent
positions.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional

from bots.base_bot import BaseBot
from bots.swing.strategy import SwingStrategy
from core.models import TradeSetup

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 60  # seconds – swing trades don't need fast polling


class SwingBot(BaseBot):
    """ICT/SMC-based swing trading bot operating on OANDA.

    Parameters
    ----------
    config : Config
        System configuration (must include ``swing`` and ``oanda`` sections).
    database : object
        Database adapter for state persistence.
    risk_manager : object
        Pre-trade risk checks.
    publisher : object
        Event publisher for status and trade notifications.
    oanda_client : object
        OANDA API client providing ``get_candles``, ``place_order``,
        ``get_open_positions``, ``modify_trade``, ``close_trade``,
        and ``get_account_summary`` async methods.
    """

    def __init__(self, config, database, risk_manager, publisher, oanda_client):
        super().__init__("swing", config, database, risk_manager, publisher)
        self.oanda = oanda_client

        swing_cfg = config.swing
        self.instruments: List[str] = config.oanda.instruments
        self.min_confluence: int = swing_cfg.min_confluence
        self.max_risk_pct: float = swing_cfg.max_risk_pct / 100.0  # fraction
        self.min_rr: float = swing_cfg.min_rr
        self.max_positions: int = swing_cfg.max_positions
        self.partial_tp_levels: List[float] = swing_cfg.partial_tp  # [1.0, 2.0]

        self.strategy = SwingStrategy(
            min_confluence=self.min_confluence,
            min_rr=self.min_rr,
            partial_tp_levels=self.partial_tp_levels,
        )

        self._ensure_state_defaults()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _ensure_state_defaults(self):
        """Populate state with defaults if resuming from empty state."""
        self._state.setdefault("open_positions", {})
        self._state.setdefault("partial_tp_tracking", {})
        self._state.setdefault("active_setups", {})
        self._state.setdefault("total_trades", 0)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main swing trading loop."""
        logger.info(
            "%s: starting – instruments=%s, max_positions=%d, partial_tp=%s",
            self.name, self.instruments, self.max_positions, self.partial_tp_levels,
        )
        self._ensure_state_defaults()

        while self.running:
            try:
                await self.on_tick()
            except Exception:
                logger.exception("%s: error in on_tick", self.name)

            await self._heartbeat()
            await asyncio.sleep(_POLL_INTERVAL)

    async def on_tick(self):
        """Single iteration: manage positions, then scan for new setups."""
        # Step 1: manage existing positions (partials, breakeven, trailing)
        await self._manage_positions()

        # Step 2: scan for new setups if below max positions
        open_count = len(self._state.get("open_positions", {}))
        if open_count < self.max_positions:
            await self._scan_instruments()

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    async def _manage_positions(self):
        """Manage open positions: partial TP, breakeven SL, trailing stop."""
        open_positions = self._state.get("open_positions", {})
        if not open_positions:
            return

        try:
            broker_positions = await self.oanda.get_open_positions()
        except Exception:
            logger.exception("%s: failed to fetch open positions", self.name)
            return

        broker_map = _build_broker_map(broker_positions)
        closed_ids: List[str] = []

        for trade_id, pos_state in list(open_positions.items()):
            broker_pos = broker_map.get(trade_id)

            if broker_pos is None:
                logger.info(
                    "%s: position %s no longer open, removing from state",
                    self.name, trade_id,
                )
                closed_ids.append(trade_id)
                continue

            current_price = _extract_current_price(broker_pos)
            if current_price is None:
                continue

            entry_price = pos_state.get("entry_price", 0.0)
            stop_loss = pos_state.get("original_stop_loss", pos_state.get("stop_loss", 0.0))
            direction = pos_state.get("direction", "long")
            risk = abs(entry_price - stop_loss)

            if risk <= 0:
                continue

            # Calculate current R-multiple
            if direction == "long":
                r_multiple = (current_price - entry_price) / risk
            else:
                r_multiple = (entry_price - current_price) / risk

            tp_tracking = self._state.get("partial_tp_tracking", {}).get(trade_id, {})

            # Check 1R: take 33% profit, move SL to breakeven
            if r_multiple >= 1.0 and not tp_tracking.get("1r_taken"):
                await self._take_partial_profit(trade_id, pos_state, fraction=0.33, r_level="1r")
                await self._move_to_breakeven(trade_id, pos_state)
                tp_tracking["1r_taken"] = True
                self._state.setdefault("partial_tp_tracking", {})[trade_id] = tp_tracking
                await self._save_state()

            # Check 2R: take another 33%, set trailing stop
            elif r_multiple >= 2.0 and not tp_tracking.get("2r_taken"):
                await self._take_partial_profit(trade_id, pos_state, fraction=0.33, r_level="2r")
                await self._set_trailing_stop(trade_id, pos_state, current_price, risk)
                tp_tracking["2r_taken"] = True
                self._state.setdefault("partial_tp_tracking", {})[trade_id] = tp_tracking
                await self._save_state()

            # Update trailing stop for the runner (remaining ~34%)
            elif tp_tracking.get("2r_taken") and not tp_tracking.get("1r_taken", False) is False:
                await self._update_trailing_stop(trade_id, pos_state, current_price, risk)

        # Clean up closed positions
        for trade_id in closed_ids:
            open_positions.pop(trade_id, None)
            self._state.get("partial_tp_tracking", {}).pop(trade_id, None)
            await self.publisher.publish(self.name, "position_closed", {
                "trade_id": trade_id,
            })

        if closed_ids:
            await self._save_state()

    async def _take_partial_profit(
        self,
        trade_id: str,
        pos_state: Dict[str, Any],
        fraction: float,
        r_level: str,
    ):
        """Close a fraction of the position for partial take-profit."""
        original_units = pos_state.get("units", 0)
        close_units = int(abs(original_units) * fraction)

        if close_units <= 0:
            return

        # For OANDA, closing partial means placing an opposite order
        # or using the reduce endpoint. We close by specifying units.
        direction = pos_state.get("direction", "long")
        if direction == "long":
            close_units = -close_units  # sell to close long
        # else close_units stays positive to close short

        try:
            await self.oanda.close_trade(trade_id, units=close_units)
            pos_state["units"] = original_units - int(abs(original_units) * fraction) * (
                1 if direction == "long" else -1
            )

            logger.info(
                "%s: partial TP at %s – closed %d units of %s",
                self.name, r_level, abs(close_units), trade_id,
            )
            await self.publisher.publish(self.name, "partial_tp", {
                "trade_id": trade_id,
                "r_level": r_level,
                "units_closed": abs(close_units),
                "units_remaining": abs(pos_state["units"]),
            })
        except Exception:
            logger.exception(
                "%s: failed to take partial profit at %s for %s",
                self.name, r_level, trade_id,
            )

    async def _move_to_breakeven(self, trade_id: str, pos_state: Dict[str, Any]):
        """Move stop-loss to breakeven (entry price + small buffer)."""
        entry_price = pos_state.get("entry_price", 0.0)
        stop_loss = pos_state.get("original_stop_loss", pos_state.get("stop_loss", 0.0))
        direction = pos_state.get("direction", "long")
        risk = abs(entry_price - stop_loss)

        buffer = risk * 0.05  # 5% of risk as buffer
        if direction == "long":
            new_sl = entry_price + buffer
        else:
            new_sl = entry_price - buffer

        try:
            await self.oanda.modify_trade(trade_id, stop_loss=new_sl)
            pos_state["stop_loss"] = new_sl
            pos_state["sl_at_breakeven"] = True

            logger.info(
                "%s: moved SL to breakeven for %s – new SL=%.5f",
                self.name, trade_id, new_sl,
            )
            await self.publisher.publish(self.name, "sl_moved", {
                "trade_id": trade_id,
                "new_sl": new_sl,
                "reason": "breakeven_1r",
            })
        except Exception:
            logger.exception(
                "%s: failed to move SL to breakeven for %s", self.name, trade_id,
            )

    async def _set_trailing_stop(
        self,
        trade_id: str,
        pos_state: Dict[str, Any],
        current_price: float,
        risk: float,
    ):
        """Set a trailing stop at 1R behind the current price."""
        direction = pos_state.get("direction", "long")

        if direction == "long":
            new_sl = current_price - risk
        else:
            new_sl = current_price + risk

        try:
            await self.oanda.modify_trade(trade_id, stop_loss=new_sl)
            pos_state["stop_loss"] = new_sl
            pos_state["trailing_stop_active"] = True

            logger.info(
                "%s: trailing stop set for %s – SL=%.5f",
                self.name, trade_id, new_sl,
            )
        except Exception:
            logger.exception(
                "%s: failed to set trailing stop for %s", self.name, trade_id,
            )

    async def _update_trailing_stop(
        self,
        trade_id: str,
        pos_state: Dict[str, Any],
        current_price: float,
        risk: float,
    ):
        """Update trailing stop if price has moved further in our favour."""
        if not pos_state.get("trailing_stop_active"):
            return

        direction = pos_state.get("direction", "long")
        current_sl = pos_state.get("stop_loss", 0.0)

        if direction == "long":
            new_sl = current_price - risk
            if new_sl <= current_sl:
                return  # only trail upward
        else:
            new_sl = current_price + risk
            if new_sl >= current_sl:
                return  # only trail downward

        try:
            await self.oanda.modify_trade(trade_id, stop_loss=new_sl)
            pos_state["stop_loss"] = new_sl

            logger.debug(
                "%s: trailing stop updated for %s – SL=%.5f",
                self.name, trade_id, new_sl,
            )
        except Exception:
            logger.exception(
                "%s: failed to update trailing stop for %s", self.name, trade_id,
            )

    # ------------------------------------------------------------------
    # Instrument scanning
    # ------------------------------------------------------------------

    async def _scan_instruments(self):
        """Scan all instruments for swing trade setups."""
        for instrument in self.instruments:
            # Skip if already have a position on this instrument
            if self._has_position_on(instrument):
                continue

            # Check if at max positions (could have opened one earlier in loop)
            open_count = len(self._state.get("open_positions", {}))
            if open_count >= self.max_positions:
                break

            setup = await self.strategy.analyze(
                self.oanda,
                instrument,
                {"min_confluence": self.min_confluence, "min_rr": self.min_rr},
            )

            if setup is not None:
                await self._execute_setup(instrument, setup)

    def _has_position_on(self, instrument: str) -> bool:
        """Check if we already have an open position on this instrument."""
        for pos in self._state.get("open_positions", {}).values():
            if pos.get("instrument") == instrument:
                return True
        return False

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def _execute_setup(self, instrument: str, setup: TradeSetup):
        """Place an OANDA order for a qualified swing trade setup."""
        # Get account balance for position sizing
        try:
            account = await self.oanda.get_account_summary()
            balance = float(account.get("balance", account.get("NAV", 0)))
        except Exception:
            logger.exception("%s: failed to get account summary", self.name)
            return

        if balance <= 0:
            logger.warning("%s: account balance is zero or negative", self.name)
            return

        # Calculate position size
        units = self.strategy.get_position_size(
            account_balance=balance,
            entry=setup.entry_price,
            stop_loss=setup.stop_loss,
            risk_pct=self.max_risk_pct,
        )

        if units <= 0:
            logger.warning("%s: position size is zero for %s", self.name, instrument)
            return

        # Apply direction
        if setup.direction == "short":
            units = -units

        # Risk manager check
        try:
            risk_ok = await self.risk.check_trade(
                bot_name=self.name,
                symbol=instrument,
                side="buy" if setup.direction == "long" else "sell",
                amount=abs(units),
                price=setup.entry_price,
            )
            if not risk_ok:
                logger.info(
                    "%s: risk manager rejected %s trade on %s",
                    self.name, setup.direction, instrument,
                )
                return
        except Exception:
            logger.exception("%s: risk check failed", self.name)
            return

        # Place order via OANDA
        try:
            order_result = await self.oanda.place_order(
                instrument=instrument,
                units=units,
                stop_loss=setup.stop_loss,
                take_profit=setup.take_profit,
            )
        except Exception:
            logger.exception(
                "%s: failed to place order for %s", self.name, instrument,
            )
            return

        trade_id = _extract_trade_id(order_result)
        if trade_id is None:
            logger.warning(
                "%s: order placed but no trade ID returned for %s",
                self.name, instrument,
            )
            return

        # Record position in state
        self._state["open_positions"][trade_id] = {
            "instrument": instrument,
            "direction": setup.direction,
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "original_stop_loss": setup.stop_loss,
            "take_profit": setup.take_profit,
            "units": units,
            "confluence_score": setup.confluence_score,
            "opened_at": time.time(),
            "sl_at_breakeven": False,
            "trailing_stop_active": False,
        }

        # Initialize partial TP tracking
        self._state.setdefault("partial_tp_tracking", {})[trade_id] = {
            "1r_taken": False,
            "2r_taken": False,
        }

        self._state["total_trades"] = self._state.get("total_trades", 0) + 1
        await self._save_state()

        logger.info(
            "%s: opened %s %d units on %s – entry=%.5f SL=%.5f TP=%.5f "
            "score=%.1f partials=%s",
            self.name, setup.direction, abs(units), instrument,
            setup.entry_price, setup.stop_loss, setup.take_profit,
            setup.confluence_score, self.partial_tp_levels,
        )

        await self.publisher.publish(self.name, "trade_opened", {
            "trade_id": trade_id,
            "instrument": instrument,
            "direction": setup.direction,
            "units": units,
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "take_profit": setup.take_profit,
            "confluence_score": setup.confluence_score,
            "partial_tp_levels": setup.components.get("partial_tp_prices", []),
        })


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------

def _build_broker_map(broker_positions) -> Dict[str, Any]:
    """Build a lookup dict of broker positions keyed by trade ID."""
    broker_map: Dict[str, Any] = {}
    if isinstance(broker_positions, list):
        for pos in broker_positions:
            trade_id = str(pos.get("id", pos.get("trade_id", "")))
            if trade_id:
                broker_map[trade_id] = pos
    elif isinstance(broker_positions, dict):
        for trade_id, pos in broker_positions.items():
            broker_map[str(trade_id)] = pos
    return broker_map


def _extract_trade_id(order_result) -> Optional[str]:
    """Best-effort extraction of trade ID from an OANDA order response."""
    if isinstance(order_result, dict):
        fill = order_result.get("orderFillTransaction", {})
        if isinstance(fill, dict):
            trade_id = fill.get("tradeOpened", {}).get("tradeID")
            if trade_id:
                return str(trade_id)

        for key in ("trade_id", "tradeID", "id"):
            val = order_result.get(key)
            if val is not None:
                return str(val)
    return None


def _extract_current_price(broker_pos) -> Optional[float]:
    """Extract the current/unrealised price from a broker position dict."""
    if isinstance(broker_pos, dict):
        for key in ("currentPrice", "current_price", "price"):
            val = broker_pos.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None
