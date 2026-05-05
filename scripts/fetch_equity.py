#!/usr/bin/env python3
"""
fetch_equity.py — Equity data via yfinance.
Usage: python3 scripts/fetch_equity.py <SYMBOL>
Output: JSON to stdout
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


def compute_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def compute_volume_profile(hist, n_buckets=50):
    prices = hist["Close"].values
    volumes = hist["Volume"].values
    highs = hist["High"].values
    lows = hist["Low"].values

    price_min = lows.min()
    price_max = highs.max()
    bucket_size = (price_max - price_min) / n_buckets
    if bucket_size == 0:
        return {}

    vol_by_bucket = np.zeros(n_buckets)
    for i in range(len(prices)):
        lo_idx = int((lows[i] - price_min) / bucket_size)
        hi_idx = int((highs[i] - price_min) / bucket_size)
        lo_idx = max(0, min(lo_idx, n_buckets - 1))
        hi_idx = max(0, min(hi_idx, n_buckets - 1))
        span = hi_idx - lo_idx + 1
        for b in range(lo_idx, hi_idx + 1):
            vol_by_bucket[b] += volumes[i] / span

    poc_idx = int(np.argmax(vol_by_bucket))
    poc_price = round(price_min + (poc_idx + 0.5) * bucket_size, 2)

    total_vol = vol_by_bucket.sum()
    target_vol = total_vol * 0.70
    cumulative = vol_by_bucket[poc_idx]
    lo_idx, hi_idx = poc_idx, poc_idx
    while cumulative < target_vol and (lo_idx > 0 or hi_idx < n_buckets - 1):
        left_vol = vol_by_bucket[lo_idx - 1] if lo_idx > 0 else 0
        right_vol = vol_by_bucket[hi_idx + 1] if hi_idx < n_buckets - 1 else 0
        if left_vol >= right_vol and lo_idx > 0:
            lo_idx -= 1
            cumulative += vol_by_bucket[lo_idx]
        elif hi_idx < n_buckets - 1:
            hi_idx += 1
            cumulative += vol_by_bucket[hi_idx]
        else:
            break

    vah = round(price_min + (hi_idx + 1) * bucket_size, 2)
    val = round(price_min + lo_idx * bucket_size, 2)

    avg_vol = vol_by_bucket.mean()
    hvns = []
    lvns = []
    for i, v in enumerate(vol_by_bucket):
        price = round(price_min + (i + 0.5) * bucket_size, 2)
        if v > avg_vol * 1.5:
            hvns.append(price)
        elif v < avg_vol * 0.5:
            lvns.append(price)

    return {
        "poc": poc_price,
        "vah": vah,
        "val": val,
        "hvns": sorted(hvns),
        "lvns": sorted(lvns),
    }


def compute_anchored_vwap(hist, anchor_date=None):
    if anchor_date:
        hist = hist[hist.index >= anchor_date]
    if hist.empty:
        return None
    typical_price = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    vwap = (typical_price * hist["Volume"]).sum() / hist["Volume"].sum()
    return round(float(vwap), 2)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_equity.py <SYMBOL>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip().upper()
    output = {
        "symbol": symbol,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        output["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        output["week52_high"] = info.get("fiftyTwoWeekHigh")
        output["week52_low"] = info.get("fiftyTwoWeekLow")

        output["fundamental"] = {
            "market_cap": info.get("marketCap"),
            "pe_forward": info.get("forwardPE"),
            "pe_trailing": info.get("trailingPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_sales": info.get("priceToSalesTrailingTwelveMonths"),
            "price_to_book": info.get("priceToBook"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "free_cashflow": info.get("freeCashflow"),
            "return_on_equity": info.get("returnOnEquity"),
            "profit_margins": info.get("profitMargins"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }

        output["positioning"] = {
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "short_ratio": info.get("shortRatio"),
            "held_percent_institutions": info.get("heldPercentInstitutions"),
            "held_percent_insiders": info.get("heldPercentInsiders"),
            "shares_short": info.get("sharesShort"),
        }

        hist = ticker.history(period="1y", interval="1d")
        if hist.empty:
            output["errors"].append("No price history returned from yfinance")
        else:
            closes = hist["Close"].values.tolist()
            output["technical"] = {
                "sma_50": round(float(np.mean(closes[-50:])), 2) if len(closes) >= 50 else None,
                "sma_200": round(float(np.mean(closes[-200:])), 2) if len(closes) >= 200 else None,
                "rsi_14": compute_rsi(np.array(closes)) if len(closes) >= 15 else None,
                "atr_14": round(float(
                    np.mean([
                        max(h - l, abs(h - pc), abs(l - pc))
                        for h, l, pc in zip(
                            hist["High"].values[-15:],
                            hist["Low"].values[-15:],
                            hist["Close"].values[-16:-1],
                        )
                    ])
                ), 2) if len(closes) >= 16 else None,
            }

            output["volume_profile"] = compute_volume_profile(hist)

            vwap_52w_low_date = hist["Close"].idxmin()
            output["anchored_vwap"] = {
                "from_52w_low": compute_anchored_vwap(hist, vwap_52w_low_date),
            }

        try:
            earnings = ticker.earnings_history
            if earnings is not None and not earnings.empty:
                records = []
                for _, row in earnings.tail(8).iterrows():
                    records.append({
                        "date": str(row.name)[:10] if hasattr(row.name, "__str__") else None,
                        "eps_estimate": row.get("epsEstimate") if "epsEstimate" in row else None,
                        "eps_actual": row.get("epsActual") if "epsActual" in row else None,
                        "surprise_pct": row.get("surprisePercent") if "surprisePercent" in row else None,
                    })
                output["earnings_history"] = records
            else:
                output["earnings_history"] = []
        except Exception as e:
            output["errors"].append(f"Earnings history: {str(e)}")
            output["earnings_history"] = []

    except Exception as e:
        output["errors"].append(f"Main fetch error: {str(e)}")

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
