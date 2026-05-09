"""
fetch_intraday.py — unified multi-resolution OHLCV fetcher

Usage:
    python3 scripts/fetch_intraday.py AAPL 1h 180
    python3 scripts/fetch_intraday.py BTCUSDT 1m 30

Outputs canonical JSON to stdout. Consumed by wfa_optimizer.py.
"""

import sys
import json
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YF_MAX_DAYS = {"1m": 7, "5m": 60, "15m": 60, "1h": 730, "1d": 1825}

BARS_PER_YEAR = {
    "1m":  525600,   # crypto / 24-7
    "5m":  105120,
    "15m":  35040,
    "1h":    8760,
    "1d":     252,
}

BINANCE_SPOT_BASE    = "https://api.binance.com"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

CRYPTO_SUFFIXES = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB")
CRYPTO_BASES    = {
    "BTC", "ETH", "BNB", "SOL", "ADA", "DOT", "DOGE", "AVAX",
    "MATIC", "LINK", "UNI", "XRP", "LTC", "BCH", "ATOM", "XLM",
}


# ---------------------------------------------------------------------------
# Asset detection
# ---------------------------------------------------------------------------

def _is_crypto(symbol: str) -> bool:
    s = symbol.upper()
    if any(s.endswith(suf) for suf in CRYPTO_SUFFIXES):
        return True
    # bare base like "BTC" or "ETH"
    return s in CRYPTO_BASES


# ---------------------------------------------------------------------------
# yfinance fetcher
# ---------------------------------------------------------------------------

def fetch_yfinance(symbol: str, interval: str, lookback_days: int | None = None) -> dict:
    max_days = YF_MAX_DAYS.get(interval, 1825)
    if lookback_days is None:
        lookback_days = max_days
    clamped = min(lookback_days, max_days)
    warning = None
    if clamped < lookback_days:
        warning = (
            f"yfinance {interval} limited to {max_days} days; "
            f"requested {lookback_days} days, returning {clamped}"
        )

    try:
        if interval == "1d":
            period = "5y"
            df = yf.download(symbol, period=period, interval="1d",
                             progress=False, auto_adjust=True)
        else:
            end   = datetime.now(timezone.utc)
            start = end - timedelta(days=clamped)
            df = yf.download(symbol,
                             start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"),
                             interval=interval,
                             progress=False, auto_adjust=True)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()

        if df.empty:
            return {"symbol": symbol, "interval": interval, "bars": [],
                    "bar_count": 0, "start": None, "end": None,
                    "source": "yfinance", "error": "no data returned"}

        bars = _df_to_bars(df)
        return {
            "symbol": symbol,
            "interval": interval,
            "bars": bars,
            "bar_count": len(bars),
            "start": bars[0]["t_iso"] if bars else None,
            "end":   bars[-1]["t_iso"] if bars else None,
            "source": "yfinance",
            "warning": warning,
            "error": None,
        }

    except Exception as e:
        return {"symbol": symbol, "interval": interval, "bars": [],
                "bar_count": 0, "start": None, "end": None,
                "source": "yfinance", "error": str(e)}


# ---------------------------------------------------------------------------
# Binance paginated fetcher
# ---------------------------------------------------------------------------

