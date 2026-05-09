#!/usr/bin/env python3
"""
fetch_fred.py — FRED macro indicators via free API.
Usage: python3 scripts/fetch_fred.py
Requires env var: FRED_API_KEY (get free at https://fred.stlouisfed.org/docs/api/api_key.html)
Output: JSON to stdout
"""

import sys
import os
import json
import datetime
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "ten_year_yield": "DGS10",
    "two_year_yield": "DGS2",
    "yield_spread_10y2y": "T10Y2Y",
    "five_year_breakeven": "T5YIE",
    "cpi_all_urban": "CPIAUCSL",
    "hy_spread": "BAMLH0A0HYM2",
    "m2_money_supply": "M2SL",
    "unemployment_rate": "UNRATE",
    "consumer_sentiment": "UMCSENT",
    "vix": "VIXCLS",
    "sp500": "SP500",
    "fed_funds_rate": "FEDFUNDS",
}


def fetch_series(series_id, api_key, limit=13):
    resp = requests.get(
        FRED_BASE,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        },
        timeout=15,
    )
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    values = []
    for o in obs:
        val_str = o.get("value", ".")
        if val_str != ".":
            try:
                values.append({"date": o["date"], "value": float(val_str)})
            except ValueError:
                continue
    return values


def compute_cpi_yoy(cpi_series):
    if len(cpi_series) < 13:
        return None
    current = cpi_series[0]["value"]
    year_ago = cpi_series[12]["value"]
    if year_ago == 0:
        return None
    return round((current - year_ago) / year_ago * 100, 2)


def main():
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        print(json.dumps({
            "error": "FRED_API_KEY environment variable not set. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html",
            "regime_indicators": {},
            "series": {},
        }))
        sys.exit(0)

    output = {
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
        "series": {},
        "regime_indicators": {},
    }

    for name, series_id in SERIES.items():
        try:
            data = fetch_series(series_id, api_key, limit=13)
            output["series"][name] = {
                "series_id": series_id,
                "latest_date": data[0]["date"] if data else None,
                "latest_value": data[0]["value"] if data else None,
                "history": data[:6],
            }
        except Exception as e:
            output["errors"].append(f"{series_id}: {str(e)}")
            output["series"][name] = {"series_id": series_id, "latest_value": None}

    def get_latest(name):
        return (output["series"].get(name) or {}).get("latest_value")

    ten_yr = get_latest("ten_year_yield")
    two_yr = get_latest("two_year_yield")
    spread = get_latest("yield_spread_10y2y")
    breakeven = get_latest("five_year_breakeven")
    hy = get_latest("hy_spread")
    vix = get_latest("vix")
    sentiment = get_latest("consumer_sentiment")
    unemployment = get_latest("unemployment_rate")
    fed_funds = get_latest("fed_funds_rate")

    cpi_history = (output["series"].get("cpi_all_urban") or {}).get("history", [])
    cpi_yoy = compute_cpi_yoy(cpi_history)

    output["regime_indicators"] = {
        "ten_year_yield_pct": ten_yr,
        "two_year_yield_pct": two_yr,
        "yield_spread_10y2y_bps": round(spread * 100, 1) if spread is not None else (
            round((ten_yr - two_yr) * 100, 1) if ten_yr and two_yr else None
        ),
        "breakeven_inflation_pct": breakeven,
        "cpi_yoy_pct": cpi_yoy,
        "hy_spread_bps": round(hy * 100, 1) if hy is not None else None,
        "vix": vix,
        "consumer_sentiment": sentiment,
        "unemployment_rate_pct": unemployment,
        "fed_funds_rate_pct": fed_funds,
    }

    ri = output["regime_indicators"]
    yield_spread = ri["yield_spread_10y2y_bps"]
    cpi = ri["cpi_yoy_pct"]
    hy_bps = ri["hy_spread_bps"]
    be = ri["breakeven_inflation_pct"]

    growth_up = (
        (yield_spread is not None and yield_spread > 0) and
        (hy_bps is None or hy_bps < 500)
    )
    inflation_up = (
        (cpi is not None and cpi > 3.0) or
        (be is not None and be > 2.5)
    )

    if growth_up and not inflation_up:
        regime = "GOLDILOCKS"
    elif growth_up and inflation_up:
        regime = "REFLATION"
    elif not growth_up and inflation_up:
        regime = "STAGFLATION"
    else:
        regime = "RISK-OFF"

    output["regime_indicators"]["derived_regime"] = regime
    output["regime_indicators"]["growth_signal"] = "UP" if growth_up else "DOWN"
    output["regime_indicators"]["inflation_signal"] = "UP" if inflation_up else "DOWN"

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
