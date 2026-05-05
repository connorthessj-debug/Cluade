#!/usr/bin/env python3
"""
fetch_cot.py — CFTC Commitments of Traders (COT) data via Socrata API.
Usage: python3 scripts/fetch_cot.py <SYMBOL>
Output: JSON to stdout
Free public API — no auth required.
"""

import sys
import json
import datetime
import requests

CFTC_API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

SYMBOL_TO_MARKET = {
    "EURUSD": "EURO FX",
    "EUR": "EURO FX",
    "GBPUSD": "BRITISH POUND",
    "GBP": "BRITISH POUND",
    "USDJPY": "JAPANESE YEN",
    "JPY": "JAPANESE YEN",
    "AUDUSD": "AUSTRALIAN DOLLAR",
    "AUD": "AUSTRALIAN DOLLAR",
    "NZDUSD": "NEW ZEALAND DOLLAR",
    "NZD": "NEW ZEALAND DOLLAR",
    "USDCAD": "CANADIAN DOLLAR",
    "CAD": "CANADIAN DOLLAR",
    "USDCHF": "SWISS FRANC",
    "CHF": "SWISS FRANC",
    "USDMXN": "MEXICAN PESO",
    "MXN": "MEXICAN PESO",
    "GOLD": "GOLD",
    "GC": "GOLD",
    "XAUUSD": "GOLD",
    "SILVER": "SILVER",
    "SI": "SILVER",
    "XAGUSD": "SILVER",
    "OIL": "CRUDE OIL, LIGHT SWEET",
    "CL": "CRUDE OIL, LIGHT SWEET",
    "WTI": "CRUDE OIL, LIGHT SWEET",
    "BTC": "BITCOIN",
    "BTCUSDT": "BITCOIN",
    "COPPER": "COPPER",
    "HG": "COPPER",
    "CORN": "CORN",
    "WHEAT": "WHEAT",
    "SPX": "S&P 500 STOCK INDEX",
    "SPY": "S&P 500 STOCK INDEX",
    "ES": "S&P 500 STOCK INDEX",
    "NDX": "NASDAQ-100 STOCK INDEX",
    "QQQ": "NASDAQ-100 STOCK INDEX",
    "NQ": "NASDAQ-100 STOCK INDEX",
}


def resolve_market_name(symbol):
    upper = symbol.upper().strip()
    if upper in SYMBOL_TO_MARKET:
        return SYMBOL_TO_MARKET[upper]
    base = upper.replace("USDT", "").replace("USD", "")
    if base in SYMBOL_TO_MARKET:
        return SYMBOL_TO_MARKET[base]
    return upper


def fetch_cot_data(market_name, limit=52):
    resp = requests.get(
        CFTC_API,
        params={
            "$where": f"upper(market_and_exchange_names) like '%{market_name.upper()}%'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": limit,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def parse_cot_record(record):
    def safe_int(val):
        try:
            return int(float(val)) if val else 0
        except (ValueError, TypeError):
            return 0

    non_comm_long = safe_int(record.get("noncomm_positions_long_all"))
    non_comm_short = safe_int(record.get("noncomm_positions_short_all"))
    net_speculator = non_comm_long - non_comm_short

    comm_long = safe_int(record.get("comm_positions_long_all"))
    comm_short = safe_int(record.get("comm_positions_short_all"))
    net_commercial = comm_long - comm_short

    return {
        "report_date": record.get("report_date_as_yyyy_mm_dd", "")[:10],
        "market": record.get("market_and_exchange_names", ""),
        "non_comm_long": non_comm_long,
        "non_comm_short": non_comm_short,
        "net_speculator": net_speculator,
        "comm_long": comm_long,
        "comm_short": comm_short,
        "net_commercial": net_commercial,
        "open_interest": safe_int(record.get("open_interest_all")),
    }


def compute_cot_index(records, lookback=52):
    nets = [r["net_speculator"] for r in records]
    if len(nets) < 2:
        return None
    current = nets[0]
    min_net = min(nets)
    max_net = max(nets)
    if max_net == min_net:
        return 50
    return round((current - min_net) / (max_net - min_net) * 100, 1)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_cot.py <SYMBOL>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip()
    market_name = resolve_market_name(symbol)

    output = {
        "symbol": symbol,
        "market_searched": market_name,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    try:
        raw_records = fetch_cot_data(market_name, limit=52)
        if not raw_records:
            output["errors"].append(
                f"No COT data found for market '{market_name}'. "
                "Add to SYMBOL_TO_MARKET mapping or check CFTC dataset."
            )
            output["latest_report"] = None
            output["cot_index_52w"] = None
            output["interpretation"] = {"positioning_label": "UNKNOWN", "contrarian_signal": "NO DATA"}
            print(json.dumps(output, indent=2, default=str))
            return

        parsed = [parse_cot_record(r) for r in raw_records]
        output["latest_report"] = parsed[0] if parsed else None
        output["history_12w"] = parsed[:12]
        output["cot_index_52w"] = compute_cot_index(parsed)

        idx = output["cot_index_52w"]
        latest_net = parsed[0]["net_speculator"] if parsed else 0
        prev_net = parsed[1]["net_speculator"] if len(parsed) > 1 else latest_net
        direction_change = latest_net - prev_net

        if idx is not None and idx > 80:
            positioning_label = "EXTREME LONG (crowded)"
            contrarian = "BEARISH (spec longs crowded)"
        elif idx is not None and idx > 60:
            positioning_label = "LONG BIAS"
            contrarian = "MILD BEARISH LEAN"
        elif idx is not None and 40 <= idx <= 60:
            positioning_label = "NEUTRAL"
            contrarian = "NO CONTRARIAN EDGE"
        elif idx is not None and idx > 20:
            positioning_label = "SHORT BIAS"
            contrarian = "MILD BULLISH LEAN"
        elif idx is not None:
            positioning_label = "EXTREME SHORT (crowded)"
            contrarian = "BULLISH (spec shorts crowded)"
        else:
            positioning_label = "UNKNOWN"
            contrarian = "INSUFFICIENT DATA"

        output["interpretation"] = {
            "cot_index": idx,
            "positioning_label": positioning_label,
            "contrarian_signal": contrarian,
            "week_over_week_change": direction_change,
            "momentum": (
                "INCREASING LONGS" if direction_change > 5000
                else "DECREASING LONGS / ADDING SHORTS" if direction_change < -5000
                else "STABLE"
            ),
        }

    except requests.exceptions.HTTPError as e:
        output["errors"].append(f"HTTP error: {str(e)}")
    except Exception as e:
        output["errors"].append(f"Unexpected error: {str(e)}")

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
