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


def fetch_yahoo(symbol: str, interval: str = "15m",
                range_str: str = "60d") -> pd.DataFrame:
    """
    Fetch OHLCV data from Yahoo Finance v8 chart API.

    Args:
        symbol: Yahoo ticker (e.g. "NQ=F", "GC=F", "ES=F")
        interval: Bar interval ("1m", "5m", "15m", "1h", "1d")
        range_str: Data range ("60d", "2y", etc.)

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    import json
    import urllib.request

    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&range={range_str}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    result = data["chart"]["result"][0]
    if "timestamp" not in result or result["timestamp"] is None:
        raise ValueError(f"No data returned for {symbol} ({interval}, {range_str})")

    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts, unit="s", utc=True),
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    })
    return df.dropna().reset_index(drop=True)


def fetch_yahoo_2yr(symbol: str, seed: int = 42) -> pd.DataFrame:
    """
    Fetch 2 years of data from Yahoo Finance.
    Uses 1-hour data and interpolates to 15-min bars.

    Args:
        symbol: Yahoo ticker
        seed: Random seed for interpolation

    Returns:
        DataFrame with ~45k 15-min bars
    """
    df_1h = fetch_yahoo(symbol, interval="1h", range_str="2y")
    rng = np.random.default_rng(seed)
    rows = []

    for _, bar in df_1h.iterrows():
        ts = bar["timestamp"]
        o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]
        bar_range = h - l
        if bar_range == 0:
            bar_range = max(0.01, abs(o) * 0.0001)

        bull = c >= o
        if bull:
            pivots = [
                o + (c - o) * rng.uniform(0.0, 0.3),
                l + (o - l) * rng.uniform(0.0, 0.4),
                o + (h - o) * rng.uniform(0.5, 0.9),
                c,
            ]
        else:
            pivots = [
                o + (h - o) * rng.uniform(0.3, 0.8),
                o - (o - c) * rng.uniform(0.2, 0.5),
                c + (l - c) * rng.uniform(-0.2, 0.3),
                c,
            ]

        sub_opens = [o, pivots[0], pivots[1], pivots[2]]
        sub_closes = pivots

        for i in range(4):
            sub_ts = ts + pd.Timedelta(minutes=15 * i)
            so, sc = sub_opens[i], sub_closes[i]
            sub_h = min(h, max(so, sc) + bar_range * rng.uniform(0.01, 0.15))
            sub_l = max(l, min(so, sc) - bar_range * rng.uniform(0.01, 0.15))
            sub_h = max(sub_h, so, sc)
            sub_l = min(sub_l, so, sc)
            sub_v = max(1, int(v / 4 * rng.uniform(0.5, 1.5))) if v and v > 0 else 0

            rows.append({
                "timestamp": sub_ts,
                "open": round(so, 2),
                "high": round(sub_h, 2),
                "low": round(sub_l, 2),
                "close": round(sc, 2),
                "volume": sub_v,
            })

    return pd.DataFrame(rows)


def fetch_yahoo_long(symbol: str, years: int = 20,
                      end_date: datetime = None) -> pd.DataFrame:
    """
    Fetch long-range daily OHLCV data from Yahoo Finance.

    Use this for 20+ years of daily bars. Note: Yahoo only provides
    intraday data (15m/1h) for 60 days / 2 years respectively - for
    longer intraday history, use load_csv_data() with paid providers.

    Args:
        symbol: Yahoo ticker (e.g. "NQ=F", "GC=F", "^GSPC")
        years: Years of history to fetch (default 20)
        end_date: End date (default: today)

    Returns:
        DataFrame with [timestamp, open, high, low, close, volume]
    """
    import json
    import urllib.request

    if end_date is None:
        end_date = datetime.now()
    start_date = end_date - timedelta(days=int(years * 365.25))

    period1 = int(start_date.timestamp())
    period2 = int(end_date.timestamp())

    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={period1}&period2={period2}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    result = data["chart"]["result"][0]
    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts, unit="s", utc=True),
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    }).dropna().reset_index(drop=True)

    return df


def load_csv_provider(filepath: str, provider: str = "auto") -> pd.DataFrame:
    """
    Load OHLCV CSV from common data providers.

    Supports:
    - Dukascopy:     "Gmt time" or "Local time" col, DD.MM.YYYY HH:MM:SS.fff format
    - FirstRateData: columns "DateTime,Open,High,Low,Close,Volume"
    - Polygon.io:    columns "timestamp,open,high,low,close,volume"
    - Databento:     columns "ts_event,open,high,low,close,volume"
    - HistData:      "DateTime,Open,High,Low,Close,Volume" (forex)
    - Generic:       any CSV with OHLCV columns (case-insensitive)

    Args:
        filepath: Path to CSV file
        provider: "dukascopy", "firstrate", "polygon", "databento", or "auto"

    Returns:
        DataFrame with standardized [timestamp, open, high, low, close, volume]
    """
    df = pd.read_csv(filepath)

    # Detect Dukascopy format BEFORE lowercase normalization
    is_dukascopy = any(c in df.columns for c in ["Gmt time", "Local time"]) or provider == "dukascopy"

    # Normalize column names (lowercase, strip spaces, unify)
    col_map = {}
    for c in df.columns:
        key = c.lower().strip()
        # Dukascopy uses "gmt time" or "local time"
        if key in ("gmt time", "local time"):
            key = "timestamp"
        col_map[c] = key
    df = df.rename(columns=col_map)

    # Map timestamp column variants
    ts_aliases = ["timestamp", "datetime", "date", "ts_event", "time", "ts"]
    ts_col = next((c for c in ts_aliases if c in df.columns), None)
    if ts_col is None:
        raise ValueError(f"No timestamp column found. Tried: {ts_aliases}. Got: {list(df.columns)}")

    df = df.rename(columns={ts_col: "timestamp"})

    # Dukascopy uses DD.MM.YYYY HH:MM:SS.fff (day-first, European)
    if is_dukascopy:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d.%m.%Y %H:%M:%S.%f",
                                         utc=True, errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])

    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}. Got: {list(df.columns)}")

    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Convert to numeric (handles string commas, quoted values)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.dropna().reset_index(drop=True)


def resample_bars(df: pd.DataFrame, interval: str = "15min") -> pd.DataFrame:
    """
    Resample OHLCV data to a different timeframe.

    Use this to convert Dukascopy tick/1-min data into 15-min bars.

    Args:
        df: DataFrame with [timestamp, open, high, low, close, volume]
        interval: Pandas offset alias ("1min", "5min", "15min", "1h", "1d")

    Returns:
        Resampled DataFrame

    Example:
        # Load Dukascopy 1-min data, resample to 15-min
        df = load_csv_provider("NQ_1min_dukascopy.csv")
        df15 = resample_bars(df, "15min")
    """
    df = df.copy()
    df = df.set_index("timestamp")

    resampled = df.resample(interval).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()

    return resampled.reset_index()



    df = generate_synthetic_data()
    print(f"Generated {len(df)} bars spanning {df['timestamp'].iloc[0].date()} to {df['timestamp'].iloc[-1].date()}")
    print(f"Price range: {df['low'].min():.2f} - {df['high'].max():.2f}")
    print(f"\nFirst 5 bars:")
    print(df.head())
    print(f"\nLast 5 bars:")
    print(df.tail())
