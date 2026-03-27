"""Fair Value Gap (FVG) detection and fill tracking.

A Fair Value Gap (also called an imbalance) is a three-candle pattern where
the middle candle's range is so large that it leaves a gap between the first
and third candle's bodies/wicks. This gap represents an area where only one
side of the market (buyers or sellers) was active, creating an "inefficiency"
that price often revisits.

Key concepts:
    - **Bullish FVG**: Forms during an impulsive up-move. The gap exists
      between candle[i-2].high and candle[i].low. Price tends to retrace
      into this zone before continuing higher (acts as support).
    - **Bearish FVG**: Forms during an impulsive down-move. The gap exists
      between candle[i-2].low and candle[i].high. Price tends to retrace
      into this zone before continuing lower (acts as resistance).
    - **Fill status**: FVGs can be unfilled (untouched), partially filled
      (price entered the zone but didn't trade through it), or fully filled
      (price traded through the entire gap).

Usage:
    >>> fvgs = find_fvg(ohlcv)
    >>> for fvg in fvgs:
    ...     status = check_fvg_fill(fvg, ohlcv)
    ...     print(f"{fvg.type} FVG: {fvg.low:.2f}-{fvg.high:.2f} [{status}]")
"""

from typing import List

from .models import OHLCV, FairValueGap


def find_fvg(ohlcv: List[OHLCV], timeframe: str = '') -> List[FairValueGap]:
    """Detect Fair Value Gaps in OHLCV price data.

    Scans through the candle series looking for three-candle patterns where
    a gap exists between the first and third candle:

    - **Bullish FVG** at index ``i``: ``ohlcv[i-2].high < ohlcv[i].low``
      The gap zone spans from ``ohlcv[i-2].high`` (bottom) to
      ``ohlcv[i].low`` (top).

    - **Bearish FVG** at index ``i``: ``ohlcv[i-2].low > ohlcv[i].high``
      The gap zone spans from ``ohlcv[i].high`` (bottom) to
      ``ohlcv[i-2].low`` (top).

    Args:
        ohlcv: Chronologically ordered OHLCV bars. Minimum 3 bars required.
        timeframe: Optional timeframe label (e.g. '1h', '4h') to attach to
            each FVG for multi-timeframe analysis.

    Returns:
        List of FairValueGap objects sorted by creation time (ascending).
    """
    if len(ohlcv) < 3:
        return []

    fvgs: List[FairValueGap] = []

    for i in range(2, len(ohlcv)):
        candle_1 = ohlcv[i - 2]  # First candle
        candle_3 = ohlcv[i]      # Third candle
        candle_2 = ohlcv[i - 1]  # Middle candle (the impulse)

        # Bullish FVG: gap between candle 1 high and candle 3 low
        if candle_1.high < candle_3.low:
            fvgs.append(FairValueGap(
                type='bullish',
                high=candle_3.low,
                low=candle_1.high,
                timeframe=timeframe,
                created_at=candle_2.timestamp,
                fill_status='unfilled',
            ))

        # Bearish FVG: gap between candle 3 high and candle 1 low
        if candle_1.low > candle_3.high:
            fvgs.append(FairValueGap(
                type='bearish',
                high=candle_1.low,
                low=candle_3.high,
                timeframe=timeframe,
                created_at=candle_2.timestamp,
                fill_status='unfilled',
            ))

    return fvgs


def check_fvg_fill(fvg: FairValueGap, ohlcv: List[OHLCV]) -> str:
    """Determine the fill status of a Fair Value Gap.

    Examines price action after the FVG was created to determine how much
    of the gap has been filled:

    - **'unfilled'**: Price has not entered the FVG zone at all.
    - **'partial'**: Price has entered the zone (wick or close touched it)
      but has not traded through the entire gap.
    - **'filled'**: Price has traded through the entire FVG zone, meaning
      the imbalance has been fully resolved.

    Fill detection logic:
        - Bullish FVG is filled when a candle's low goes below the FVG low
          (price swept through the entire support zone).
        - Bearish FVG is filled when a candle's high goes above the FVG high
          (price swept through the entire resistance zone).
        - Partial fill is when price enters the zone without completing the
          full traversal.

    Args:
        fvg: The FairValueGap to evaluate.
        ohlcv: Full OHLCV data series.

    Returns:
        One of 'unfilled', 'partial', or 'filled'.
    """
    touched = False
    filled = False

    for candle in ohlcv:
        if candle.timestamp <= fvg.created_at:
            continue

        if fvg.type == 'bullish':
            # Check if price entered the zone from above (retracing into it)
            if candle.low <= fvg.high:
                touched = True
            # Fully filled if price traded through the bottom of the zone
            if candle.low <= fvg.low:
                filled = True
                break
        else:
            # Bearish FVG: check if price entered from below
            if candle.high >= fvg.low:
                touched = True
            # Fully filled if price traded through the top of the zone
            if candle.high >= fvg.high:
                filled = True
                break

    if filled:
        fvg.fill_status = 'filled'
        return 'filled'
    elif touched:
        fvg.fill_status = 'partial'
        return 'partial'
    else:
        return 'unfilled'


def is_price_in_fvg(price: float, fvg: FairValueGap) -> bool:
    """Check if a price is within a Fair Value Gap zone.

    Args:
        price: The price level to check.
        fvg: The FairValueGap zone.

    Returns:
        True if the price is between the FVG's low and high (inclusive).
    """
    return fvg.low <= price <= fvg.high
