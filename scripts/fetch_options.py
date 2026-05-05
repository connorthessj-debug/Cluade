#!/usr/bin/env python3
"""
fetch_options.py — Options chain analysis: GEX, max pain, P/C ratio.
Usage: python3 scripts/fetch_options.py <SYMBOL>
Output: JSON to stdout
Free via yfinance — no auth required.
"""

import sys
import json
import datetime
import numpy as np

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed. Run: pip install yfinance"}))
    sys.exit(1)


def compute_max_pain(calls_df, puts_df, spot_price):
    all_strikes = sorted(set(calls_df["strike"].tolist() + puts_df["strike"].tolist()))
    if not all_strikes:
        return None

    min_pain = None
    max_pain_strike = None

    for test_price in all_strikes:
        call_pain = sum(
            max(0, test_price - k) * oi
            for k, oi in zip(calls_df["strike"], calls_df["openInterest"])
        )
        put_pain = sum(
            max(0, k - test_price) * oi
            for k, oi in zip(puts_df["strike"], puts_df["openInterest"])
        )
        total_pain = call_pain + put_pain
        if min_pain is None or total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_price

    return max_pain_strike


def compute_gex(calls_df, puts_df, spot_price):
    total_gex = 0.0

    for _, row in calls_df.iterrows():
        gamma = row.get("gamma", 0) or 0
        oi = row.get("openInterest", 0) or 0
        gex = gamma * oi * 100 * spot_price
        total_gex += gex

    for _, row in puts_df.iterrows():
        gamma = row.get("gamma", 0) or 0
        oi = row.get("openInterest", 0) or 0
        gex = gamma * oi * 100 * spot_price
        total_gex -= gex

    return round(total_gex, 2)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_options.py <SYMBOL>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip().upper()
    output = {
        "symbol": symbol,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
        "expiries": [],
        "summary": {},
    }

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        spot_price = info.get("currentPrice") or info.get("regularMarketPrice")
        output["spot_price"] = spot_price

        expirations = ticker.options
        if not expirations:
            output["errors"].append("No options data available for this symbol")
            print(json.dumps(output, indent=2, default=str))
            return

        target_expiries = expirations[:2]
        all_pcrs = []
        all_gex = []
        all_max_pain = []

        for exp in target_expiries:
            try:
                chain = ticker.option_chain(exp)
                calls = chain.calls
                puts = chain.puts

                if calls.empty or puts.empty:
                    continue

                call_oi = calls["openInterest"].fillna(0).sum()
                put_oi = puts["openInterest"].fillna(0).sum()
                pcr = round(put_oi / call_oi, 3) if call_oi > 0 else None

                max_pain_strike = compute_max_pain(calls, puts, spot_price) if spot_price else None
                gex = compute_gex(calls, puts, spot_price) if spot_price else None

                expiry_data = {
                    "expiry": exp,
                    "call_oi": int(call_oi),
                    "put_oi": int(put_oi),
                    "pcr": pcr,
                    "max_pain_strike": max_pain_strike,
                    "net_gex": gex,
                    "top_call_strikes": calls.nlargest(3, "openInterest")[["strike", "openInterest", "lastPrice"]].to_dict("records") if not calls.empty else [],
                    "top_put_strikes": puts.nlargest(3, "openInterest")[["strike", "openInterest", "lastPrice"]].to_dict("records") if not puts.empty else [],
                }
                output["expiries"].append(expiry_data)

                if pcr is not None:
                    all_pcrs.append(pcr)
                if gex is not None:
                    all_gex.append(gex)
                if max_pain_strike is not None:
                    all_max_pain.append(max_pain_strike)

            except Exception as e:
                output["errors"].append(f"Options chain error for {exp}: {str(e)}")

        output["summary"] = {
            "avg_pcr": round(sum(all_pcrs) / len(all_pcrs), 3) if all_pcrs else None,
            "total_net_gex": round(sum(all_gex), 2) if all_gex else None,
            "max_pain_strike": all_max_pain[0] if all_max_pain else None,
            "spot_price": spot_price,
            "max_pain_vs_spot_pct": (
                round((all_max_pain[0] - spot_price) / spot_price * 100, 2)
                if all_max_pain and spot_price and spot_price > 0
                else None
            ),
        }

    except Exception as e:
        output["errors"].append(f"Main options error: {str(e)}")

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
