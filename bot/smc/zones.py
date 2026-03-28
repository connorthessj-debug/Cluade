"""
SMC Zones — Order Blocks (OB) and Fair Value Gaps (FVG).

Order Blocks: The last opposing candle before a strong move (institutional footprint).
Fair Value Gaps: Three-candle imbalances where price moved too fast, leaving a gap.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from config import (
    OB_MAX_AGE_CANDLES, OB_MAX_BODY_RATIO,
    FVG_MIN_GAP_PIPS, FVG_MAX_AGE_CANDLES,
)

logger = logging.getLogger(__name__)


@dataclass
class OrderBlock:
    """An institutional order block zone."""
    index: int
    high: float
    low: float
    kind: str        # "bullish" or "bearish"
    mitigated: bool  # Has price returned to this zone?
    datetime: pd.Timestamp

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class FairValueGap:
    """A fair value gap (imbalance)."""
    index: int
    high: float      # Upper boundary of gap
    low: float       # Lower boundary of gap
    kind: str        # "bullish" or "bearish"
    filled: bool     # Has the gap been filled?
    datetime: pd.Timestamp

    @property
    def size(self) -> float:
        return abs(self.high - self.low)

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


def detect_order_blocks(
    df: pd.DataFrame,
    pip_size: float = 0.0001,
) -> list[OrderBlock]:
    """
    Detect order blocks in price data.

    Bullish OB: Last bearish candle before a strong bullish move that
    breaks structure (the low of that candle is the OB zone).

    Bearish OB: Last bullish candle before a strong bearish move that
    breaks structure (the high of that candle is the OB zone).
    """
    n = len(df)
    if n < 10:
        return []

    obs = []

    for i in range(2, n - 1):
        curr_open = df["open"].iloc[i]
        curr_close = df["close"].iloc[i]
        curr_high = df["high"].iloc[i]
        curr_low = df["low"].iloc[i]
        curr_range = curr_high - curr_low

        if curr_range == 0:
            continue

        body_ratio = abs(curr_close - curr_open) / curr_range

        # Previous candle for comparison
        prev_close = df["close"].iloc[i - 1]
        next_close = df["close"].iloc[i + 1] if i + 1 < n else curr_close

        # Bullish OB: bearish candle followed by strong bullish move
        if curr_close < curr_open:  # Current is bearish
            # Next candle(s) move strongly bullish
            move_up = next_close - curr_close
            if move_up > curr_range * 1.5 and body_ratio <= OB_MAX_BODY_RATIO:
                obs.append(OrderBlock(
                    index=i,
                    high=curr_high,
                    low=curr_low,
                    kind="bullish",
                    mitigated=False,
                    datetime=df["datetime"].iloc[i],
                ))

        # Bearish OB: bullish candle followed by strong bearish move
        if curr_close > curr_open:  # Current is bullish
            move_down = curr_close - next_close
            if move_down > curr_range * 1.5 and body_ratio <= OB_MAX_BODY_RATIO:
                obs.append(OrderBlock(
                    index=i,
                    high=curr_high,
                    low=curr_low,
                    kind="bearish",
                    mitigated=False,
                    datetime=df["datetime"].iloc[i],
                ))

    # Check mitigation — has price returned to the OB zone?
    last_idx = n - 1
    for ob in obs:
        age = last_idx - ob.index
        if age > OB_MAX_AGE_CANDLES:
            ob.mitigated = True  # Too old, consider mitigated
            continue

        for j in range(ob.index + 2, n):
            if ob.kind == "bullish" and df["low"].iloc[j] <= ob.high:
                ob.mitigated = True
                break
            elif ob.kind == "bearish" and df["high"].iloc[j] >= ob.low:
                ob.mitigated = True
                break

    return obs


def detect_fvg(
    df: pd.DataFrame,
    pip_size: float = 0.0001,
) -> list[FairValueGap]:
    """
    Detect Fair Value Gaps (imbalances) in price data.

    Bullish FVG: Candle 1 high < Candle 3 low (gap up).
    Bearish FVG: Candle 1 low > Candle 3 high (gap down).
    """
    n = len(df)
    if n < 3:
        return []

    min_gap = FVG_MIN_GAP_PIPS * pip_size
    fvgs = []

    for i in range(2, n):
        c1_high = df["high"].iloc[i - 2]
        c1_low = df["low"].iloc[i - 2]
        c3_high = df["high"].iloc[i]
        c3_low = df["low"].iloc[i]

        # Bullish FVG: gap between candle 1 high and candle 3 low
        if c3_low > c1_high and (c3_low - c1_high) >= min_gap:
            fvgs.append(FairValueGap(
                index=i - 1,  # The middle candle
                high=c3_low,
                low=c1_high,
                kind="bullish",
                filled=False,
                datetime=df["datetime"].iloc[i - 1],
            ))

        # Bearish FVG: gap between candle 3 high and candle 1 low
        if c1_low > c3_high and (c1_low - c3_high) >= min_gap:
            fvgs.append(FairValueGap(
                index=i - 1,
                high=c1_low,
                low=c3_high,
                kind="bearish",
                filled=False,
                datetime=df["datetime"].iloc[i - 1],
            ))

    # Check if FVGs have been filled
    last_idx = n - 1
    for fvg in fvgs:
        age = last_idx - fvg.index
        if age > FVG_MAX_AGE_CANDLES:
            fvg.filled = True
            continue

        for j in range(fvg.index + 2, n):
            if fvg.kind == "bullish" and df["low"].iloc[j] <= fvg.low:
                fvg.filled = True
                break
            elif fvg.kind == "bearish" and df["high"].iloc[j] >= fvg.high:
                fvg.filled = True
                break

    return fvgs


def find_entry_zone(
    df: pd.DataFrame,
    direction: str,
    pip_size: float = 0.0001,
) -> dict | None:
    """
    Find the best entry zone (OB or FVG) for a trade in the given direction.

    Returns the most recent unmitigated/unfilled zone, or None.
    """
    current_price = df["close"].iloc[-1]

    # Check Order Blocks first (higher probability)
    obs = detect_order_blocks(df, pip_size)
    valid_obs = [
        ob for ob in obs
        if ob.kind == ("bullish" if direction == "bullish" else "bearish")
        and not ob.mitigated
        and (len(df) - 1 - ob.index) <= OB_MAX_AGE_CANDLES
    ]

    if valid_obs:
        # Find the closest unmitigated OB to current price
        best_ob = min(valid_obs, key=lambda ob: abs(ob.midpoint - current_price))
        return {
            "type": "order_block",
            "high": best_ob.high,
            "low": best_ob.low,
            "entry": best_ob.midpoint,
            "direction": direction,
            "datetime": best_ob.datetime,
        }

    # Fall back to FVG
    fvgs = detect_fvg(df, pip_size)
    valid_fvgs = [
        fvg for fvg in fvgs
        if fvg.kind == ("bullish" if direction == "bullish" else "bearish")
        and not fvg.filled
        and (len(df) - 1 - fvg.index) <= FVG_MAX_AGE_CANDLES
    ]

    if valid_fvgs:
        best_fvg = min(valid_fvgs, key=lambda f: abs(f.midpoint - current_price))
        return {
            "type": "fvg",
            "high": best_fvg.high,
            "low": best_fvg.low,
            "entry": best_fvg.midpoint,
            "direction": direction,
            "datetime": best_fvg.datetime,
        }

    return None
