#!/usr/bin/env python3
"""
Fetch historical USDC-USD candle data from Coinbase Advanced Trade API.

Usage:
    python fetch_data.py                    # Fetch last 30 days of 1-minute candles
    python fetch_data.py --days 90          # Fetch last 90 days
    python fetch_data.py --granularity ONE_HOUR --days 365

Requires COINBASE_API_KEY and COINBASE_API_SECRET in ../.env or environment.
Falls back to CoinGecko daily data if Coinbase API credentials are not available.
"""

import os
import sys
import time
import json
import csv
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import jwt
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("ERROR: 'PyJWT' and 'cryptography' required. Run: pip install PyJWT cryptography")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "usdc_usd_candles.csv"

COINBASE_BASE_URL = "https://api.coinbase.com"
PRODUCT_ID = "USDC-USD"

GRANULARITY_SECONDS = {
    "ONE_MINUTE": 60,
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "TWO_HOUR": 7200,
    "SIX_HOUR": 21600,
    "ONE_DAY": 86400,
}

MAX_CANDLES_PER_REQUEST = 300


# ---------------------------------------------------------------------------
# Coinbase Auth
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file from parent directory if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def get_coinbase_credentials():
    """Return (api_key, api_secret) or (None, None) if not configured."""
    load_env()
    api_key = os.environ.get("COINBASE_API_KEY")
    api_secret = os.environ.get("COINBASE_API_SECRET")
    if api_key and api_secret:
        # Unescape literal \n to actual newlines in the PEM key
        api_secret = api_secret.replace("\\n", "\n")
        return api_key, api_secret
    return None, None


def build_jwt(api_key, api_secret, method, path):
    """
    Build a JWT token for Coinbase Advanced Trade API (CDP API key auth).
    See: https://docs.cdp.coinbase.com/advanced-trade/docs/rest-api-auth
    """
    uri = f"{method.upper()} {COINBASE_BASE_URL.replace('https://', '')}{path}"

    now = int(time.time())
    payload = {
        "sub": api_key,
        "iss": "cdp",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + 120,  # 2 minute expiry
        "uris": [uri],
    }

    # Load the EC private key
    private_key = serialization.load_pem_private_key(
        api_secret.encode("utf-8"), password=None
    )

    token = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": api_key, "nonce": secrets.token_hex(16), "typ": "JWT"},
    )
    return token


