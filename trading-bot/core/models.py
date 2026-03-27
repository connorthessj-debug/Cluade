"""Data models for the trading bot system.

All core domain objects are defined as dataclasses for clarity, immutability
hints, and easy serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
import uuid


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Market data models
# ---------------------------------------------------------------------------

@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderBook:
    bids: List[Tuple[float, float]]  # (price, amount)
    asks: List[Tuple[float, float]]
    timestamp: datetime
    exchange: str
    symbol: str


# ---------------------------------------------------------------------------
# SMC / ICT structure models
# ---------------------------------------------------------------------------

@dataclass
class SwingPoint:
    index: int
    price: float
    type: Literal["high", "low"]
    timestamp: datetime


@dataclass
class OrderBlock:
    type: Literal["bullish", "bearish"]
    high: float
    low: float
    timeframe: str
    created_at: datetime = field(default_factory=_now)
    mitigated: bool = False


@dataclass
class FairValueGap:
    type: Literal["bullish", "bearish"]
    high: float
    low: float
    timeframe: str
    created_at: datetime = field(default_factory=_now)
    fill_status: float = 0.0  # 0.0 = unfilled, 1.0 = fully filled


@dataclass
class LiquidityLevel:
    price: float
    type: Literal["buy_side", "sell_side"]
    strength: float = 1.0
    swept: bool = False


@dataclass
class TradeSetup:
    signal_type: str
    direction: Literal["long", "short"]
    entry_price: float
    stop_loss: float
    take_profit: float
    confluence_score: float
    components: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trading records
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    id: str = field(default_factory=_new_id)
    bot_name: str = ""
    exchange: str = ""
    symbol: str = ""
    side: Literal["buy", "sell"] = "buy"
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    amount: float = 0.0
    pnl: Optional[float] = None
    fees: float = 0.0
    entry_time: datetime = field(default_factory=_now)
    exit_time: Optional[datetime] = None
    setup_type: str = ""
    notes: str = ""
    r_multiple: Optional[float] = None


@dataclass
class Signal:
    id: str = field(default_factory=_new_id)
    bot_name: str = ""
    symbol: str = ""
    timeframe: str = ""
    signal_type: str = ""
    score: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


@dataclass
class Position:
    id: str = field(default_factory=_new_id)
    bot_name: str = ""
    exchange: str = ""
    symbol: str = ""
    side: Literal["buy", "sell"] = "buy"
    entry_price: float = 0.0
    amount: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: datetime = field(default_factory=_now)
    status: Literal["open", "closed", "partial"] = "open"
