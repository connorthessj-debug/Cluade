"""Fibonacci retracement levels and Optimal Trade Entry (OTE) zones.

Fibonacci ratios derived from the golden ratio (1.618) are used extensively
in SMC/ICT methodology to identify high-probability retracement zones where
institutional orders are likely resting.

Key concepts:
    - **Fibonacci retracement**: Horizontal lines at key ratios (23.6%,
      38.2%, 50%, 61.8%, 70.5%, 78.6%) between a swing high and swing low,
      indicating potential support/resistance levels during a pullback.
    - **OTE (Optimal Trade Entry)**: The zone between the 61.8% and 78.6%
      retracement levels. This is ICT's preferred entry zone because it
      offers the best risk-to-reward ratio while still having a high
      probability of holding as support/resistance.
    - **Premium/Discount**: The 50% level divides the range into premium
      (above 50%, expensive, good for selling) and discount (below 50%,
      cheap, good for buying).

Usage:
    >>> ote = calculate_ote_zone(swing_high=50000, swing_low=48000, direction='bullish')
    >>> print(f"OTE zone: {ote['ote_low']:.2f} - {ote['ote_high']:.2f}")
    >>> if is_in_discount(current_price, 50000, 48000):
    ...     print("Price is in discount zone - look for longs")
"""

import numpy as np


# Standard Fibonacci retracement ratios used in ICT/SMC analysis
_FIB_RATIOS = {
    0.0: 0.0,
    0.236: 0.236,
    0.382: 0.382,
    0.5: 0.5,
    0.618: 0.618,
    0.705: 0.705,
    0.786: 0.786,
    1.0: 1.0,
}


def calculate_ote_zone(
    swing_high: float,
    swing_low: float,
    direction: str,
) -> dict:
    """Calculate the Optimal Trade Entry (OTE) zone.

    The OTE zone sits between the 61.8% and 78.6% Fibonacci retracement
    levels and represents ICT's preferred entry area. It provides an
    excellent risk-to-reward ratio because entries near the extremes of
    the retracement zone allow tight stop losses while targeting the full
    continuation of the trend.

    For a **bullish** retracement (buying the dip after an up-move):
        - Price retraces downward from swing_high toward swing_low.
        - The 0.618 level = swing_high - range * 0.618 (shallower retracement).
        - The 0.786 level = swing_high - range * 0.786 (deeper retracement).
        - OTE zone: from 0.786 level (bottom) to 0.618 level (top).
        - Traders look to buy within this zone.

    For a **bearish** retracement (selling the rally after a down-move):
        - Price retraces upward from swing_low toward swing_high.
        - The 0.618 level = swing_low + range * 0.618 (shallower retracement).
        - The 0.786 level = swing_low + range * 0.786 (deeper retracement).
        - OTE zone: from 0.618 level (bottom) to 0.786 level (top).
        - Traders look to sell within this zone.

    Args:
        swing_high: The swing high price.
        swing_low: The swing low price.
        direction: 'bullish' (buying retracement) or 'bearish' (selling rally).

    Returns:
        Dict with keys:
            - ``ote_high``: Upper boundary of the OTE zone.
            - ``ote_low``: Lower boundary of the OTE zone.
            - ``premium_discount_line``: The 50% level dividing premium/discount.
            - ``direction``: The trade direction.

    Raises:
        ValueError: If swing_high <= swing_low or direction is invalid.
    """
    if swing_high <= swing_low:
        raise ValueError(
            f"swing_high ({swing_high}) must be greater than swing_low ({swing_low})"
        )

    if direction not in ('bullish', 'bearish'):
        raise ValueError(f"direction must be 'bullish' or 'bearish', got '{direction}'")

    price_range = swing_high - swing_low
    midpoint = swing_low + price_range * 0.5

    if direction == 'bullish':
        # Retracement from high: price pulled back, looking to buy
        level_618 = swing_high - price_range * 0.618
        level_786 = swing_high - price_range * 0.786
        ote_high = level_618  # Shallower (higher price)
        ote_low = level_786   # Deeper (lower price)
    else:
        # Retracement from low: price rallied back, looking to sell
        level_618 = swing_low + price_range * 0.618
        level_786 = swing_low + price_range * 0.786
        ote_high = level_786  # Deeper retracement (higher price)
        ote_low = level_618   # Shallower (lower price)

    return {
        'ote_high': float(ote_high),
        'ote_low': float(ote_low),
        'premium_discount_line': float(midpoint),
        'direction': direction,
    }


def is_in_premium(price: float, swing_high: float, swing_low: float) -> bool:
    """Check if a price is in the premium zone (above 50% of the range).

    The premium zone is the upper half of the swing range. Prices in this
    zone are considered "expensive" and are better suited for selling
    (shorting) rather than buying.

    In SMC, smart money sells in premium and buys in discount.

    Args:
        price: Current price to evaluate.
        swing_high: The swing high defining the range.
        swing_low: The swing low defining the range.

    Returns:
        True if the price is above the 50% level of the range.
    """
    midpoint = swing_low + (swing_high - swing_low) * 0.5
    return price > midpoint


def is_in_discount(price: float, swing_high: float, swing_low: float) -> bool:
    """Check if a price is in the discount zone (below 50% of the range).

    The discount zone is the lower half of the swing range. Prices in this
    zone are considered "cheap" and are better suited for buying (going long)
    rather than selling.

    In SMC, smart money buys in discount and sells in premium.

    Args:
        price: Current price to evaluate.
        swing_high: The swing high defining the range.
        swing_low: The swing low defining the range.

    Returns:
        True if the price is below the 50% level of the range.
    """
    midpoint = swing_low + (swing_high - swing_low) * 0.5
    return price < midpoint


def get_fib_levels(swing_high: float, swing_low: float) -> dict:
    """Calculate all standard Fibonacci retracement levels.

    Computes horizontal price levels at each standard Fibonacci ratio
    between the swing high and swing low. These levels are measured as
    retracements from the high (i.e., from top down):

        level_price = swing_high - (swing_high - swing_low) * ratio

    So the 0.0 level equals swing_high (no retracement) and the 1.0
    level equals swing_low (full retracement).

    Standard ratios: 0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0

    Args:
        swing_high: The swing high price.
        swing_low: The swing low price.

    Returns:
        Dict mapping ratio (float) to price level (float).
        Example: {0.0: 50000.0, 0.236: 49528.0, ..., 1.0: 48000.0}

    Raises:
        ValueError: If swing_high <= swing_low.
    """
    if swing_high <= swing_low:
        raise ValueError(
            f"swing_high ({swing_high}) must be greater than swing_low ({swing_low})"
        )

    price_range = swing_high - swing_low
    levels: dict = {}

    for ratio in _FIB_RATIOS:
        levels[ratio] = float(swing_high - price_range * ratio)

    return levels
