"""
SMC Structure Detection — BOS (Break of Structure) and CHoCH (Change of Character).

Identifies swing highs/lows and determines market structure shifts.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from config import STRUCTURE_LOOKBACK, SWING_STRENGTH

logger = logging.getLogger(__name__)


@dataclass
class SwingPoint:
    """A swing high or low point."""
    index: int
    price: float
    kind: str  # "high" or "low"
    datetime: pd.Timestamp


@dataclass
class StructureBreak:
    """A break of structure or change of character event."""
    index: int
    price: float
    kind: str         # "bos" or "choch"
    direction: str    # "bullish" or "bearish"
    broken_level: float
    datetime: pd.Timestamp


def find_swing_points(df: pd.DataFrame, strength: int = None) -> list[SwingPoint]:
    """
    Identify swing highs and swing lows in price data.

    A swing high requires `strength` candles on each side with lower highs.
    A swing low requires `strength` candles on each side with higher lows.
    """
    if strength is None:
        strength = SWING_STRENGTH

    points = []
    n = len(df)

    for i in range(strength, n - strength):
        # Check swing high
        is_high = True
        for j in range(1, strength + 1):
            if df["high"].iloc[i - j] >= df["high"].iloc[i] or \
               df["high"].iloc[i + j] >= df["high"].iloc[i]:
                is_high = False
                break

        if is_high:
            points.append(SwingPoint(
                index=i,
                price=df["high"].iloc[i],
                kind="high",
                datetime=df["datetime"].iloc[i],
            ))

        # Check swing low
        is_low = True
        for j in range(1, strength + 1):
            if df["low"].iloc[i - j] <= df["low"].iloc[i] or \
               df["low"].iloc[i + j] <= df["low"].iloc[i]:
                is_low = False
                break

        if is_low:
            points.append(SwingPoint(
                index=i,
                price=df["low"].iloc[i],
                kind="low",
                datetime=df["datetime"].iloc[i],
            ))

    # Sort by index
    points.sort(key=lambda p: p.index)
    return points


def detect_structure(df: pd.DataFrame, strength: int = None) -> list[StructureBreak]:
    """
    Detect BOS and CHoCH events in price data.

    BOS (Break of Structure): Price breaks a swing point in the SAME direction
    as the prevailing trend — trend continuation.

    CHoCH (Change of Character): Price breaks a swing point in the OPPOSITE
    direction — potential trend reversal.

    Returns a list of StructureBreak events.
    """
    swings = find_swing_points(df, strength)
    if len(swings) < 4:
        return []

    breaks = []
    trend = None  # "bullish" or "bearish" or None

    # Track the most recent significant swing high and low
    last_high = None
    last_low = None

    for i, swing in enumerate(swings):
        if swing.kind == "high":
            if last_high is not None and last_low is not None:
                # Determine trend from previous swings
                if last_high.price < swing.price and trend != "bullish":
                    # Higher high — if we were bearish, this is CHoCH
                    if trend == "bearish":
                        breaks.append(StructureBreak(
                            index=swing.index,
                            price=swing.price,
                            kind="choch",
                            direction="bullish",
                            broken_level=last_high.price,
                            datetime=swing.datetime,
                        ))
                    trend = "bullish"
                elif last_high.price < swing.price and trend == "bullish":
                    # Higher high in bullish trend — BOS
                    breaks.append(StructureBreak(
                        index=swing.index,
                        price=swing.price,
                        kind="bos",
                        direction="bullish",
                        broken_level=last_high.price,
                        datetime=swing.datetime,
                    ))
            last_high = swing

        elif swing.kind == "low":
            if last_low is not None and last_high is not None:
                if last_low.price > swing.price and trend != "bearish":
                    # Lower low — if we were bullish, this is CHoCH
                    if trend == "bullish":
                        breaks.append(StructureBreak(
                            index=swing.index,
                            price=swing.price,
                            kind="choch",
                            direction="bearish",
                            broken_level=last_low.price,
                            datetime=swing.datetime,
                        ))
                    trend = "bearish"
                elif last_low.price > swing.price and trend == "bearish":
                    # Lower low in bearish trend — BOS
                    breaks.append(StructureBreak(
                        index=swing.index,
                        price=swing.price,
                        kind="bos",
                        direction="bearish",
                        broken_level=last_low.price,
                        datetime=swing.datetime,
                    ))
            last_low = swing

    return breaks


def get_current_bias(df: pd.DataFrame) -> str:
    """
    Determine the current market bias based on recent structure.
    Returns "bullish", "bearish", or "neutral".
    """
    breaks = detect_structure(df)
    if not breaks:
        return "neutral"

    # Look at the last 3 structure breaks
    recent = breaks[-3:]
    bullish = sum(1 for b in recent if b.direction == "bullish")
    bearish = sum(1 for b in recent if b.direction == "bearish")

    if bullish > bearish:
        return "bullish"
    elif bearish > bullish:
        return "bearish"
    return "neutral"
