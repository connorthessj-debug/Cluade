"""Arbitrage trade execution and balance rebalancing.

Places simultaneous buy/sell orders on two exchanges, records slippage
and actual vs expected profit, and provides a rebalance recommendation
when balances become too skewed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from bots.arbitrage.fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class ArbitrageExecutor:
    """Execute cross-exchange arbitrage trades.

    Parameters
    ----------
    exchange_manager : object
        Provides ``place_order(exchange, symbol, side, amount, price)``
        and ``get_balances(exchange)`` async methods.
    fee_calculator : FeeCalculator
        For computing expected vs actual profit.
    """

    def __init__(self, exchange_manager, fee_calculator: FeeCalculator):
        self.exchange_manager = exchange_manager
        self.fee_calc = fee_calculator

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    async def execute_arbitrage(self, opportunity: Dict[str, Any], amount: float) -> Dict[str, Any]:
        """Execute the buy and sell legs simultaneously.

        Parameters
        ----------
        opportunity : dict
            As returned by :meth:`SpreadMonitor.get_best_opportunity`.
            Must contain ``pair``, ``buy_exchange``, ``sell_exchange``,
            ``buy_price``, ``sell_price``.
        amount : float
            Trade size in base-currency units.

        Returns
        -------
        dict
            Execution report with keys:
            ``success, buy_fill, sell_fill, expected_profit, actual_profit,
            buy_slippage, sell_slippage, execution_time_ms, timestamp``.
        """
        pair = opportunity["pair"]
        buy_ex = opportunity["buy_exchange"]
        sell_ex = opportunity["sell_exchange"]
        expected_buy = opportunity["buy_price"]
        expected_sell = opportunity["sell_price"]

        expected_profit = self.fee_calc.calculate_net_profit(
            buy_ex, sell_ex, expected_buy, expected_sell, amount,
        )

        t0 = time.monotonic()

        try:
            buy_result, sell_result = await asyncio.gather(
                self.exchange_manager.place_order(
                    buy_ex, pair, "buy", amount, expected_buy,
                ),
                self.exchange_manager.place_order(
                    sell_ex, pair, "sell", amount, expected_sell,
                ),
            )
        except Exception:
            logger.exception("Arbitrage execution failed for %s", pair)
            return {
                "success": False,
                "pair": pair,
                "buy_exchange": buy_ex,
                "sell_exchange": sell_ex,
                "error": "order_placement_failed",
                "timestamp": time.time(),
            }

        elapsed_ms = (time.monotonic() - t0) * 1000

        # Extract fill prices – adapt to whatever the exchange manager returns.
        buy_fill = self._extract_fill_price(buy_result, fallback=expected_buy)
        sell_fill = self._extract_fill_price(sell_result, fallback=expected_sell)

        actual_profit = self.fee_calc.calculate_net_profit(
            buy_ex, sell_ex, buy_fill, sell_fill, amount,
        )

        buy_slippage = buy_fill - expected_buy
        sell_slippage = expected_sell - sell_fill

        result = {
            "success": True,
            "pair": pair,
            "buy_exchange": buy_ex,
            "sell_exchange": sell_ex,
            "amount": amount,
            "buy_fill": buy_fill,
            "sell_fill": sell_fill,
            "expected_profit": expected_profit,
            "actual_profit": actual_profit,
            "buy_slippage": buy_slippage,
            "sell_slippage": sell_slippage,
            "execution_time_ms": elapsed_ms,
            "timestamp": time.time(),
        }

        logger.info(
            "Arbitrage executed: %s buy@%.6f sell@%.6f net=%.6f (expected %.6f) in %.0fms",
            pair,
            buy_fill,
            sell_fill,
            actual_profit,
            expected_profit,
            elapsed_ms,
        )

        return result

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    async def rebalance_check(self, exchange_manager=None) -> Dict[str, Any]:
        """Check whether balances are too skewed between exchanges.

        A simple heuristic: if one exchange holds less than 30 % of the
        total across both exchanges for any tracked asset, a rebalance is
        recommended.

        Parameters
        ----------
        exchange_manager : object, optional
            Falls back to ``self.exchange_manager`` when not given.

        Returns
        -------
        dict
            ``{needs_rebalance: bool, recommendations: [...]}``
        """
        em = exchange_manager or self.exchange_manager
        exchanges = (
            list(em.exchanges.keys())
            if hasattr(em, "exchanges")
            else em.get_exchange_names()
        )

        if len(exchanges) < 2:
            return {"needs_rebalance": False, "recommendations": []}

        try:
            balances = {}
            for ex in exchanges:
                balances[ex] = await em.get_balances(ex)
        except Exception:
            logger.warning("Could not fetch balances for rebalance check", exc_info=True)
            return {"needs_rebalance": False, "recommendations": []}

        recommendations = []
        threshold = 0.30  # minimum share per exchange

        # Collect all assets present on either exchange.
        all_assets: set = set()
        for bal in balances.values():
            if isinstance(bal, dict):
                all_assets.update(bal.keys())

        for asset in all_assets:
            amounts = {
                ex: (balances[ex].get(asset, 0.0) if isinstance(balances[ex], dict) else 0.0)
                for ex in exchanges
            }
            total = sum(amounts.values())
            if total <= 0:
                continue

            for ex, amt in amounts.items():
                share = amt / total
                if share < threshold:
                    deficit = (0.5 * total) - amt  # target 50/50
                    other_ex = [e for e in exchanges if e != ex][0]
                    recommendations.append(
                        {
                            "asset": asset,
                            "from_exchange": other_ex,
                            "to_exchange": ex,
                            "suggested_amount": round(deficit, 6),
                            "current_share": round(share, 4),
                        }
                    )

        return {
            "needs_rebalance": len(recommendations) > 0,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_fill_price(order_result, fallback: float) -> float:
        """Best-effort extraction of the average fill price from an order result."""
        if isinstance(order_result, dict):
            for key in ("average", "avg_price", "price", "fill_price"):
                val = order_result.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
        return fallback
