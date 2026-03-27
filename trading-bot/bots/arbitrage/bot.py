"""Crypto arbitrage bot for stablecoin pairs across Binance and Coinbase.

Continuously monitors bid/ask spreads between two exchanges and executes
simultaneous buy/sell orders when a profitable spread exceeds the minimum
threshold after fees.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from bots.base_bot import BaseBot
from bots.arbitrage.fee_calculator import FeeCalculator
from bots.arbitrage.spread_monitor import SpreadMonitor
from bots.arbitrage.execution import ArbitrageExecutor

logger = logging.getLogger(__name__)


class ArbitrageBot(BaseBot):
    """Stablecoin arbitrage bot operating across two crypto exchanges.

    Parameters
    ----------
    config : Config
        System configuration (must include ``arbitrage`` section).
    database : object
        Database adapter for state persistence.
    risk_manager : object
        Pre-trade risk checks.
    publisher : object
        Event publisher for status and trade notifications.
    exchange_manager : object
        Provides order book fetching, order placement, and balance queries.
    """

    def __init__(self, config, database, risk_manager, publisher, exchange_manager):
        super().__init__("arbitrage", config, database, risk_manager, publisher)
        self.exchange_manager = exchange_manager

        arb_cfg = config.arbitrage
        self.pairs = arb_cfg.pairs
        self.min_spread = arb_cfg.min_spread
        self.poll_interval = arb_cfg.poll_interval
        self.max_position = arb_cfg.max_position

        self.fee_calc = FeeCalculator()
        self.spread_monitor = SpreadMonitor(exchange_manager, self.pairs, self.fee_calc)
        self.executor = ArbitrageExecutor(exchange_manager, self.fee_calc)

        # Running statistics (persisted in _state)
        self._ensure_state_defaults()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _ensure_state_defaults(self):
        """Populate state keys with defaults if not already present."""
        self._state.setdefault("total_trades", 0)
        self._state.setdefault("total_profit", 0.0)
        self._state.setdefault("total_spread_captured", 0.0)
        self._state.setdefault("last_execution_time", None)

    @property
    def total_trades(self) -> int:
        return self._state.get("total_trades", 0)

    @property
    def total_profit(self) -> float:
        return self._state.get("total_profit", 0.0)

    @property
    def avg_spread_captured(self) -> float:
        trades = self.total_trades
        if trades == 0:
            return 0.0
        return self._state.get("total_spread_captured", 0.0) / trades

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main arbitrage loop: poll spreads, evaluate, execute."""
        logger.info(
            "%s: entering main loop – pairs=%s, min_spread=%.4f, interval=%.1fs",
            self.name, self.pairs, self.min_spread, self.poll_interval,
        )
        self._ensure_state_defaults()

        rebalance_counter = 0

        while self.running:
            try:
                await self.on_tick()
            except Exception:
                logger.exception("%s: error in on_tick", self.name)

            # Periodic rebalance check (every 60 ticks)
            rebalance_counter += 1
            if rebalance_counter >= 60:
                rebalance_counter = 0
                await self._check_rebalance()

            # Heartbeat every tick
            await self._heartbeat()

            await asyncio.sleep(self.poll_interval)

    async def on_tick(self):
        """Single iteration: fetch spreads, find opportunity, execute."""
        spreads = await self.spread_monitor.fetch_spreads()

        if not spreads:
            return

        opportunity = self.spread_monitor.get_best_opportunity()
        if opportunity is None:
            return

        # Check if the spread exceeds our minimum threshold
        spread_pct = opportunity.get("spread_pct", 0.0) / 100.0  # convert to fraction
        min_profitable = self.fee_calc.get_min_profitable_spread(
            opportunity["buy_exchange"], opportunity["sell_exchange"],
        )

        if spread_pct < max(self.min_spread, min_profitable):
            logger.debug(
                "%s: spread %.6f below threshold %.6f for %s",
                self.name, spread_pct, max(self.min_spread, min_profitable),
                opportunity["pair"],
            )
            return

        # Determine trade size
        net_per_unit = opportunity.get("net_profit_per_unit", 0.0)
        if net_per_unit <= 0:
            return

        amount = min(self.max_position, self._available_amount(opportunity))
        if amount <= 0:
            logger.warning("%s: computed amount is zero, skipping", self.name)
            return

        # Risk manager check
        risk_ok = await self._check_risk(opportunity, amount)
        if not risk_ok:
            logger.info("%s: risk manager rejected trade", self.name)
            return

        # Execute
        logger.info(
            "%s: executing arbitrage on %s – buy@%.6f(%s) sell@%.6f(%s) amount=%.2f",
            self.name,
            opportunity["pair"],
            opportunity["buy_price"],
            opportunity["buy_exchange"],
            opportunity["sell_price"],
            opportunity["sell_exchange"],
            amount,
        )

        result = await self.executor.execute_arbitrage(opportunity, amount)

        if result.get("success"):
            await self._record_trade(result)
        else:
            logger.warning("%s: execution failed – %s", self.name, result.get("error"))
            await self.publisher.publish(
                self.name, "trade_failed", {"result": result},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _available_amount(self, opportunity: Dict[str, Any]) -> float:
        """Determine trade size capped by max_position.

        For stablecoin pairs the amount is essentially in USD terms, so
        ``max_position`` directly limits the notional.
        """
        return self.max_position

    async def _check_risk(self, opportunity: Dict[str, Any], amount: float) -> bool:
        """Ask the risk manager whether this trade is allowed."""
        try:
            return await self.risk.check_trade(
                bot_name=self.name,
                symbol=opportunity["pair"],
                side="buy",
                amount=amount,
                price=opportunity["buy_price"],
            )
        except Exception:
            logger.exception("%s: risk check raised an exception", self.name)
            return False

    async def _record_trade(self, result: Dict[str, Any]):
        """Update running statistics and publish the trade event."""
        self._state["total_trades"] = self._state.get("total_trades", 0) + 1
        self._state["total_profit"] = (
            self._state.get("total_profit", 0.0) + result.get("actual_profit", 0.0)
        )
        spread_captured = abs(result.get("sell_fill", 0) - result.get("buy_fill", 0))
        self._state["total_spread_captured"] = (
            self._state.get("total_spread_captured", 0.0) + spread_captured
        )
        self._state["last_execution_time"] = result.get("timestamp")

        await self._save_state()

        await self.publisher.publish(self.name, "trade_executed", {
            "pair": result.get("pair"),
            "buy_exchange": result.get("buy_exchange"),
            "sell_exchange": result.get("sell_exchange"),
            "buy_fill": result.get("buy_fill"),
            "sell_fill": result.get("sell_fill"),
            "actual_profit": result.get("actual_profit"),
            "expected_profit": result.get("expected_profit"),
            "execution_time_ms": result.get("execution_time_ms"),
            "running_total_profit": self.total_profit,
            "total_trades": self.total_trades,
        })

        logger.info(
            "%s: trade #%d – P&L=%.6f, running total=%.6f, avg spread=%.6f",
            self.name,
            self.total_trades,
            result.get("actual_profit", 0.0),
            self.total_profit,
            self.avg_spread_captured,
        )

    async def _check_rebalance(self):
        """Periodic rebalance check between exchanges."""
        try:
            rebalance = await self.executor.rebalance_check()
            if rebalance.get("needs_rebalance"):
                logger.warning(
                    "%s: rebalance recommended – %s",
                    self.name, rebalance["recommendations"],
                )
                await self.publisher.publish(
                    self.name, "rebalance_needed", rebalance,
                )
        except Exception:
            logger.exception("%s: rebalance check failed", self.name)
