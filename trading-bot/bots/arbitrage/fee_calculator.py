"""Fee calculation for cross-exchange arbitrage.

Stores maker/taker fee schedules for supported exchanges and provides
helpers to compute net profit after fees and the minimum spread required
for a profitable round-trip.
"""

from __future__ import annotations

import logging
from typing import Dict, Literal

logger = logging.getLogger(__name__)

# Default fee schedules (fraction, *not* percent).
# Override at runtime via the constructor if needed.
_DEFAULT_FEE_SCHEDULES: Dict[str, Dict[str, float]] = {
    "binance": {
        "maker": 0.001,   # 0.10 %
        "taker": 0.001,   # 0.10 %
    },
    "coinbase": {
        "maker": 0.004,   # 0.40 %
        "taker": 0.006,   # 0.60 %
    },
}


class FeeCalculator:
    """Calculate trading fees and net profit for arbitrage opportunities.

    Parameters
    ----------
    fee_schedules : dict, optional
        Mapping of ``{exchange: {maker: float, taker: float}}``.
        Falls back to built-in defaults for Binance and Coinbase.
    """

    def __init__(self, fee_schedules: Dict[str, Dict[str, float]] | None = None):
        self.fees: Dict[str, Dict[str, float]] = dict(_DEFAULT_FEE_SCHEDULES)
        if fee_schedules:
            self.fees.update(fee_schedules)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def calculate_fees(
        self,
        exchange: str,
        side: Literal["maker", "taker"],
        amount: float,
        price: float,
    ) -> float:
        """Return the absolute fee for a single order.

        Parameters
        ----------
        exchange : str
            Exchange name (lower-case, e.g. ``"binance"``).
        side : ``"maker"`` or ``"taker"``
            Whether the order sits on the book or crosses the spread.
        amount : float
            Trade size in base-currency units.
        price : float
            Execution price per unit.

        Returns
        -------
        float
            Fee in quote-currency terms.
        """
        exchange = exchange.lower()
        schedule = self.fees.get(exchange)
        if schedule is None:
            logger.warning("No fee schedule for exchange %s – assuming 0.1%%", exchange)
            rate = 0.001
        else:
            rate = schedule.get(side, schedule.get("taker", 0.001))

        notional = amount * price
        return notional * rate

    def calculate_net_profit(
        self,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: float,
        sell_price: float,
        amount: float,
    ) -> float:
        """Compute net profit of buying on one exchange and selling on another.

        Both legs are assumed to be **taker** orders (market / IOC).

        Returns
        -------
        float
            Net profit in quote currency after fees on both sides.
        """
        gross = (sell_price - buy_price) * amount
        buy_fee = self.calculate_fees(buy_exchange, "taker", amount, buy_price)
        sell_fee = self.calculate_fees(sell_exchange, "taker", amount, sell_price)
        net = gross - buy_fee - sell_fee
        return net

    def get_min_profitable_spread(
        self,
        buy_exchange: str,
        sell_exchange: str,
    ) -> float:
        """Return the minimum spread (as a fraction) to break even after fees.

        Spread is defined as ``(sell_price - buy_price) / buy_price``.

        Both legs are assumed to be taker orders.

        Returns
        -------
        float
            Minimum spread fraction (e.g. ``0.007`` means 0.7 %).
        """
        buy_rate = self._taker_rate(buy_exchange)
        sell_rate = self._taker_rate(sell_exchange)
        # Break-even: spread >= buy_fee_rate + sell_fee_rate
        return buy_rate + sell_rate

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _taker_rate(self, exchange: str) -> float:
        exchange = exchange.lower()
        schedule = self.fees.get(exchange)
        if schedule is None:
            return 0.001
        return schedule.get("taker", 0.001)
