"""Scalper bot for OANDA forex using ICT/SMC methodology.

Scans configurable instruments on short timeframes, looking for high-
confluence setups aligned with higher-timeframe bias. Manages up to 3
concurrent positions with breakeven stop-loss management after 1R profit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from bots.base_bot import BaseBot
from bots.scalper.strategy import ScalperStrategy
from core.models import TradeSetup

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5  # seconds between main loop iterations


class ScalperBot(BaseBot):
    """ICT/SMC-based forex scalper operating on OANDA.

    Parameters
    ----------
    config : Config
        System configuration (must include ``scalper`` and ``oanda`` sections).
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
        super().__init__("scalper", config, database, risk_manager, publisher)
        self.oanda = oanda_client

        scalper_cfg = config.scalper
        self.instruments: List[str] = config.oanda.instruments
        self.min_confluence: int = scalper_cfg.min_confluence
        self.max_risk_pct: float = scalper_cfg.max_risk_pct / 100.0  # convert to fraction
        self.min_rr: float = scalper_cfg.min_rr
        self.max_positions: int = scalper_cfg.max_positions
        self.cooldown_seconds: int = scalper_cfg.cooldown_seconds

        self.strategy = ScalperStrategy(
            min_confluence=self.min_confluence,
            min_rr=self.min_rr,
        )

        self._ensure_state_defaults()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _ensure_state_defaults(self):
        """Populate state with defaults if resuming from empty state."""
        self._state.setdefault("open_positions", {})
        self._state.setdefault("active_signals", {})
        self._state.setdefault("scan_index", 0)
        self._state.setdefault("total_trades", 0)
        self._state.setdefault("last_trade_times", {})

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main scalper loop: manage positions, scan instruments, place orders."""
        logger.info(
            "%s: starting – instruments=%s, max_positions=%d, cooldown=%ds",
            self.name, self.instruments, self.max_positions, self.cooldown_seconds,
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
        """Single iteration: manage existing positions, scan for new setups."""
        # Step 1: manage existing positions
        await self._manage_positions()

        # Step 2: scan instruments for new setups
        open_count = len(self._state.get("open_positions", {}))
        if open_count >= self.max_positions:
            logger.debug("%s: at max positions (%d), skipping scan", self.name, open_count)
            return

        await self._scan_instruments()

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    async def _manage_positions(self):
        """Check open positions and manage SL/TP."""
        open_positions = self._state.get("open_positions", {})
        if not open_positions:
            return

        try:
            broker_positions = await self.oanda.get_open_positions()
        except Exception:
            logger.exception("%s: failed to fetch open positions", self.name)
            return

        # Build lookup of broker positions by trade ID
        broker_map: Dict[str, Any] = {}
        if isinstance(broker_positions, list):
            for pos in broker_positions:
                trade_id = str(pos.get("id", pos.get("trade_id", "")))
                if trade_id:
                    broker_map[trade_id] = pos
        elif isinstance(broker_positions, dict):
            for trade_id, pos in broker_positions.items():
                broker_map[str(trade_id)] = pos

        closed_ids: List[str] = []

        for trade_id, pos_state in list(open_positions.items()):
            broker_pos = broker_map.get(trade_id)

            if broker_pos is None:
                # Position no longer open at broker – record closure
                logger.info(
                    "%s: position %s no longer open, removing from state",
                    self.name, trade_id,
                )
                closed_ids.append(trade_id)
                continue

            # Move SL to breakeven after 1R profit
            await self._check_breakeven(trade_id, pos_state, broker_pos)

        # Clean up closed positions from state
        for trade_id in closed_ids:
            open_positions.pop(trade_id, None)
            await self.publisher.publish(self.name, "position_closed", {
                "trade_id": trade_id,
            })

        if closed_ids:
            await self._save_state()

    async def _check_breakeven(
        self,
        trade_id: str,
        pos_state: Dict[str, Any],
        broker_pos: Any,
    ):
        """Move stop-loss to breakeven after 1R profit is reached."""
        if pos_state.get("sl_at_breakeven"):
            return

        entry_price = pos_state.get("entry_price", 0.0)
        stop_loss = pos_state.get("stop_loss", 0.0)
        direction = pos_state.get("direction", "long")

        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return

        # Get current price from broker position
        current_price = _extract_current_price(broker_pos)
        if current_price is None:
            return

        # Check if 1R profit has been achieved
        if direction == "long":
            unrealised = current_price - entry_price
        else:
            unrealised = entry_price - current_price

        if unrealised >= risk:
            # Move SL to breakeven (entry price + small buffer)
            buffer = risk * 0.05  # 5% of risk as buffer
            if direction == "long":
                new_sl = entry_price + buffer
            else:
                new_sl = entry_price - buffer

            try:
                await self.oanda.modify_trade(trade_id, stop_loss=new_sl)
                pos_state["sl_at_breakeven"] = True
                pos_state["stop_loss"] = new_sl
                await self._save_state()

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
                    "%s: failed to modify SL for %s", self.name, trade_id,
                )

    # ------------------------------------------------------------------
    # Instrument scanning
    # ------------------------------------------------------------------

    async def _scan_instruments(self):
        """Scan instruments round-robin for trade setups."""
        scan_index = self._state.get("scan_index", 0)
        now = time.time()

        for i in range(len(self.instruments)):
            idx = (scan_index + i) % len(self.instruments)
            instrument = self.instruments[idx]

            # Cooldown check – skip if we recently traded this instrument
            last_trade = self._state.get("last_trade_times", {}).get(instrument, 0)
            if now - last_trade < self.cooldown_seconds:
                continue

            # Skip if already have a position on this instrument
            if self._has_position_on(instrument):
                continue

            setup = await self.strategy.analyze(
                self.oanda,
                instrument,
                {"min_confluence": self.min_confluence, "min_rr": self.min_rr},
            )

            if setup is not None:
                await self._execute_setup(instrument, setup)

                # Update scan index to resume after this instrument next time
                self._state["scan_index"] = (idx + 1) % len(self.instruments)
                await self._save_state()

                # Only open one position per tick to avoid over-exposure
                return

        # Advance scan index for next tick
        self._state["scan_index"] = (scan_index + 1) % len(self.instruments)

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
        """Place an OANDA order for a qualified trade setup."""
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

        # Apply direction (negative units for sell)
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
                logger.info("%s: risk manager rejected %s trade on %s", self.name, setup.direction, instrument)
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

        # Extract trade ID from result
        trade_id = _extract_trade_id(order_result)
        if trade_id is None:
            logger.warning(
                "%s: order placed but no trade ID returned for %s",
                self.name, instrument,
            )
            return

        # Record in state
        self._state["open_positions"][trade_id] = {
            "instrument": instrument,
            "direction": setup.direction,
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "take_profit": setup.take_profit,
            "units": units,
            "confluence_score": setup.confluence_score,
            "opened_at": time.time(),
            "sl_at_breakeven": False,
        }

        self._state["total_trades"] = self._state.get("total_trades", 0) + 1
        self._state.setdefault("last_trade_times", {})[instrument] = time.time()

        await self._save_state()

        logger.info(
            "%s: opened %s %d units on %s – entry=%.5f SL=%.5f TP=%.5f score=%.1f",
            self.name, setup.direction, abs(units), instrument,
            setup.entry_price, setup.stop_loss, setup.take_profit,
            setup.confluence_score,
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
        })


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------

def _extract_trade_id(order_result) -> Optional[str]:
    """Best-effort extraction of trade ID from an OANDA order response."""
    if isinstance(order_result, dict):
        # Standard OANDA response nesting
        fill = order_result.get("orderFillTransaction", {})
        if isinstance(fill, dict):
            trade_ids = fill.get("tradeOpened", {}).get("tradeID")
            if trade_ids:
                return str(trade_ids)

        # Simpler structures
        for key in ("trade_id", "tradeID", "id"):
            val = order_result.get(key)
            if val is not None:
                return str(val)
    return None


def _extract_current_price(broker_pos) -> Optional[float]:
    """Extract the current/unrealised price from a broker position dict."""
    if isinstance(broker_pos, dict):
        for key in ("currentPrice", "current_price", "price", "unrealizedPL"):
            val = broker_pos.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None
