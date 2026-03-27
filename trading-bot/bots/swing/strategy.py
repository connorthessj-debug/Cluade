"""Swing trading strategy using Smart Money Concepts (ICT methodology).

Multi-timeframe analysis with higher timeframes than the scalper:
  W1  -> major market bias
  D1  -> structure and order block identification
  H4  -> entry timing, waiting for price to retrace into D1 OB
  H1  -> CHoCH confirmation within the D1 OB

Partial take-profit at 1R and 2R levels. Minimum R:R of 1:3.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from smc.market_structure import detect_swing_points, detect_bos, detect_choch, get_trend
from smc.order_blocks import find_order_blocks, is_price_in_ob
from smc.fibonacci import is_in_premium, is_in_discount, get_fib_levels
from smc.confluence import score_setup, calculate_sl_tp
from core.models import OHLCV, TradeSetup, SwingPoint

logger = logging.getLogger(__name__)


class SwingStrategy:
    """ICT/SMC-based swing trading strategy with multi-timeframe confluence.

    Parameters
    ----------
    min_confluence : int
        Minimum confluence score (0-100) required to generate a setup.
        Default is 65 (higher bar than scalper due to wider stops).
    min_rr : float
        Minimum reward-to-risk ratio. Default 3.0.
    partial_tp_levels : list[float]
        R-multiples at which to take partial profit (e.g. ``[1.0, 2.0]``).
    """

    def __init__(
        self,
        min_confluence: int = 65,
        min_rr: float = 3.0,
        partial_tp_levels: Optional[List[float]] = None,
    ):
        self.min_confluence = min_confluence
        self.min_rr = min_rr
        self.partial_tp_levels = partial_tp_levels or [1.0, 2.0]

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    async def analyze(
        self,
        oanda_client,
        instrument: str,
        config: Dict[str, Any],
    ) -> Optional[TradeSetup]:
        """Run multi-timeframe SMC analysis for swing trading.

        Parameters
        ----------
        oanda_client : OandaClient
            OANDA API client.
        instrument : str
            OANDA instrument name (e.g. ``'EUR_USD'``).
        config : dict
            Strategy parameters.

        Returns
        -------
        TradeSetup or None
        """
        try:
            return await self._run_analysis(oanda_client, instrument, config)
        except Exception:
            logger.exception("SwingStrategy: analysis failed for %s", instrument)
            return None

    async def _run_analysis(
        self,
        oanda_client,
        instrument: str,
        config: Dict[str, Any],
    ) -> Optional[TradeSetup]:
        # ----------------------------------------------------------
        # Step 1: W1 – major bias
        # ----------------------------------------------------------
        w1_candles = await oanda_client.get_candles(instrument, "W", 20)
        if not w1_candles or len(w1_candles) < 10:
            logger.debug("SwingStrategy: insufficient W1 data for %s", instrument)
            return None

        w1_swings = detect_swing_points(w1_candles, lookback=2)
        w1_trend = get_trend(w1_swings)

        if w1_trend == "ranging":
            logger.debug("SwingStrategy: W1 trend is ranging for %s, skipping", instrument)
            return None

        # ----------------------------------------------------------
        # Step 2: D1 – structure and OB identification
        # ----------------------------------------------------------
        d1_candles = await oanda_client.get_candles(instrument, "D", 50)
        if not d1_candles or len(d1_candles) < 20:
            return None

        d1_swings = detect_swing_points(d1_candles, lookback=3)
        d1_trend = get_trend(d1_swings)
        d1_bos = detect_bos(d1_candles, d1_swings)
        d1_obs = find_order_blocks(d1_candles, d1_swings)

        # Filter OBs aligned with W1 bias
        if w1_trend == "bullish":
            aligned_obs = [ob for ob in d1_obs if ob.type == "bullish" and not ob.mitigated]
        else:
            aligned_obs = [ob for ob in d1_obs if ob.type == "bearish" and not ob.mitigated]

        if not aligned_obs:
            logger.debug("SwingStrategy: no aligned D1 OBs for %s", instrument)
            return None

        # ----------------------------------------------------------
        # Step 3: H4 – entry timing, wait for price to retrace into D1 OB
        # ----------------------------------------------------------
        h4_candles = await oanda_client.get_candles(instrument, "H4", 50)
        if not h4_candles or len(h4_candles) < 15:
            return None

        current_price = h4_candles[-1].close

        # Check if price is currently inside a D1 order block
        active_ob = None
        for ob in reversed(aligned_obs):
            if is_price_in_ob(current_price, ob):
                active_ob = ob
                break

        if active_ob is None:
            logger.debug(
                "SwingStrategy: price %.5f not in any D1 OB for %s",
                current_price, instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 4: H1 – CHoCH confirmation within the D1 OB
        # ----------------------------------------------------------
        h1_candles = await oanda_client.get_candles(instrument, "H1", 30)
        if not h1_candles or len(h1_candles) < 15:
            return None

        h1_swings = detect_swing_points(h1_candles, lookback=2)
        h1_choch = detect_choch(h1_candles, h1_swings)

        # Need CHoCH in the direction of our bias
        confirming_choch = [c for c in h1_choch if c["type"] == w1_trend]

        if not confirming_choch:
            logger.debug(
                "SwingStrategy: no H1 CHoCH confirmation for %s", instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 5: Premium/discount zone check and confluence scoring
        # ----------------------------------------------------------
        d1_highs = [sp for sp in d1_swings if sp.type == "high"]
        d1_lows = [sp for sp in d1_swings if sp.type == "low"]

        if not d1_highs or not d1_lows:
            return None

        swing_high = max(sp.price for sp in d1_highs)
        swing_low = min(sp.price for sp in d1_lows)

        # Longs only in discount, shorts only in premium
        if w1_trend == "bullish":
            if not is_in_discount(current_price, swing_high, swing_low):
                logger.debug(
                    "SwingStrategy: price not in discount zone for long on %s",
                    instrument,
                )
                return None
        else:
            if not is_in_premium(current_price, swing_high, swing_low):
                logger.debug(
                    "SwingStrategy: price not in premium zone for short on %s",
                    instrument,
                )
                return None

        # Build confluence components
        components = {
            "w1_trend": w1_trend,
            "d1_trend": d1_trend,
            "d1_ob": {"type": active_ob.type, "high": active_ob.high, "low": active_ob.low},
            "h1_choch_count": len(confirming_choch),
            "d1_bos_count": len(d1_bos),
            "partial_tp_levels": self.partial_tp_levels,
        }

        confluence_score = score_setup(
            candles=d1_candles,
            swing_points=d1_swings,
            order_blocks=d1_obs,
        )

        if confluence_score < self.min_confluence:
            logger.debug(
                "SwingStrategy: confluence %.1f below threshold %d for %s",
                confluence_score, self.min_confluence, instrument,
            )
            return None

        # ----------------------------------------------------------
        # Step 6: Calculate entry, SL, TP
        # ----------------------------------------------------------
        direction = "long" if w1_trend == "bullish" else "short"

        sl_tp = calculate_sl_tp(
            direction=direction,
            entry_price=current_price,
            swing_points=d1_swings,
            order_blocks=aligned_obs,
        )

        entry_price = current_price
        stop_loss = sl_tp.get("stop_loss", 0.0)
        take_profit = sl_tp.get("take_profit", 0.0)

        # Validate minimum R:R of 1:3
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return None

        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk

        if rr_ratio < self.min_rr:
            logger.debug(
                "SwingStrategy: R:R %.2f below minimum %.2f for %s",
                rr_ratio, self.min_rr, instrument,
            )
            return None

        # Calculate partial TP price levels
        partial_prices = []
        for r_mult in self.partial_tp_levels:
            if direction == "long":
                partial_prices.append(entry_price + risk * r_mult)
            else:
                partial_prices.append(entry_price - risk * r_mult)

        components["rr_ratio"] = round(rr_ratio, 2)
        components["risk_pips"] = round(risk, 5)
        components["partial_tp_prices"] = [round(p, 5) for p in partial_prices]

        setup = TradeSetup(
            signal_type="swing_smc",
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confluence_score=confluence_score,
            components=components,
        )

        logger.info(
            "SwingStrategy: setup found for %s – %s entry=%.5f SL=%.5f TP=%.5f "
            "R:R=%.2f score=%.1f partials=%s",
            instrument, direction, entry_price, stop_loss, take_profit,
            rr_ratio, confluence_score,
            [round(p, 5) for p in partial_prices],
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
            Current account equity.
        entry : float
            Planned entry price.
        stop_loss : float
            Planned stop-loss price.
        risk_pct : float
            Fraction of account to risk (e.g. 0.01 for 1 %).

        Returns
        -------
        int
            Number of units (positive integer).
        """
        risk_amount = account_balance * risk_pct
        pip_risk = abs(entry - stop_loss)

        if pip_risk <= 0:
            return 0

        units = risk_amount / pip_risk
        return max(1, int(math.floor(units)))
