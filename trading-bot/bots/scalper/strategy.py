"""Scalper strategy using Smart Money Concepts (ICT methodology).

Multi-timeframe analysis:
  H1  -> overall market bias (BOS/CHoCH structure)
  M15 -> order block and structure identification aligned with H1 bias
  M5  -> detect price entering a M15 order block zone
  M1  -> CHoCH confirmation for precise entry timing

Only takes longs in discount zones and shorts in premium zones.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from smc.market_structure import detect_swing_points, detect_bos, detect_choch, get_trend
from smc.order_blocks import find_order_blocks, is_price_in_ob
from smc.fibonacci import is_in_premium, is_in_discount, get_fib_levels
from smc.confluence import score_setup, calculate_sl_tp
from core.models import OHLCV, TradeSetup, SwingPoint

logger = logging.getLogger(__name__)


class ScalperStrategy:
    """ICT-based scalping strategy with multi-timeframe confluence.

    Parameters
    ----------
    min_confluence : int
        Minimum confluence score (0-100) required to generate a setup.
    min_rr : float
        Minimum reward-to-risk ratio for a valid setup.
    """

    def __init__(self, min_confluence: int = 60, min_rr: float = 2.0):
        self.min_confluence = min_confluence
        self.min_rr = min_rr

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    async def analyze(
        self,
        oanda_client,
        instrument: str,
        config: Dict[str, Any],
    ) -> Optional[TradeSetup]:
        """Run multi-timeframe SMC analysis and return a trade setup if found.

        Parameters
        ----------
        oanda_client : OandaClient
            OANDA API client with ``get_candles(instrument, granularity, count)``
            returning a list of :class:`core.models.OHLCV`.
        instrument : str
            OANDA instrument name (e.g. ``'EUR_USD'``).
        config : dict
            Strategy parameters (timeframes, thresholds, etc.).

        Returns
        -------
        TradeSetup or None
            A fully qualified trade setup if all confluence criteria are met.
        """
        try:
            return await self._run_analysis(oanda_client, instrument, config)
        except Exception:
            logger.exception("ScalperStrategy: analysis failed for %s", instrument)
            return None

    async def _run_analysis(
        self,
        oanda_client,
        instrument: str,
        config: Dict[str, Any],
    ) -> Optional[TradeSetup]:
        # ----------------------------------------------------------
        # Step 1: H1 – determine overall bias
        # ----------------------------------------------------------
        h1_candles = await oanda_client.get_candles(instrument, "H1", 50)
        if not h1_candles or len(h1_candles) < 20:
            logger.debug("ScalperStrategy: insufficient H1 data for %s", instrument)
            return None

        h1_swings = detect_swing_points(h1_candles, lookback=3)
        h1_trend = get_trend(h1_swings)

        if h1_trend == "ranging":
            logger.debug("ScalperStrategy: H1 trend is ranging for %s, skipping", instrument)
            return None

        h1_bos = detect_bos(h1_candles, h1_swings)
        h1_choch = detect_choch(h1_candles, h1_swings)

        logger.debug(
            "ScalperStrategy: %s H1 trend=%s, BOS=%d, CHoCH=%d",
            instrument, h1_trend, len(h1_bos), len(h1_choch),
        )

        # ----------------------------------------------------------
        # Step 2: M15 – find OBs and structure aligned with H1 bias
        # ----------------------------------------------------------
        m15_candles = await oanda_client.get_candles(instrument, "M15", 100)
        if not m15_candles or len(m15_candles) < 30:
            return None

        m15_swings = detect_swing_points(m15_candles, lookback=3)
        m15_trend = get_trend(m15_swings)
        m15_obs = find_order_blocks(m15_candles, m15_swings)

        # Filter OBs aligned with H1 bias
        if h1_trend == "bullish":
            aligned_obs = [ob for ob in m15_obs if ob.type == "bullish" and not ob.mitigated]
        else:
            aligned_obs = [ob for ob in m15_obs if ob.type == "bearish" and not ob.mitigated]

        if not aligned_obs:
            logger.debug("ScalperStrategy: no aligned M15 OBs for %s", instrument)
            return None

        # ----------------------------------------------------------
        # Step 3: M5 – check if price is entering an M15 OB zone
        # ----------------------------------------------------------
        m5_candles = await oanda_client.get_candles(instrument, "M5", 50)
        if not m5_candles or len(m5_candles) < 10:
            return None

        current_price = m5_candles[-1].close

        # Find the nearest unmitigated OB that price is currently in
        active_ob = None
        for ob in reversed(aligned_obs):
            if is_price_in_ob(current_price, ob):
                active_ob = ob
                break

        if active_ob is None:
            logger.debug(
                "ScalperStrategy: price %.5f not in any M15 OB for %s",
                current_price, instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 4: M1 – look for CHoCH confirmation
        # ----------------------------------------------------------
        m1_candles = await oanda_client.get_candles(instrument, "M1", 30)
        if not m1_candles or len(m1_candles) < 15:
            return None

        m1_swings = detect_swing_points(m1_candles, lookback=2)
        m1_choch = detect_choch(m1_candles, m1_swings)

        # We need a CHoCH in the direction of our bias
        confirming_choch = [
            c for c in m1_choch if c["type"] == h1_trend
        ]

        if not confirming_choch:
            logger.debug(
                "ScalperStrategy: no M1 CHoCH confirmation for %s", instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 5: Premium/discount zone check and confluence scoring
        # ----------------------------------------------------------
        m15_highs = [sp for sp in m15_swings if sp.type == "high"]
        m15_lows = [sp for sp in m15_swings if sp.type == "low"]

        if not m15_highs or not m15_lows:
            return None

        swing_high = max(sp.price for sp in m15_highs)
        swing_low = min(sp.price for sp in m15_lows)

        # Enforce premium/discount zones
        if h1_trend == "bullish":
            if not is_in_discount(current_price, swing_high, swing_low):
                logger.debug(
                    "ScalperStrategy: price not in discount zone for long on %s",
                    instrument,
                )
                return None
        else:
            if not is_in_premium(current_price, swing_high, swing_low):
                logger.debug(
                    "ScalperStrategy: price not in premium zone for short on %s",
                    instrument,
                )
                return None

        # Build confluence components
        components = {
            "h1_trend": h1_trend,
            "m15_trend": m15_trend,
            "m15_ob": {"type": active_ob.type, "high": active_ob.high, "low": active_ob.low},
            "m1_choch_count": len(confirming_choch),
            "h1_bos_count": len(h1_bos),
            "h1_choch_count": len(h1_choch),
        }

        confluence_score = score_setup(
            candles=m15_candles,
            swing_points=m15_swings,
            order_blocks=m15_obs,
        )

        if confluence_score < self.min_confluence:
            logger.debug(
                "ScalperStrategy: confluence %.1f below threshold %d for %s",
                confluence_score, self.min_confluence, instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 6: Calculate entry, SL, TP
        # ----------------------------------------------------------
        direction = "long" if h1_trend == "bullish" else "short"

        sl_tp = calculate_sl_tp(
            direction=direction,
            entry_price=current_price,
            swing_points=m15_swings,
            order_blocks=aligned_obs,
        )

        entry_price = current_price
        stop_loss = sl_tp.get("stop_loss", 0.0)
        take_profit = sl_tp.get("take_profit", 0.0)

        # Validate R:R ratio
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return None

        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk

        if rr_ratio < self.min_rr:
            logger.debug(
                "ScalperStrategy: R:R %.2f below minimum %.2f for %s",
                rr_ratio, self.min_rr, instrument,
            )
            return None

        components["rr_ratio"] = round(rr_ratio, 2)
        components["risk_pips"] = round(risk, 5)

        setup = TradeSetup(
            signal_type="scalper_smc",
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confluence_score=confluence_score,
            components=components,
        )

        logger.info(
            "ScalperStrategy: setup found for %s – %s entry=%.5f SL=%.5f TP=%.5f "
            "R:R=%.2f score=%.1f",
            instrument, direction, entry_price, stop_loss, take_profit,
            rr_ratio, confluence_score,
        )

        return setup

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    @staticmethod
    def get_position_size(
        account_balance: float,
        entry: float,
        stop_loss: float,
        risk_pct: float,
    ) -> int:
        """Calculate the number of units for an OANDA order.

        Parameters
        ----------
        account_balance : float
            Current account equity in the account's base currency.
        entry : float
            Planned entry price.
        stop_loss : float
            Planned stop-loss price.
        risk_pct : float
            Fraction of account to risk (e.g. 0.005 for 0.5 %).

        Returns
        -------
        int
            Number of units (always a positive integer; the caller applies
            the sign for buy/sell when placing the OANDA order).
        """
        risk_amount = account_balance * risk_pct
        pip_risk = abs(entry - stop_loss)

        if pip_risk <= 0:
            return 0

        units = risk_amount / pip_risk
        return max(1, int(math.floor(units)))