def _binance_klines_page(
    base_url: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
) -> list:
    endpoint = f"{base_url}/fapi/v1/klines" if "fapi" in base_url else f"{base_url}/api/v3/klines"
    params = {
        "symbol":    symbol.upper(),
        "interval":  interval,
        "startTime": int(start_ms),
        "endTime":   int(end_ms),
        "limit":     limit,
    }
    resp = requests.get(endpoint, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_binance(
    symbol: str,
    interval: str,
    lookback_days: int = 365,
    futures: bool = False,
) -> dict:
    base_url = BINANCE_FUTURES_BASE if futures else BINANCE_SPOT_BASE
    source   = "binance_futures" if futures else "binance_spot"

    now_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp() * 1000)
    end_ms   = now_ms

    all_raw: list = []
    try:
        while start_ms < end_ms:
            page = _binance_klines_page(base_url, symbol, interval, start_ms, end_ms)
            if not page:
                break
            all_raw.extend(page)
            last_open_ms = int(page[-1][0])
            if last_open_ms <= start_ms:
                break
            start_ms = last_open_ms + 1
            if len(page) < 1000:
                break
            time.sleep(0.05)  # gentle rate-limit

    except Exception as e:
        # fall back to spot if futures fails
        if futures:
            return fetch_binance(symbol, interval, lookback_days, futures=False)
        return {"symbol": symbol, "interval": interval, "bars": [],
                "bar_count": 0, "start": None, "end": None,
                "source": source, "error": str(e)}

    if not all_raw:
        return {"symbol": symbol, "interval": interval, "bars": [],
                "bar_count": 0, "start": None, "end": None,
                "source": source, "error": "no data returned from Binance"}

    bars = []
    for k in all_raw:
        t_ms = int(k[0])
        bars.append({
            "t":     t_ms,
            "t_iso": datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat(),
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })

    # deduplicate by timestamp
    seen: set = set()
    unique = []
    for b in bars:
        if b["t"] not in seen:
            seen.add(b["t"])
            unique.append(b)
    unique.sort(key=lambda x: x["t"])

    return {
        "symbol":    symbol,
        "interval":  interval,
        "bars":      unique,
        "bar_count": len(unique),
        "start":     unique[0]["t_iso"]  if unique else None,
        "end":       unique[-1]["t_iso"] if unique else None,
        "source":    source,
        "warning":   None,
        "error":     None,
    }


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def fetch_ohlcv(
    symbol: str,
    interval: str = "1d",
    lookback_days: int | None = None,
) -> dict:
    """
    Dispatch to the best available source for the given symbol and interval.
    Crypto + intraday → Binance (much longer history than yfinance).
    Everything else → yfinance.
    Falls back to yfinance on Binance error.
    """
    if _is_crypto(symbol) and interval != "1d":
        days = lookback_days or 365
        result = fetch_binance(symbol, interval, lookback_days=days)
        if result.get("error"):
            # fallback
            result = fetch_yfinance(symbol, interval, days)
            result["fallback"] = True
        return result
    return fetch_yfinance(symbol, interval, lookback_days)


# ---------------------------------------------------------------------------
# DataFrame conversion
# ---------------------------------------------------------------------------

def _df_to_bars(df: pd.DataFrame) -> list[dict]:
    bars = []
    for ts, row in df.iterrows():
        if hasattr(ts, "timestamp"):
            t_ms = int(ts.timestamp() * 1000)
            t_iso = ts.isoformat()
        else:
            t_ms = int(pd.Timestamp(ts).timestamp() * 1000)
            t_iso = str(ts)
        bars.append({
            "t":     t_ms,
            "t_iso": t_iso,
            "o": float(row.get("Open",  row.get("open",  0))),
            "h": float(row.get("High",  row.get("high",  0))),
            "l": float(row.get("Low",   row.get("low",   0))),
            "c": float(row.get("Close", row.get("close", 0))),
            "v": float(row.get("Volume",row.get("volume",0))),
        })
    return bars


def to_dataframe(fetched: dict) -> pd.DataFrame:
    """
    Convert canonical fetch dict → DataFrame with Open/High/Low/Close/Volume
    columns and a UTC DatetimeIndex. Used by wfa_optimizer.py.
    """
    bars = fetched.get("bars", [])
    if not bars:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    rows = []
    for b in bars:
        rows.append({
            "Open":   b["o"],
            "High":   b["h"],
            "Low":    b["l"],
            "Close":  b["c"],
            "Volume": b["v"],
        })
    idx = pd.to_datetime([b["t_iso"] for b in bars], utc=True)
    df  = pd.DataFrame(rows, index=idx)
    return df.sort_index().dropna()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch OHLCV data")
    parser.add_argument("symbol",   help="Ticker symbol (e.g. AAPL, BTCUSDT)")
    parser.add_argument("interval", nargs="?", default="1d",
                        help="Bar interval: 1m|5m|15m|1h|1d (default: 1d)")
    parser.add_argument("days",     nargs="?", type=int, default=None,
                        help="Lookback days (default: max for interval)")
    args = parser.parse_args()

    result = fetch_ohlcv(args.symbol, args.interval, args.days)

    # strip t_iso from bars for cleaner output (keep t, o, h, l, c, v)
    for b in result.get("bars", []):
        b.pop("t_iso", None)

    print(json.dumps(result, indent=2))
