"""Multi-factor confluence scoring and trade setup generation.

Confluence scoring combines multiple SMC signals into a single probability
score (0-100) for a potential trade. Higher scores indicate that more
institutional footprints align at the entry zone, increasing the likelihood
of a successful trade.

Scoring factors:
    - Market structure alignment (trend direction)
    - Order block presence at the entry zone
    - Fair value gap overlap
    - Liquidity sweep confirmation
    - OTE zone alignment
    - Premium/discount zone position

Usage:
    >>> score = score_setup(components)
    >>> if score >= 60:
    ...     setup = find_entry(ohlcv, swing_points, ...)
    ...     sl, tp = calculate_sl_tp(entry, direction, atr, rr_ratio=2.0)
"""

from typing import Any, Dict, List, Optional, Tuple

from .models import (
    OHLCV,
    FairValueGap,
    LiquidityLevel,
    OrderBlock,
    SwingPoint,
    TradeSetup,
)
from .fibonacci import calculate_ote_zone, is_in_discount, is_in_premium


def score_setup(components: Dict[str, Any]) -> float:
    """Calculate a confluence score (0-100) from SMC signal components.

    Each component adds points to the total score:
        - trend_aligned:    +25 (market structure supports direction)
        - in_order_block:   +20 (price is at an institutional OB)
        - in_fvg:           +15 (price is in a fair value gap)
        - liquidity_swept:  +15 (a liquidity grab confirms reversal)
        - in_ote:           +15 (price is in the OTE zone)
        - in_discount/premium: +10 (correct zone for direction)

    Args:
        components: Dict with boolean flags for each signal factor.

    Returns:
        Score between 0 and 100.
    """
    score = 0.0

    if components.get("trend_aligned", False):
        score += 25.0
    if components.get("in_order_block", False):
        score += 20.0
    if components.get("in_fvg", False):
        score += 15.0
    if components.get("liquidity_swept", False):
        score += 15.0
    if components.get("in_ote", False):
        score += 15.0
    if components.get("in_discount", False) or components.get("in_premium", False):
        score += 10.0

    return min(score, 100.0)


def find_entry(
    ohlcv: List[OHLCV],
    swing_points: List[SwingPoint],
    order_blocks: List[OrderBlock],
    fvgs: List[FairValueGap],
    liquidity_levels: List[LiquidityLevel],
    direction: str,
    trend: str,
) -> Optional[TradeSetup]:
    """Scan for a confluent trade entry from current price action.

    Evaluates the latest price against available SMC factors and produces
    a TradeSetup if sufficient confluence exists.

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        swing_points: Detected swing points.
        order_blocks: Active (unmitigated) order blocks.
        fvgs: Active fair value gaps.
        liquidity_levels: Mapped liquidity levels.
        direction: Desired trade direction ('long' or 'short').
        trend: Current market trend ('bullish', 'bearish', 'ranging').

    Returns:
        A TradeSetup if confluence score meets threshold, else None.
    """
    if not ohlcv or len(ohlcv) < 2:
        return None

    current_price = ohlcv[-1].close

    # Determine swing range for Fibonacci calculations
    highs = [sp for sp in swing_points if sp.type == 'high']
    lows = [sp for sp in swing_points if sp.type == 'low']

    if not highs or not lows:
        return None

    swing_high = max(sp.price for sp in highs)
    swing_low = min(sp.price for sp in lows)

    if swing_high <= swing_low:
        return None

    # Evaluate confluence components
    components: Dict[str, Any] = {}

    # 1. Trend alignment
    if direction == "long" and trend == "bullish":
        components["trend_aligned"] = True
    elif direction == "short" and trend == "bearish":
        components["trend_aligned"] = True
    else:
        components["trend_aligned"] = False

    # 2. Order block check
    components["in_order_block"] = False
    for ob in order_blocks:
        if ob.mitigated:
            continue
        if ob.low <= current_price <= ob.high:
            if (direction == "long" and ob.type == "bullish") or \
               (direction == "short" and ob.type == "bearish"):
                components["in_order_block"] = True
                components["order_block"] = ob
                break

    # 3. Fair value gap check
    components["in_fvg"] = False
    for fvg in fvgs:
        if fvg.fill_status == 'filled':
            continue
        if fvg.low <= current_price <= fvg.high:
            if (direction == "long" and fvg.type == "bullish") or \
               (direction == "short" and fvg.type == "bearish"):
                components["in_fvg"] = True
                components["fvg"] = fvg
                break

    # 4. Liquidity sweep check
    components["liquidity_swept"] = False
    for level in liquidity_levels:
        if level.swept:
            components["liquidity_swept"] = True
            break

    # 5. OTE zone check
    ote = calculate_ote_zone(swing_low, swing_high)
    components["in_ote"] = ote["ote_low"] <= current_price <= ote["ote_high"]

    # 6. Premium/Discount zone
    if direction == "long":
        components["in_discount"] = is_in_discount(current_price, swing_low, swing_high)
    else:
        components["in_premium"] = is_in_premium(current_price, swing_low, swing_high)

    confluence = score_setup(components)

    if confluence < 40:
        return None

    # Calculate SL/TP
    atr = _estimate_atr(ohlcv)
    sl, tp = calculate_sl_tp(current_price, direction, atr, rr_ratio=2.0)

    return TradeSetup(
        signal_type="smc_confluence",
        direction=direction,
        entry_price=current_price,
        stop_loss=sl,
        take_profit=tp,
        confluence_score=confluence,
        components=components,
    )


def calculate_sl_tp(
    entry_price: float,
    direction: str,
    atr: float,
    rr_ratio: float = 2.0,
    sl_multiplier: float = 1.5,
) -> Tuple[float, float]:
    """Calculate stop-loss and take-profit levels.

    Uses ATR-based stops with a configurable risk-to-reward ratio.

    Args:
        entry_price: The planned entry price.
        direction: 'long' or 'short'.
        atr: Average True Range value for volatility-based sizing.
        rr_ratio: Target risk-to-reward ratio (e.g. 2.0 = 1:2 R:R).
        sl_multiplier: ATR multiplier for stop-loss distance.

    Returns:
        Tuple of (stop_loss, take_profit) prices.
    """
    sl_distance = atr * sl_multiplier
    tp_distance = sl_distance * rr_ratio

    if direction == "long":
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance

    return stop_loss, take_profit


def _estimate_atr(ohlcv: List[OHLCV], period: int = 14) -> float:
    """Estimate the Average True Range from OHLCV data.

    Uses the standard ATR calculation:
        TR = max(high - low, |high - prev_close|, |low - prev_close|)
        ATR = SMA(TR, period)

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        period: Lookback period for the ATR average.

    Returns:
        Current ATR value. Returns a default based on recent range if
        insufficient data.
    """
    if len(ohlcv) < 2:
        return ohlcv[0].high - ohlcv[0].low if ohlcv else 0.001

    true_ranges = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i].high
        low = ohlcv[i].low
        prev_close = ohlcv[i - 1].close

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    # Use the last `period` TRs for the average
    lookback = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(lookback) / len(lookback) if lookback else 0.001
