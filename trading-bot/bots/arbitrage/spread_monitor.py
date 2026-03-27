"""Real-time spread monitoring across two exchanges.

Fetches top-of-book from both exchanges for a list of stablecoin pairs and
identifies arbitrage opportunities where one exchange's bid exceeds the
other's ask.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from bots.arbitrage.fee_calculator import FeeCalculator

logger = logging.getLogger(__name__)


class SpreadMonitor:
    """Monitor bid/ask spreads between two exchanges for arbitrage.

    Parameters
    ----------
    exchange_manager : object
        Provides ``get_order_book(exchange, symbol)`` returning an
        :class:`core.models.OrderBook` (or equivalent with ``.bids`` /
        ``.asks`` lists of ``(price, amount)`` tuples).
    pairs : list[str]
        Symbols to monitor, e.g. ``['USDC/USDT', 'USDC/USD', 'USDT/USD']``.
    fee_calculator : FeeCalculator, optional
        Used to determine net profitability.  A default instance is created
        when omitted.
    """

    def __init__(
        self,
        exchange_manager,
        pairs: List[str],
        fee_calculator: FeeCalculator | None = None,
    ):
        self.exchange_manager = exchange_manager
        self.pairs = pairs
        self.fee_calc = fee_calculator or FeeCalculator()
        self._last_spreads: List[Dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_spreads(self) -> List[Dict]:
        """Fetch order-book tops from both exchanges for every pair.

        For each pair the method checks both directions:
        * Buy on exchange A, sell on exchange B
        * Buy on exchange B, sell on exchange A

        Returns
        -------
        list[dict]
            Each dict contains:
            ``pair, buy_exchange, sell_exchange, buy_price, sell_price,
            spread, spread_pct, timestamp``.
        """
        exchanges = list(self.exchange_manager.exchanges.keys()) if hasattr(
            self.exchange_manager, "exchanges"
        ) else self.exchange_manager.get_exchange_names()

        if len(exchanges) < 2:
            logger.error("Need at least 2 exchanges; got %s", exchanges)
            return []

        ex_a, ex_b = exchanges[0], exchanges[1]

        # Fetch all order books concurrently.
        tasks = []
        fetch_map = []  # keep track of (exchange, pair) per task
        for pair in self.pairs:
            for ex in (ex_a, ex_b):
                tasks.append(self._safe_fetch_book(ex, pair))
                fetch_map.append((ex, pair))

        results = await asyncio.gather(*tasks)

        # Organise results by (exchange, pair).
        books: Dict[tuple, object] = {}
        for (ex, pair), book in zip(fetch_map, results):
            if book is not None:
                books[(ex, pair)] = book

        spreads: List[Dict] = []
        now = time.time()

        for pair in self.pairs:
            book_a = books.get((ex_a, pair))
            book_b = books.get((ex_b, pair))

            if book_a is None or book_b is None:
                continue

            # Direction 1: buy on A (best ask), sell on B (best bid)
            ask_a = self._best_ask(book_a)
            bid_b = self._best_bid(book_b)
            if ask_a and bid_b and bid_b > ask_a:
                spread = bid_b - ask_a
                spreads.append(
                    {
                        "pair": pair,
                        "buy_exchange": ex_a,
                        "sell_exchange": ex_b,
                        "buy_price": ask_a,
                        "sell_price": bid_b,
                        "spread": spread,
                        "spread_pct": (spread / ask_a) * 100,
                        "timestamp": now,
                    }
                )

            # Direction 2: buy on B (best ask), sell on A (best bid)
            ask_b = self._best_ask(book_b)
            bid_a = self._best_bid(book_a)
            if ask_b and bid_a and bid_a > ask_b:
                spread = bid_a - ask_b
                spreads.append(
                    {
                        "pair": pair,
                        "buy_exchange": ex_b,
                        "sell_exchange": ex_a,
                        "buy_price": ask_b,
                        "sell_price": bid_a,
                        "spread": spread,
                        "spread_pct": (spread / ask_b) * 100,
                        "timestamp": now,
                    }
                )

        self._last_spreads = spreads
        return spreads

    def get_best_opportunity(self) -> Optional[Dict]:
        """Return the spread with the highest net profit potential.

        Uses :pyclass:`FeeCalculator` to rank by *net* profit rather than
        raw spread so that fee asymmetry between exchanges is accounted for.

        Returns ``None`` when no profitable opportunity exists.
        """
        if not self._last_spreads:
            return None

        best: Optional[Dict] = None
        best_net = 0.0

        for s in self._last_spreads:
            # Use a nominal 1-unit amount to compare relative profitability.
            net = self.fee_calc.calculate_net_profit(
                buy_exchange=s["buy_exchange"],
                sell_exchange=s["sell_exchange"],
                buy_price=s["buy_price"],
                sell_price=s["sell_price"],
                amount=1.0,
            )
            if net > best_net:
                best_net = net
                best = {**s, "net_profit_per_unit": net}

        return best

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _safe_fetch_book(self, exchange: str, pair: str):
        """Fetch an order book, returning ``None`` on failure."""
        try:
            return await self.exchange_manager.get_order_book(exchange, pair)
        except Exception:
            logger.warning("Failed to fetch order book for %s on %s", pair, exchange, exc_info=True)
            return None

    @staticmethod
    def _best_bid(book) -> Optional[float]:
        if book.bids:
            return book.bids[0][0]
        return None

    @staticmethod
    def _best_ask(book) -> Optional[float]:
        if book.asks:
            return book.asks[0][0]
        return None
