"""
SMC Liquidity Detection — Equal highs/lows, liquidity pools, and sweep events.

Liquidity sits above swing highs and below swing lows. Smart money sweeps
these levels to fill orders before reversing.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from config import LIQ_SWEEP_THRESHOLD_PIPS, LIQ_EQUAL_HIGHS_TOLERANCE
from .structure import find_swing_points

logger = logging.getLogger(__name__)


@dataclass
class LiquidityLevel:
    """A level where liquidity is likely resting (stop losses)."""
    price: float
    kind: str        # "above" (buy-side) or "below" (sell-side)
    strength: int    # Number of touches / equal levels
    last_index: int
    datetime: pd.Timestamp


@dataclass
class LiquiditySweep:
    """An event where price swept through a liquidity level and reversed."""
    index: int
    sweep_price: float
    level_price: float
    kind: str         # "buy_side" or "sell_side"
    datetime: pd.Timestamp


def find_liquidity_levels(
    df: pd.DataFrame,
    pip_size: float = 0.0001,
) -> list[LiquidityLevel]:
    """
    Find levels where liquidity is resting:
    - Equal highs (buy-side liquidity above)
    - Equal lows (sell-side liquidity below)
    - Prominent swing highs/lows
    """
    swings = find_swing_points(df)
    if not swings:
        return []

    tolerance = LIQ_EQUAL_HIGHS_TOLERANCE * pip_size
    levels = []

    # Group swing highs that are near the same price (equal highs)
    highs = [s for s in swings if s.kind == "high"]
    used_highs = set()
    for i, h1 in enumerate(highs):
        if i in used_highs:
            continue
        cluster = [h1]
        for j, h2 in enumerate(highs):
            if j != i and j not in used_highs and abs(h1.price - h2.price) <= tolerance:
                cluster.append(h2)
                used_highs.add(j)
        used_highs.add(i)

        levels.append(LiquidityLevel(
            price=max(c.price for c in cluster),
            kind="above",
            strength=len(cluster),
            last_index=max(c.index for c in cluster),
            datetime=max(c.datetime for c in cluster),
        ))

    # Group swing lows (equal lows)
    lows = [s for s in swings if s.kind == "low"]
    used_lows = set()
    for i, l1 in enumerate(lows):
        if i in used_lows:
            continue
        cluster = [l1]
        for j, l2 in enumerate(lows):
            if j != i and j not in used_lows and abs(l1.price - l2.price) <= tolerance:
                cluster.append(l2)
                used_lows.add(j)
        used_lows.add(i)

        levels.append(LiquidityLevel(
            price=min(c.price for c in cluster),
            kind="below",
            strength=len(cluster),
            last_index=max(c.index for c in cluster),
            datetime=max(c.datetime for c in cluster),
        ))

    return levels


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    pip_size: float = 0.0001,
    lookback: int = 5,
) -> list[LiquiditySweep]:
    """
    Detect candles that swept a liquidity level and then reversed.

    A buy-side sweep: price wicks above a swing high but closes below it.
    A sell-side sweep: price wicks below a swing low but closes above it.
    """
    levels = find_liquidity_levels(df, pip_size)
    if not levels:
        return []

    threshold = LIQ_SWEEP_THRESHOLD_PIPS * pip_size
    sweeps = []
    n = len(df)

    for level in levels:
        # Only check candles after the level was established
        start = level.last_index + 1
        end = min(start + lookback * 10, n)

        for i in range(start, end):
            if level.kind == "above":
                # Buy-side liquidity sweep: wick above, close below
                if (df["high"].iloc[i] > level.price + threshold and
                        df["close"].iloc[i] < level.price):
                    sweeps.append(LiquiditySweep(
                        index=i,
                        sweep_price=df["high"].iloc[i],
                        level_price=level.price,
                        kind="buy_side",
                        datetime=df["datetime"].iloc[i],
                    ))
                    break  # One sweep per level

            elif level.kind == "below":
                # Sell-side liquidity sweep: wick below, close above
                if (df["low"].iloc[i] < level.price - threshold and
                        df["close"].iloc[i] > level.price):
                    sweeps.append(LiquiditySweep(
                        index=i,
                        sweep_price=df["low"].iloc[i],
                        level_price=level.price,
                        kind="sell_side",
                        datetime=df["datetime"].iloc[i],
                    ))
                    break

    # Sort by most recent
    sweeps.sort(key=lambda s: s.index, reverse=True)
    return sweeps


def has_recent_sweep(
    df: pd.DataFrame,
    direction: str,
    pip_size: float = 0.0001,
    max_candles_ago: int = 10,
) -> LiquiditySweep | None:
    """
    Check if there's a recent liquidity sweep that supports a trade in `direction`.

    For a bullish trade: need a recent sell-side sweep (grabbed lows, reversing up).
    For a bearish trade: need a recent buy-side sweep (grabbed highs, reversing down).
    """
    sweeps = detect_liquidity_sweeps(df, pip_size)
    if not sweeps:
        return None

    last_idx = len(df) - 1
    needed_kind = "sell_side" if direction == "bullish" else "buy_side"

    for sweep in sweeps:
        if sweep.kind == needed_kind and (last_idx - sweep.index) <= max_candles_ago:
            return sweep

    return None
