"""
SMC Sentiment Layer — Trend alignment, momentum bias, and contrarian positioning.

Combines multiple signals to confirm or deny trade setups.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Calculate MACD line and signal line."""
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    return macd, signal


def _calc_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period).mean()


def _trend_alignment(df: pd.DataFrame) -> str:
    """
    Determine trend direction from EMA stack.
    EMA 20 > 50 > 200 = bullish
    EMA 20 < 50 < 200 = bearish
    """
    close = df["close"]
    ema20 = _calc_ema(close, 20).iloc[-1]
    ema50 = _calc_ema(close, 50).iloc[-1]

    if len(df) >= 200:
        ema200 = _calc_ema(close, 200).iloc[-1]
        if ema20 > ema50 > ema200:
            return "bullish"
        elif ema20 < ema50 < ema200:
            return "bearish"
    else:
        # Use just 20/50 if not enough data for 200
        if ema20 > ema50:
            return "bullish"
        elif ema20 < ema50:
            return "bearish"

    return "neutral"


def _momentum_bias(df: pd.DataFrame) -> str:
    """
    Determine momentum direction from RSI and MACD.
    """
    close = df["close"]

    # RSI
    rsi = _calc_rsi(close).iloc[-1]

    # MACD
    macd, signal = _calc_macd(close)
    macd_val = macd.iloc[-1]
    signal_val = signal.iloc[-1]
    macd_above = macd_val > signal_val

    # Combine signals
    bullish_count = 0
    bearish_count = 0

    if rsi > 55:
        bullish_count += 1
    elif rsi < 45:
        bearish_count += 1

    if macd_above and macd_val > 0:
        bullish_count += 1
    elif not macd_above and macd_val < 0:
        bearish_count += 1

    if bullish_count > bearish_count:
        return "bullish"
    elif bearish_count > bullish_count:
        return "bearish"
    return "neutral"


def _retail_contrarian(df: pd.DataFrame) -> str:
    """
    Simple contrarian signal: if price has moved sharply in one direction
    recently, retail is likely piled in — fade them.

    Uses RSI extremes as a proxy for retail overexposure.
    """
    rsi = _calc_rsi(df["close"]).iloc[-1]

    if rsi > 70:
        # Retail is long, be contrarian = bearish
        return "bearish"
    elif rsi < 30:
        # Retail is short, be contrarian = bullish
        return "bullish"
    return "neutral"


def get_sentiment_bias(df: pd.DataFrame) -> dict:
    """
    Calculate overall sentiment bias by combining:
    1. Trend alignment (EMA stack)
    2. Momentum (RSI + MACD)
    3. Contrarian retail positioning (RSI extremes)

    Returns a dict with individual signals and overall bias.
    """
    trend = _trend_alignment(df)
    momentum = _momentum_bias(df)
    contrarian = _retail_contrarian(df)

    # Scoring: each signal votes
    score = 0
    for signal in [trend, momentum, contrarian]:
        if signal == "bullish":
            score += 1
        elif signal == "bearish":
            score -= 1

    if score >= 2:
        overall = "bullish"
    elif score <= -2:
        overall = "bearish"
    else:
        overall = "neutral"

    return {
        "trend": trend,
        "momentum": momentum,
        "contrarian": contrarian,
        "overall": overall,
        "score": score,
    }


def sentiment_confirms(df: pd.DataFrame, direction: str) -> bool:
    """
    Check if sentiment aligns with the proposed trade direction.
    Returns True if sentiment supports the trade, False otherwise.
    """
    bias = get_sentiment_bias(df)

    # Overall bias must match or be neutral
    if bias["overall"] == direction:
        return True

    # If overall is neutral, require at least trend alignment
    if bias["overall"] == "neutral" and bias["trend"] == direction:
        return True

    return False
