"""Smart Money Concepts (SMC) Analysis Library.

This library provides the core technical analysis engine used by scalper and
swing trading bots. It implements ICT (Inner Circle Trader) methodology
including market structure analysis, order block detection, fair value gap
identification, liquidity mapping, Fibonacci/OTE zones, and confluence scoring.

Modules:
    market_structure: Swing point detection, BOS/CHoCH, trend classification.
    order_blocks:     Institutional order block identification and mitigation.
    fair_value_gaps:  Fair value gap (imbalance) detection and fill tracking.
    liquidity:        Liquidity pool mapping and sweep detection.
    fibonacci:        Fibonacci retracements and Optimal Trade Entry zones.
    confluence:       Multi-factor confluence scoring and trade setup generation.
"""

from .models import (
    OHLCV,
    FairValueGap,
    LiquidityLevel,
    OrderBlock,
    SwingPoint,
    TradeSetup,
)

from .market_structure import (
    classify_structure,
    detect_bos,
    detect_choch,
    detect_swing_points,
    get_trend,
)

from .order_blocks import (
    check_mitigation,
    find_order_blocks,
    is_price_in_ob,
)

from .fair_value_gaps import (
    check_fvg_fill,
    find_fvg,
    is_price_in_fvg,
)

from .liquidity import (
    detect_liquidity_sweep,
    find_equal_levels,
    find_swing_liquidity,
)

from .fibonacci import (
    calculate_ote_zone,
    get_fib_levels,
    is_in_discount,
    is_in_premium,
)

from .confluence import (
    calculate_sl_tp,
    find_entry,
    score_setup,
)

__all__ = [
    # Models
    "OHLCV",
    "SwingPoint",
    "OrderBlock",
    "FairValueGap",
    "LiquidityLevel",
    "TradeSetup",
    # Market structure
    "detect_swing_points",
    "classify_structure",
    "detect_bos",
    "detect_choch",
    "get_trend",
    # Order blocks
    "find_order_blocks",
    "check_mitigation",
    "is_price_in_ob",
    # Fair value gaps
    "find_fvg",
    "check_fvg_fill",
    "is_price_in_fvg",
    # Liquidity
    "find_equal_levels",
    "find_swing_liquidity",
    "detect_liquidity_sweep",
    # Fibonacci
    "calculate_ote_zone",
    "is_in_premium",
    "is_in_discount",
    "get_fib_levels",
    # Confluence
    "score_setup",
    "find_entry",
    "calculate_sl_tp",
]
