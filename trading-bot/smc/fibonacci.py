"""Fibonacci retracement and Optimal Trade Entry (OTE) zone calculation.

The OTE zone (0.618 - 0.786 Fibonacci retracement) is considered the
highest-probability entry zone in ICT methodology. When price retraces into
this zone within a trending market, it offers optimal risk-to-reward entries
aligned with institutional order flow.

Key concepts:
    - **Fibonacci levels**: Standard retracement levels (0.236, 0.382, 0.5,
      0.618, 0.786) measured from swing high to swing low (or vice versa).
    - **OTE zone**: The 0.618 to 0.786 retracement zone, where institutional
      traders are most likely to re-enter after a pullback.
    - **Premium zone**: Above the 0.5 level in a bearish retracement (above
      equilibrium -- expensive). Sell setups are favored here.
    - **Discount zone**: Below the 0.5 level in a bullish retracement (below
      equilibrium -- cheap). Buy setups are favored here.

Usage:
    >>> levels = get_fib_levels(swing_low=1.0800, swing_high=1.1000)
    >>> ote = calculate_ote_zone(swing_low=1.0800, swing_high=1.1000)
    >>> print(f"OTE zone: {ote['ote_low']:.4f} - {ote['ote_high']:.4f}")
"""

from typing import Dict

from .models import SwingPoint


# Standard Fibonacci retracement levels.
FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0]


def get_fib_levels(
    swing_low: float,
    swing_high: float,
) -> Dict[float, float]:
    """Calculate Fibonacci retracement price levels.

    Measures the retracement from a swing high back down toward the swing low.
    Level 0.0 is the swing high (no retracement) and level 1.0 is the swing
    low (full retracement).

    Args:
        swing_low: The lower price of the measured move.
        swing_high: The upper price of the measured move.

    Returns:
        Dict mapping each Fibonacci ratio to its price level.
    """
    diff = swing_high - swing_low
    return {level: swing_high - diff * level for level in FIB_LEVELS}


def calculate_ote_zone(
    swing_low: float,
    swing_high: float,
) -> Dict[str, float]:
    """Calculate the Optimal Trade Entry (OTE) zone.

    The OTE zone spans the 0.618 to 0.786 Fibonacci retracement of the
    measured move. For a bullish setup (retracement of an up-move), the
    OTE zone represents the discount area where buyers are expected to
    step in.

    Args:
        swing_low: The lower price of the measured move.
        swing_high: The upper price of the measured move.

    Returns:
        Dict with keys:
            - ``ote_high``: upper boundary (0.618 retracement price)
            - ``ote_low``: lower boundary (0.786 retracement price)
            - ``equilibrium``: the 0.5 level
    """
    diff = swing_high - swing_low
    return {
        "ote_high": swing_high - diff * 0.618,
        "ote_low": swing_high - diff * 0.786,
        "equilibrium": swing_high - diff * 0.5,
    }


def is_in_premium(
    price: float,
    swing_low: float,
    swing_high: float,
) -> bool:
    """Check if a price is in the premium zone (above equilibrium).

    The premium zone is above the 0.5 Fibonacci level. In a downtrend
    retracement, this is where price is considered expensive and short
    entries are favored.

    Args:
        price: The price to evaluate.
        swing_low: The lower price of the measured range.
        swing_high: The upper price of the measured range.

    Returns:
        True if price is in the premium zone.
    """
    equilibrium = (swing_high + swing_low) / 2.0
    return price > equilibrium


def is_in_discount(
    price: float,
    swing_low: float,
    swing_high: float,
) -> bool:
    """Check if a price is in the discount zone (below equilibrium).

    The discount zone is below the 0.5 Fibonacci level. In an uptrend
    retracement, this is where price is considered cheap and long entries
    are favored.

    Args:
        price: The price to evaluate.
        swing_low: The lower price of the measured range.
        swing_high: The upper price of the measured range.

    Returns:
        True if price is in the discount zone.
    """
    equilibrium = (swing_high + swing_low) / 2.0
    return price < equilibrium
