"""
Synthetic MNQ 15-min OHLCV data generator with realistic market regimes.
Generates 2+ years of data covering all major market conditions.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# MNQ tick size is $0.25, point value $2/point ($0.50/tick)
TICK_SIZE = 0.25
POINT_VALUE = 2.0

# Trading sessions (ET)
RTH_START_HOUR = 9   # 9:30 ET
RTH_START_MIN = 30
RTH_END_HOUR = 16    # 16:00 ET
RTH_END_MIN = 0

# Regime durations in trading days (approximate)
REGIME_CONFIG = {
    "strong_bull":       {"days": (20, 60), "drift": (0.0008, 0.0020), "vol": (0.003, 0.006)},
    "strong_bear":       {"days": (15, 45), "drift": (-0.0020, -0.0008), "vol": (0.004, 0.008)},
    "ranging":           {"days": (15, 40), "drift": (-0.0002, 0.0002), "vol": (0.002, 0.004)},
    "high_volatility":   {"days": (5, 15),  "drift": (-0.0010, 0.0010), "vol": (0.008, 0.015)},
    "low_volatility":    {"days": (10, 30), "drift": (-0.0001, 0.0001), "vol": (0.001, 0.002)},
    "reversal":          {"days": (10, 25), "drift": (-0.0005, 0.0005), "vol": (0.004, 0.008)},
}

REGIME_NAMES = list(REGIME_CONFIG.keys())


def _generate_regime_bars(regime: str, num_bars: int, start_price: float,
                          rng: np.random.Generator) -> np.ndarray:
    """Generate OHLCV bars for a single market regime."""
    cfg = REGIME_CONFIG[regime]
    drift = rng.uniform(*cfg["drift"])
    vol = rng.uniform(*cfg["vol"])

    # For reversals, flip drift midway
    if regime == "reversal":
        mid = num_bars // 2
        drifts = np.full(num_bars, drift)
        drifts[mid:] = -drift * rng.uniform(1.2, 2.0)
    elif regime == "high_volatility":
        # Add occasional spikes (FOMC-style)
        drifts = np.full(num_bars, drift)
        spike_indices = rng.choice(num_bars, size=max(1, num_bars // 20), replace=False)
        drifts[spike_indices] = rng.choice([-1, 1], size=len(spike_indices)) * vol * rng.uniform(2.0, 5.0, size=len(spike_indices))
    else:
        drifts = np.full(num_bars, drift)

    closes = np.zeros(num_bars)
    opens = np.zeros(num_bars)
    highs = np.zeros(num_bars)
    lows = np.zeros(num_bars)
    volumes = np.zeros(num_bars)

    price = start_price

    for i in range(num_bars):
        open_price = price
        # Intra-bar random walk
        returns = drifts[i] + vol * rng.standard_normal()
        close_price = open_price * (1 + returns)

        # Generate realistic high/low
        bar_range = abs(close_price - open_price)
        extra_wick = vol * open_price * rng.uniform(0.1, 0.8)

        if close_price >= open_price:
            high_price = close_price + extra_wick * rng.uniform(0.0, 1.0)
            low_price = open_price - extra_wick * rng.uniform(0.2, 1.0)
        else:
            high_price = open_price + extra_wick * rng.uniform(0.2, 1.0)
            low_price = close_price - extra_wick * rng.uniform(0.0, 1.0)

        # Snap to tick size
        open_price = round(open_price / TICK_SIZE) * TICK_SIZE
        close_price = round(close_price / TICK_SIZE) * TICK_SIZE
        high_price = round(high_price / TICK_SIZE) * TICK_SIZE
        low_price = round(low_price / TICK_SIZE) * TICK_SIZE

        # Ensure OHLC consistency
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        # Volume: higher in trends and volatility, lower in compression
        base_vol = 500
        if regime == "high_volatility":
            base_vol = 2000
        elif regime == "low_volatility":
            base_vol = 200
        elif regime in ("strong_bull", "strong_bear"):
            base_vol = 800
        volume = int(base_vol * rng.uniform(0.5, 2.5))

        opens[i] = open_price
        highs[i] = high_price
        lows[i] = low_price
        closes[i] = close_price
        volumes[i] = volume

        price = close_price

    return np.column_stack([opens, highs, lows, closes, volumes])


def _generate_session_timestamps(start_date: datetime, num_trading_days: int) -> list:
    """Generate 15-min bar timestamps for RTH sessions only."""
    timestamps = []
    current = start_date

    days_generated = 0
    while days_generated < num_trading_days:
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        # RTH session: 9:30 to 16:00 ET = 26 bars of 15 min
        session_start = current.replace(hour=RTH_START_HOUR, minute=RTH_START_MIN, second=0, microsecond=0)
        bar_time = session_start

        while bar_time.hour < RTH_END_HOUR or (bar_time.hour == RTH_END_HOUR and bar_time.minute == 0):
            if bar_time.hour == RTH_END_HOUR and bar_time.minute > 0:
                break
            timestamps.append(bar_time)
            bar_time += timedelta(minutes=15)

        days_generated += 1
        current += timedelta(days=1)

    return timestamps


def generate_synthetic_data(years: float = 2.5, start_price: float = 15000.0,
                            seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic MNQ 15-min OHLCV data.

    Args:
        years: Number of years of data to generate (default 2.5)
        start_price: Starting price level (default 15000.0)
        seed: Random seed for reproducibility

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    rng = np.random.default_rng(seed)

    # ~252 trading days/year, 26 bars/day (RTH 9:30-16:00 in 15-min)
    total_trading_days = int(years * 252)
    bars_per_day = 26

    # Generate timestamps
    start_date = datetime(2024, 1, 2)  # First trading day of 2024
    timestamps = _generate_session_timestamps(start_date, total_trading_days)

    # Generate price data by cycling through regimes
    all_bars = []
    price = start_price
    bars_remaining = len(timestamps)
    regime_idx = 0

    while bars_remaining > 0:
        regime = REGIME_NAMES[regime_idx % len(REGIME_NAMES)]
        cfg = REGIME_CONFIG[regime]

        # Random regime duration
        regime_days = rng.integers(cfg["days"][0], cfg["days"][1] + 1)
        regime_bars = min(regime_days * bars_per_day, bars_remaining)

        bars = _generate_regime_bars(regime, regime_bars, price, rng)
        all_bars.append(bars)

        price = bars[-1, 3]  # Last close
        bars_remaining -= regime_bars
        regime_idx += 1

        # Shuffle regime order occasionally for variety
        if regime_idx % len(REGIME_NAMES) == 0:
            rng.shuffle(REGIME_NAMES)

    ohlcv = np.vstack(all_bars)

    # Add session gaps (overnight gaps between days)
    day_starts = []
    for i in range(1, len(timestamps)):
        if timestamps[i].date() != timestamps[i - 1].date():
            day_starts.append(i)

    for idx in day_starts:
        gap_pct = rng.normal(0.0, 0.003)  # ~0.3% avg overnight gap
        gap_factor = 1 + gap_pct
        ohlcv[idx, 0] = round(ohlcv[idx - 1, 3] * gap_factor / TICK_SIZE) * TICK_SIZE
        # Adjust high/low if open is outside them
        ohlcv[idx, 1] = max(ohlcv[idx, 1], ohlcv[idx, 0])
        ohlcv[idx, 2] = min(ohlcv[idx, 2], ohlcv[idx, 0])

    # Trim to match timestamps
    n = min(len(timestamps), len(ohlcv))
    timestamps = timestamps[:n]
    ohlcv = ohlcv[:n]

    df = pd.DataFrame({
        "timestamp": timestamps[:n],
        "open": ohlcv[:, 0],
        "high": ohlcv[:, 1],
        "low": ohlcv[:, 2],
        "close": ohlcv[:, 3],
        "volume": ohlcv[:, 4].astype(int),
    })

    return df


def load_csv_data(filepath: str) -> pd.DataFrame:
    """Load OHLCV data from a CSV file."""
    df = pd.read_csv(filepath, parse_dates=["timestamp"])
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    return df


if __name__ == "__main__":
    df = generate_synthetic_data()
    print(f"Generated {len(df)} bars spanning {df['timestamp'].iloc[0].date()} to {df['timestamp'].iloc[-1].date()}")
    print(f"Price range: {df['low'].min():.2f} - {df['high'].max():.2f}")
    print(f"\nFirst 5 bars:")
    print(df.head())
    print(f"\nLast 5 bars:")
    print(df.tail())
