#!/usr/bin/env python3
"""
fetch_binance.py — Binance perpetual futures: funding rate, open interest, klines.
Usage: python3 scripts/fetch_binance.py <SYMBOL>
Output: JSON to stdout
Free public API — no auth required.
"""

import sys
import json
import datetime
import requests

FAPI_BASE = "https://fapi.binance.com"


def normalize_symbol(symbol):
    upper = symbol.upper().strip()
    if upper.endswith("USDT"):
        return upper
    if upper in ("BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "LINK", "LTC", "MATIC"):
        return upper + "USDT"
    return upper


def fetch_funding_rate(symbol, limit=30):
    resp = requests.get(
        f"{FAPI_BASE}/fapi/v1/fundingRate",
        params={"symbol": symbol, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_open_interest(symbol):
    resp = requests.get(
        f"{FAPI_BASE}/fapi/v1/openInterest",
        params={"symbol": symbol},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_open_interest_hist(symbol, period="1d", limit=30):
    resp = requests.get(
        f"{FAPI_BASE}/futures/data/openInterestHist",
        params={"symbol": symbol, "period": period, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_klines(symbol, interval="1d", limit=30):
    resp = requests.get(
        f"{FAPI_BASE}/fapi/v1/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_binance.py <SYMBOL>"}))
        sys.exit(1)

    raw_symbol = sys.argv[1].strip()
    symbol = normalize_symbol(raw_symbol)

    output = {
        "symbol": symbol,
        "raw_symbol": raw_symbol,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    try:
        funding_data = fetch_funding_rate(symbol, limit=30)
        rates = [float(f["fundingRate"]) * 100 for f in funding_data if "fundingRate" in f]
        current_rate = rates[-1] if rates else None
        output["funding_history"] = [
            {
                "time": datetime.datetime.fromtimestamp(f["fundingTime"] / 1000, tz=datetime.timezone.utc).isoformat(),
                "rate_pct": round(float(f["fundingRate"]) * 100, 6),
            }
            for f in funding_data[-14:]
        ]
        output["funding_summary"] = {
            "current_rate_pct": round(current_rate, 6) if current_rate is not None else None,
            "avg_7d_pct": round(sum(rates[-21:]) / len(rates[-21:]), 6) if len(rates) >= 3 else None,
            "avg_30d_pct": round(sum(rates) / len(rates), 6) if rates else None,
            "min_30d_pct": round(min(rates), 6) if rates else None,
            "max_30d_pct": round(max(rates), 6) if rates else None,
        }
    except requests.exceptions.HTTPError as e:
        output["errors"].append(f"Funding rate HTTP error: {str(e)} — symbol '{symbol}' may not have a perp market")
        output["funding_summary"] = {}
        output["funding_history"] = []
    except Exception as e:
        output["errors"].append(f"Funding rate error: {str(e)}")
        output["funding_summary"] = {}
        output["funding_history"] = []

    try:
        oi_data = fetch_open_interest(symbol)
        current_oi = float(oi_data.get("openInterest", 0))
        output["open_interest_current"] = {
            "contracts": current_oi,
            "time": datetime.datetime.fromtimestamp(
                oi_data["time"] / 1000, tz=datetime.timezone.utc
            ).isoformat() if "time" in oi_data else None,
        }
    except Exception as e:
        output["errors"].append(f"Open interest current error: {str(e)}")
        output["open_interest_current"] = {}

    try:
        oi_hist = fetch_open_interest_hist(symbol, period="1d", limit=30)
        if oi_hist:
            oi_values = [float(r["sumOpenInterest"]) for r in oi_hist if "sumOpenInterest" in r]
            if len(oi_values) >= 2:
                oi_change_pct = round((oi_values[-1] - oi_values[0]) / oi_values[0] * 100, 2) if oi_values[0] != 0 else None
                output["oi_trend"] = {
                    "oi_change_pct": oi_change_pct,
                    "oi_start": oi_values[0],
                    "oi_end": oi_values[-1],
                    "history_30d": [
                        {
                            "date": r.get("timestamp", ""),
                            "oi": float(r["sumOpenInterest"]),
                        }
                        for r in oi_hist[-14:]
                    ],
                }
            else:
                output["oi_trend"] = {"oi_change_pct": None}
        else:
            output["oi_trend"] = {"oi_change_pct": None}
    except Exception as e:
        output["errors"].append(f"OI history error: {str(e)}")
        output["oi_trend"] = {"oi_change_pct": None}

    try:
        klines = fetch_klines(symbol, interval="1d", limit=30)
        output["klines_30d"] = [
            {
                "date": datetime.datetime.fromtimestamp(k[0] / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d"),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in klines[-7:]
        ]
        if klines:
            first_close = float(klines[0][4])
            last_close = float(klines[-1][4])
            output["price_change_30d_pct"] = round((last_close - first_close) / first_close * 100, 2) if first_close != 0 else None
    except Exception as e:
        output["errors"].append(f"Klines error: {str(e)}")
        output["klines_30d"] = []

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
