"""
Shared data models for the Smart Money Concepts (SMC) analysis library.

These dataclasses represent the core data structures used across all SMC
modules for market structure analysis, order block detection, fair value
gap identification, liquidity mapping, and confluence scoring.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class OHLCV:
    """Represents a single candlestick (Open-High-Low-Close-Volume) bar."""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SwingPoint:
    """A local price extreme (swing high or swing low).

    Swing highs are local maxima where surrounding bars have lower highs.
    Swing lows are local minima where surrounding bars have higher lows.
    """
    index: int
    price: float
    type: str       # 'high' or 'low'
    timestamp: float


@dataclass
class OrderBlock:
    """An institutional order block zone.

    Bullish OB: the last bearish candle before a bullish impulse move (BOS).
    Bearish OB: the last bullish candle before a bearish impulse move (BOS).
    These zones often act as support/resistance where institutions placed orders.
    """
    type: str           # 'bullish' or 'bearish'
    high: float
    low: float
    timeframe: str
    created_at: float
    mitigated: bool = False


@dataclass
class FairValueGap:
    """A Fair Value Gap (imbalance) in price action.

    Bullish FVG: gap between candle[i-2].high and candle[i].low where the
    middle candle's body expanded rapidly, leaving unfilled price space.
    Bearish FVG: gap between candle[i-2].low and candle[i].high.
    """
    type: str           # 'bullish' or 'bearish'
    high: float
    low: float
    timeframe: str
    created_at: float
    fill_status: str = 'unfilled'


@dataclass
class LiquidityLevel:
    """A liquidity pool at a given price level.

    Equal highs/lows cluster stop-loss orders, creating liquidity targets
    that institutional players often sweep before reversing price.
    """
    price: float
    type: str           # 'high' or 'low'
    strength: int
    swept: bool = False


@dataclass
class TradeSetup:
    """A scored trade setup derived from confluence of SMC signals.

    The confluence_score (0-100) reflects how many SMC factors align at the
    entry zone. Higher scores indicate higher-probability setups.
    """
    signal_type: str
    direction: str          # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    confluence_score: float
    components: Dict = field(default_factory=dict)
