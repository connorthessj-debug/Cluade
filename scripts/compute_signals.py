#!/usr/bin/env python3
"""
compute_signals.py — Aggregate all fetch scripts into a unified signals JSON.
Usage: python3 scripts/compute_signals.py <SYMBOL> <equity|crypto|index|forex|macro>
Output: JSON to stdout
"""

import sys
import json
import datetime
import subprocess
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run_script(script_name, *args):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    try:
        result = subprocess.run(
            ["python3", script_path, *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return {"error": f"{script_name} returned empty output", "stderr": result.stderr[:200]}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"error": f"{script_name} timed out after 60s"}
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON from {script_name}"}
    except Exception as e:
        return {"error": str(e)}


def score_equity(symbol):
    equity = run_script("fetch_equity.py", symbol)
    edgar = run_script("fetch_edgar.py", symbol)
    options = run_script("fetch_options.py", symbol)
    news = run_script("fetch_news.py", symbol)
    fred = run_script("fetch_fred.py")

    signals = {}
    scores = {}

    # Pillar 1: Earnings
    eh = equity.get("earnings_history", [])
    if eh:
        beats = sum(1 for q in eh if q.get("surprise_pct") and float(q["surprise_pct"]) > 0)
        growth = (equity.get("fundamental", {}).get("earnings_growth") or 0) * 100
        if beats >= 6 and growth > 10:
            signals["earnings"] = "BULL"
            scores["earnings"] = 1
        elif beats <= 3 or growth < -5:
            signals["earnings"] = "BEAR"
            scores["earnings"] = -1
        else:
            signals["earnings"] = "NEUTRAL"
            scores["earnings"] = 0
    else:
        signals["earnings"] = "INSUFFICIENT_DATA"
        scores["earnings"] = 0

    # Pillar 2: Balance Sheet
    fund = equity.get("fundamental", {})
    de = fund.get("debt_to_equity")
    cr = fund.get("current_ratio")
    fcf = fund.get("free_cashflow")
    mc = fund.get("market_cap")
    fcf_yield = (fcf / mc * 100) if fcf and mc and mc > 0 else None

    if de is not None and cr is not None:
        if de < 50 and cr > 2.0 and (fcf_yield is None or fcf_yield > 3):
            signals["balance_sheet"] = "BULL"
            scores["balance_sheet"] = 1
        elif de > 200 or cr < 1.0 or (fcf_yield is not None and fcf_yield < 0):
            signals["balance_sheet"] = "BEAR"
            scores["balance_sheet"] = -1
        else:
            signals["balance_sheet"] = "NEUTRAL"
            scores["balance_sheet"] = 0
    else:
        signals["balance_sheet"] = "INSUFFICIENT_DATA"
        scores["balance_sheet"] = 0

    # Pillar 3: Valuation
    pe_fwd = fund.get("pe_forward")
    peg = fund.get("peg_ratio")
    if pe_fwd is not None and peg is not None:
        if peg < 1.0 and pe_fwd < 25:
            signals["valuation"] = "BULL"
            scores["valuation"] = 1
        elif peg > 2.5 or pe_fwd > 50:
            signals["valuation"] = "BEAR"
            scores["valuation"] = -1
        else:
            signals["valuation"] = "NEUTRAL"
            scores["valuation"] = 0
    else:
        signals["valuation"] = "INSUFFICIENT_DATA"
        scores["valuation"] = 0

    # Pillar 4: Insider / Institutional
    insider = edgar.get("insider_activity", {})
    form4_count = insider.get("form4_count_last_90d", 0)
    short_pct = equity.get("positioning", {}).get("short_percent_of_float")
    inst_pct = equity.get("positioning", {}).get("held_percent_institutions")
    signals["insider_institutional"] = "NEUTRAL"
    scores["insider_institutional"] = 0

    # Pillar 5: Options
    opts = options.get("summary", {})
    pcr = opts.get("avg_pcr")
    gex = opts.get("total_net_gex")
    if pcr is not None and gex is not None:
        if pcr < 0.7 and gex > 0:
            signals["options"] = "BULL"
            scores["options"] = 1
        elif pcr > 1.3 and gex < 0:
            signals["options"] = "BEAR"
            scores["options"] = -1
        else:
            signals["options"] = "NEUTRAL"
            scores["options"] = 0
    else:
        signals["options"] = "INSUFFICIENT_DATA"
        scores["options"] = 0

    # Pillar 6: Technical
    tech = equity.get("technical", {})
    price = equity.get("current_price")
    sma50 = tech.get("sma_50")
    sma200 = tech.get("sma_200")
    rsi = tech.get("rsi_14")
    if price and sma50 and sma200:
        bull = price > sma50 > sma200 and (rsi is None or 45 <= rsi <= 70)
        bear = price < sma50 < sma200 and (rsi is None or rsi < 35 or rsi > 80)
        if bull:
            signals["technical"] = "BULL"
            scores["technical"] = 1
        elif bear:
            signals["technical"] = "BEAR"
            scores["technical"] = -1
        else:
            signals["technical"] = "NEUTRAL"
            scores["technical"] = 0
    else:
        signals["technical"] = "INSUFFICIENT_DATA"
        scores["technical"] = 0

    total = sum(scores.values())
    if total >= 4:
        conviction = "HIGH LONG"
    elif total >= 1:
        conviction = "MODERATE LONG"
    elif total <= -4:
        conviction = "HIGH SHORT"
    elif total <= -1:
        conviction = "MODERATE SHORT"
    else:
        conviction = "NEUTRAL — NO TRADE"

    vp = equity.get("volume_profile", {})
    return {
        "asset_class": "equity",
        "symbol": symbol,
        "signals": signals,
        "scores": scores,
        "total_score": total,
        "conviction": conviction,
        "key_metrics": {
            "price": price,
            "sma_50": sma50,
            "sma_200": sma200,
            "rsi_14": rsi,
            "atr_14": tech.get("atr_14"),
            "poc": vp.get("poc"),
            "vah": vp.get("vah"),
            "val": vp.get("val"),
            "hvns": vp.get("hvns", []),
            "week52_high": equity.get("week52_high"),
            "week52_low": equity.get("week52_low"),
            "pe_forward": pe_fwd,
            "peg": peg,
            "short_float_pct": short_pct,
            "inst_ownership_pct": inst_pct,
            "pcr": pcr,
            "net_gex": gex,
            "form4_count_90d": form4_count,
        },
        "news_sentiment": news.get("sentiment_summary"),
        "fred_regime": fred.get("regime_indicators"),
    }


def score_crypto(symbol):
    crypto = run_script("fetch_crypto.py", symbol)
    binance = run_script("fetch_binance.py", symbol)
    news = run_script("fetch_news.py", symbol)

    signals = {}
    scores = {}

    fg = crypto.get("fear_and_greed", {})
    fg_val = fg.get("current_value") if fg else None
    if fg_val is not None:
        if fg_val < 25:
            signals["fear_greed"] = "BULL (extreme fear)"
            scores["fear_greed"] = 1
        elif fg_val > 75:
            signals["fear_greed"] = "BEAR (extreme greed)"
            scores["fear_greed"] = -1
        else:
            signals["fear_greed"] = "NEUTRAL"
            scores["fear_greed"] = 0
    else:
        signals["fear_greed"] = "INSUFFICIENT_DATA"
        scores["fear_greed"] = 0

    funding = binance.get("funding_summary", {})
    rate = funding.get("current_rate_pct")
    if rate is not None:
        if rate < -0.01:
            signals["funding"] = "BULL (negative funding)"
            scores["funding"] = 1
        elif rate > 0.1:
            signals["funding"] = "BEAR (high positive funding)"
            scores["funding"] = -1
        else:
            signals["funding"] = "NEUTRAL"
            scores["funding"] = 0
    else:
        signals["funding"] = "INSUFFICIENT_DATA"
        scores["funding"] = 0

    oi_trend = binance.get("oi_trend", {})
    oi_change = oi_trend.get("oi_change_pct")
    price_change = crypto.get("market_data", {}).get("price_change_30d_pct")
    if oi_change is not None and price_change is not None:
        if price_change > 5 and oi_change > 5:
            signals["oi_trend"] = "BULL (price+OI both rising)"
            scores["oi_trend"] = 1
        elif price_change < -5 and oi_change > 5:
            signals["oi_trend"] = "BEAR (price down, OI up)"
            scores["oi_trend"] = -1
        else:
            signals["oi_trend"] = "NEUTRAL"
            scores["oi_trend"] = 0
    else:
        signals["oi_trend"] = "INSUFFICIENT_DATA"
        scores["oi_trend"] = 0

    total = sum(scores.values())
    if total >= 2:
        conviction = "MODERATE-HIGH LONG"
    elif total >= 1:
        conviction = "MODERATE LONG"
    elif total <= -2:
        conviction = "MODERATE-HIGH SHORT"
    elif total <= -1:
        conviction = "MODERATE SHORT"
    else:
        conviction = "NEUTRAL — NO TRADE"

    md = crypto.get("market_data", {})
    return {
        "asset_class": "crypto",
        "symbol": symbol,
        "signals": signals,
        "scores": scores,
        "total_score": total,
        "conviction": conviction,
        "key_metrics": {
            "price_usd": md.get("current_price_usd"),
            "market_cap_usd": md.get("market_cap_usd"),
            "fear_greed_value": fg_val,
            "fear_greed_label": fg.get("current_label") if fg else None,
            "funding_rate_pct": rate,
            "oi_change_pct": oi_change,
            "price_change_30d_pct": price_change,
        },
        "news_sentiment": news.get("sentiment_summary"),
    }


def score_forex(symbol):
    cot = run_script("fetch_cot.py", symbol)
    fred = run_script("fetch_fred.py")
    news = run_script("fetch_news.py", symbol)

    signals = {}
    scores = {}

    cot_interp = cot.get("interpretation", {})
    contrarian = cot_interp.get("contrarian_signal", "")
    if "BEARISH" in contrarian:
        signals["cot"] = "BEAR (specs crowded long)"
        scores["cot"] = -1
    elif "BULLISH" in contrarian:
        signals["cot"] = "BULL (specs crowded short)"
        scores["cot"] = 1
    else:
        signals["cot"] = "NEUTRAL"
        scores["cot"] = 0

    signals["rate_differential"] = "NEUTRAL — requires manual foreign rate entry"
    scores["rate_differential"] = 0

    news_sent = news.get("sentiment_summary", {})
    label = news_sent.get("label", "MIXED")
    if label == "BULLISH":
        signals["news"] = "BULL"
        scores["news"] = 1
    elif label == "BEARISH":
        signals["news"] = "BEAR"
        scores["news"] = -1
    else:
        signals["news"] = "NEUTRAL"
        scores["news"] = 0

    total = sum(scores.values())
    conviction = (
        "MODERATE LONG" if total >= 2
        else "MILD LONG" if total == 1
        else "MODERATE SHORT" if total <= -2
        else "MILD SHORT" if total == -1
        else "NEUTRAL"
    )

    return {
        "asset_class": "forex",
        "symbol": symbol,
        "signals": signals,
        "scores": scores,
        "total_score": total,
        "conviction": conviction,
        "key_metrics": {
            "cot_index_52w": cot.get("cot_index_52w"),
            "cot_positioning": cot_interp.get("positioning_label"),
            "ten_year_usd_yield": (fred.get("regime_indicators") or {}).get("ten_year_yield_pct"),
        },
        "news_sentiment": news_sent,
    }


def score_macro():
    fred = run_script("fetch_fred.py")
    ri = fred.get("regime_indicators", {})
    return {
        "asset_class": "macro",
        "regime": ri.get("derived_regime", "UNKNOWN"),
        "growth_signal": ri.get("growth_signal"),
        "inflation_signal": ri.get("inflation_signal"),
        "regime_indicators": ri,
    }


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python3 compute_signals.py <SYMBOL> <equity|crypto|index|forex|macro>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip()
    asset_class = sys.argv[2].strip().lower()

    output = {
        "symbol": symbol,
        "asset_class": asset_class,
        "computed_at": datetime.datetime.utcnow().isoformat(),
    }

    try:
        if asset_class == "equity":
            output.update(score_equity(symbol))
        elif asset_class == "crypto":
            output.update(score_crypto(symbol))
        elif asset_class == "index":
            output.update(score_equity(symbol))
            output["asset_class"] = "index"
        elif asset_class == "forex":
            output.update(score_forex(symbol))
        elif asset_class == "macro":
            output.update(score_macro())
        else:
            output["error"] = f"Unknown asset class: {asset_class}"
    except Exception as e:
        output["error"] = str(e)

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