def coinbase_get(path, params=None, api_key=None, api_secret=None):
    """Authenticated GET request to Coinbase API using JWT."""
    query = ""
    if params:
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    full_path = path + query

    token = build_jwt(api_key, api_secret, "GET", path)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.get(COINBASE_BASE_URL + full_path, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Coinbase candle fetcher
# ---------------------------------------------------------------------------

def fetch_coinbase_candles(days=30, granularity="ONE_MINUTE"):
    """
    Fetch historical candles from Coinbase Advanced Trade API.
    Paginates backward in time, 300 candles per request.
    """
    api_key, api_secret = get_coinbase_credentials()
    if not api_key:
        return None

    gran_seconds = GRANULARITY_SECONDS.get(granularity)
    if not gran_seconds:
        print(f"ERROR: Unknown granularity '{granularity}'")
        print(f"Valid options: {', '.join(GRANULARITY_SECONDS.keys())}")
        sys.exit(1)

    end_time = int(time.time())
    start_time = end_time - (days * 86400)

    all_candles = []
    cursor_end = end_time
    request_count = 0
    total_window = (end_time - start_time) // gran_seconds

    print(f"Fetching {PRODUCT_ID} candles from Coinbase API...")
    print(f"  Granularity: {granularity} ({gran_seconds}s)")
    print(f"  Date range: {datetime.fromtimestamp(start_time, tz=timezone.utc).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(end_time, tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"  Expected candles: ~{total_window}")
    print()

    while cursor_end > start_time:
        cursor_start = max(cursor_end - (MAX_CANDLES_PER_REQUEST * gran_seconds), start_time)

        params = {
            "start": str(cursor_start),
            "end": str(cursor_end),
            "granularity": granularity,
        }

        try:
            data = coinbase_get(
                f"/api/v3/brokerage/products/{PRODUCT_ID}/candles",
                params=params,
                api_key=api_key,
                api_secret=api_secret,
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("  Rate limited, waiting 2s...")
                time.sleep(2)
                continue
            elif e.response.status_code in (401, 403):
                print(f"  Auth error ({e.response.status_code}): Check your API key/secret")
                return None
            else:
                body = ""
                try:
                    body = e.response.text
                except Exception:
                    pass
                print(f"\n  HTTP {e.response.status_code}: {body}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"  Network error: {e}")
            time.sleep(1)
            continue

        candles = data.get("candles", [])
        if not candles:
            cursor_end = cursor_start
            continue

        all_candles.extend(candles)
        request_count += 1

        # Progress
        fetched_pct = min(100, ((end_time - cursor_start) / (end_time - start_time)) * 100)
        print(f"\r  Progress: {fetched_pct:.0f}% | {len(all_candles)} candles | {request_count} requests", end="", flush=True)

        cursor_end = cursor_start

        # Respect rate limits: 10 req/sec for public, but be conservative
        if request_count % 8 == 0:
            time.sleep(1)

    print(f"\n  Done! Fetched {len(all_candles)} candles in {request_count} requests.\n")

    # Deduplicate and sort by timestamp ascending
    seen = set()
    unique = []
    for c in all_candles:
        ts = c["start"]
        if ts not in seen:
            seen.add(ts)
            unique.append(c)

    unique.sort(key=lambda c: int(c["start"]))
    return unique


# ---------------------------------------------------------------------------
# CoinGecko fallback (daily data, no auth needed)
# ---------------------------------------------------------------------------

def fetch_coingecko_daily(days=365):
    """
    Fallback: fetch daily USDC/USD price data from CoinGecko.
    No API key needed. Returns daily granularity only.
    """
    print(f"Fetching {days} days of USDC-USD daily data from CoinGecko (fallback)...")

    url = "https://api.coingecko.com/api/v3/coins/usd-coin/market_chart"
    params = {"vs_currency": "usd", "days": str(days), "interval": "daily"}

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  CoinGecko error: {e}")
        return None

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    if not prices:
        print("  No data returned from CoinGecko.")
        return None

    # Build candle-like records (daily: open=close=price, high/low estimated)
    candles = []
    for i, (ts_ms, price) in enumerate(prices):
        vol = volumes[i][1] if i < len(volumes) else 0
        candles.append({
            "start": str(int(ts_ms / 1000)),
            "open": str(price),
            "high": str(price * 1.0003),  # Estimated spread
            "low": str(price * 0.9997),
            "close": str(price),
            "volume": str(vol),
        })

    print(f"  Done! Got {len(candles)} daily candles.\n")
    return candles


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_csv(candles, output_path):
    """Write candles to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        for c in candles:
            ts = int(c["start"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([
                ts,
                dt,
                c["open"],
                c["high"],
                c["low"],
                c["close"],
                c["volume"],
            ])

    print(f"Saved {len(candles)} candles to {output_path}")
    print(f"  First: {datetime.fromtimestamp(int(candles[0]['start']), tz=timezone.utc)}")
    print(f"  Last:  {datetime.fromtimestamp(int(candles[-1]['start']), tz=timezone.utc)}")

    # Quick stats
    closes = [float(c["close"]) for c in candles]
    print(f"\n  Price range: ${min(closes):.6f} - ${max(closes):.6f}")
    print(f"  Mean: ${sum(closes)/len(closes):.6f}")
    deviations = [abs(p - 1.0) for p in closes]
    print(f"  Mean deviation from $1.00: ${sum(deviations)/len(deviations):.6f}")
    print(f"  Max deviation from $1.00: ${max(deviations):.6f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch USDC-USD historical candle data")
    parser.add_argument("--days", type=int, default=30, help="Number of days to fetch (default: 30)")
    parser.add_argument("--granularity", type=str, default="ONE_MINUTE",
                        help="Candle granularity (default: ONE_MINUTE)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_FILE

    print("=" * 60)
    print("  USDC-USD Historical Data Fetcher")
    print("=" * 60)
    print()

    # Try Coinbase API first
    candles = fetch_coinbase_candles(days=args.days, granularity=args.granularity)

    if candles is None:
        print("Coinbase API not available (no credentials or auth error).")
        print("Falling back to CoinGecko daily data...\n")
        candles = fetch_coingecko_daily(days=args.days)

    if candles is None:
        print("\nERROR: Could not fetch data from any source.")
        print("To use Coinbase API, create arb/.env with:")
        print("  COINBASE_API_KEY=your_key")
        print("  COINBASE_API_SECRET=your_secret")
        sys.exit(1)

    write_csv(candles, output_path)
    print("\nDone! Run 'python backtest.py' next to simulate the strategy.")


if __name__ == "__main__":
    main()
