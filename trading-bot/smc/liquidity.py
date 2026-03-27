"""Liquidity analysis and sweep detection.

Liquidity in SMC refers to clusters of resting orders (stop losses, limit
orders) at predictable price levels. Institutional traders often engineer
price moves to "sweep" or "grab" these liquidity pools before reversing
direction, creating high-probability trade entries.

Key concepts:
    - **Equal highs/lows**: When multiple swing points cluster at nearly the
      same price, stop-loss orders accumulate just beyond those levels. These
      are visible targets for institutional sweeps.
    - **Swing liquidity**: Major swing highs and lows act as liquidity targets
      because retail traders place stops just beyond them.
    - **Liquidity sweep (stop hunt)**: Price wicks beyond a liquidity level
      (triggering stops) but closes back inside, signaling that the sweep
      is complete and a reversal is likely.

Usage:
    >>> equal_levels = find_equal_levels(swing_points, tolerance=0.001)
    >>> swing_liq = find_swing_liquidity(swing_points)
    >>> all_levels = equal_levels + swing_liq
    >>> sweeps = detect_liquidity_sweep(ohlcv, all_levels)
    >>> for sweep in sweeps:
    ...     print(f"Sweep at {sweep['level'].price:.2f}, index {sweep['sweep_index']}")
"""

from typing import List

import numpy as np

from .models import OHLCV, LiquidityLevel, SwingPoint


def find_equal_levels(
    swing_points: List[SwingPoint],
    tolerance: float = 0.001,
) -> List[LiquidityLevel]:
    """Identify clusters of swing points at approximately the same price.

    Equal highs and equal lows form when price repeatedly tests the same
    level without breaking through. Each touch adds resting stop-loss
    orders just beyond the level, making it an attractive liquidity target.

    The algorithm groups swing points of the same type (high/low) whose
    prices are within ``tolerance`` (as a fraction of the price) of each
    other. The resulting level's price is the mean of the cluster, and its
    strength equals the number of touches.

    Args:
        swing_points: List of SwingPoint objects from swing detection.
        tolerance: Maximum relative price difference to consider two swing
            points as "equal". A tolerance of 0.001 means prices within
            0.1% of each other are grouped together.

    Returns:
        List of LiquidityLevel objects representing equal-level clusters.
        Only clusters with 2 or more touches are returned (a single swing
        point is not considered an "equal level").
    """
    if not swing_points:
        return []

    # Separate highs and lows
    highs = [sp for sp in swing_points if sp.type == 'high']
    lows = [sp for sp in swing_points if sp.type == 'low']

    levels: List[LiquidityLevel] = []
    levels.extend(_cluster_swings(highs, tolerance, level_type='high'))
    levels.extend(_cluster_swings(lows, tolerance, level_type='low'))

    return levels


def _cluster_swings(
    swings: List[SwingPoint],
    tolerance: float,
    level_type: str,
) -> List[LiquidityLevel]:
    """Group swing points into clusters based on price proximity.

    Uses a greedy single-pass clustering approach: sort by price, then
    walk through building clusters where each new point is within tolerance
    of the cluster's running mean.
    """
    if not swings:
        return []

    sorted_swings = sorted(swings, key=lambda sp: sp.price)
    clusters: List[List[SwingPoint]] = []
    current_cluster: List[SwingPoint] = [sorted_swings[0]]

    for sp in sorted_swings[1:]:
        cluster_mean = np.mean([s.price for s in current_cluster])
        # Check relative distance from cluster mean
        if abs(sp.price - cluster_mean) / cluster_mean <= tolerance:
            current_cluster.append(sp)
        else:
            clusters.append(current_cluster)
            current_cluster = [sp]

    clusters.append(current_cluster)

    # Convert clusters with 2+ touches into LiquidityLevel objects
    levels: List[LiquidityLevel] = []
    for cluster in clusters:
        if len(cluster) >= 2:
            mean_price = float(np.mean([sp.price for sp in cluster]))
            levels.append(LiquidityLevel(
                price=mean_price,
                type=level_type,
                strength=len(cluster),
                swept=False,
            ))

    return levels


def find_swing_liquidity(
    swing_points: List[SwingPoint],
) -> List[LiquidityLevel]:
    """Map major swing highs and lows as individual liquidity targets.

    Every significant swing high has buy-stop liquidity resting above it
    (from short sellers' stop losses and breakout buyers' entries). Every
    significant swing low has sell-stop liquidity resting below it (from
    long traders' stop losses and breakdown sellers' entries).

    Unlike ``find_equal_levels`` which looks for clusters, this function
    treats each swing point as its own liquidity target with strength 1.

    Args:
        swing_points: List of SwingPoint objects.

    Returns:
        List of LiquidityLevel objects, one per swing point.
    """
    levels: List[LiquidityLevel] = []

    for sp in swing_points:
        levels.append(LiquidityLevel(
            price=sp.price,
            type=sp.type,
            strength=1,
            swept=False,
        ))

    return levels


def detect_liquidity_sweep(
    ohlcv: List[OHLCV],
    levels: List[LiquidityLevel],
) -> List[dict]:
    """Detect liquidity sweeps (stop hunts / liquidity grabs).

    A liquidity sweep occurs when price momentarily trades beyond a
    liquidity level (the wick pierces it) but the candle closes back
    inside, indicating that:

    1. Resting stop-loss orders at the level were triggered (filled).
    2. The move beyond the level was not sustained (no real breakout).
    3. Institutional players grabbed the liquidity and are likely to
       reverse price direction.

    This is one of the highest-probability reversal signals in SMC.

    Detection logic:
        - **High liquidity sweep**: A candle's high exceeds the level price,
          but the close is below the level. The wick "swept" buy-stop
          liquidity above the swing high.
        - **Low liquidity sweep**: A candle's low goes below the level price,
          but the close is above the level. The wick "swept" sell-stop
          liquidity below the swing low.

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        levels: Liquidity levels to monitor for sweeps.

    Returns:
        List of dicts with keys:
            - ``level``: The LiquidityLevel that was swept.
            - ``sweep_index``: Bar index where the sweep occurred.
            - ``swept``: Always True (confirms the sweep event).
    """
    if not ohlcv or not levels:
        return []

    sweeps: List[dict] = []

    for level in levels:
        if level.swept:
            continue

        for i, candle in enumerate(ohlcv):
            swept = False

            if level.type == 'high':
                # Wick above the level, close below => sweep of buy-stop liquidity
                if candle.high > level.price and candle.close < level.price:
                    swept = True

            elif level.type == 'low':
                # Wick below the level, close above => sweep of sell-stop liquidity
                if candle.low < level.price and candle.close > level.price:
                    swept = True

            if swept:
                level.swept = True
                sweeps.append({
                    'level': level,
                    'sweep_index': i,
                    'swept': True,
                })
                break  # Only record the first sweep per level

    sweeps.sort(key=lambda s: s['sweep_index'])
    return sweeps
