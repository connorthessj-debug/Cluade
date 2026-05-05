#!/usr/bin/env python3
"""
fetch_crypto.py — Crypto data via CoinGecko free API + Fear & Greed index.
Usage: python3 scripts/fetch_crypto.py <SYMBOL>
Output: JSON to stdout
Free API — no key required.
"""

import sys
import json
import datetime
import requests

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_API = "https://api.alternative.me/fng/?limit=7"

SYMBOL_MAP = {
    "BTC": "bitcoin",
    "BTCUSDT": "bitcoin",
    "ETH": "ethereum",
    "ETHUSDT": "ethereum",
    "SOL": "solana",
    "SOLUSDT": "solana",
    "BNB": "binancecoin",
    "BNBUSDT": "binancecoin",
    "XRP": "ripple",
    "XRPUSDT": "ripple",
    "ADA": "cardano",
    "ADAUSDT": "cardano",
    "AVAX": "avalanche-2",
    "AVAXUSDT": "avalanche-2",
    "DOGE": "dogecoin",
    "DOGEUSDT": "dogecoin",
    "MATIC": "matic-network",
    "MATICUSDT": "matic-network",
    "DOT": "polkadot",
    "DOTUSDT": "polkadot",
    "LINK": "chainlink",
    "LINKUSDT": "chainlink",
    "LTC": "litecoin",
    "LTCUSDT": "litecoin",
}


def resolve_coin_id(symbol):
    upper = symbol.upper().strip()
    if upper in SYMBOL_MAP:
        return SYMBOL_MAP[upper]
    base = upper.replace("USDT", "").replace("USD", "").replace("BTC", "")
    if base in SYMBOL_MAP:
        return SYMBOL_MAP[base]
    return upper.lower()


def fetch_coin_data(coin_id):
    resp = requests.get(
        f"{COINGECKO_BASE}/coins/{coin_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_fear_greed():
    resp = requests.get(FEAR_GREED_API, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    entries = data.get("data", [])
    if not entries:
        return {}
    latest = entries[0]
    return {
        "current_value": int(latest.get("value", 0)),
        "current_label": latest.get("value_classification", ""),
        "timestamp": latest.get("timestamp", ""),
        "history_7d": [
            {"value": int(e.get("value", 0)), "label": e.get("value_classification", "")}
            for e in entries
        ],
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_crypto.py <SYMBOL>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip()
    coin_id = resolve_coin_id(symbol)

    output = {
        "symbol": symbol,
        "coin_id": coin_id,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    try:
        coin = fetch_coin_data(coin_id)
        md = coin.get("market_data", {})
        output["market_data"] = {
            "current_price_usd": md.get("current_price", {}).get("usd"),
            "market_cap_usd": md.get("market_cap", {}).get("usd"),
            "total_volume_usd": md.get("total_volume", {}).get("usd"),
            "high_24h_usd": md.get("high_24h", {}).get("usd"),
            "low_24h_usd": md.get("low_24h", {}).get("usd"),
            "price_change_24h_pct": md.get("price_change_percentage_24h"),
            "price_change_7d_pct": md.get("price_change_percentage_7d"),
            "price_change_30d_pct": md.get("price_change_percentage_30d"),
            "price_change_1y_pct": md.get("price_change_percentage_1y"),
            "ath_usd": md.get("ath", {}).get("usd"),
            "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
            "atl_usd": md.get("atl", {}).get("usd"),
            "circulating_supply": md.get("circulating_supply"),
            "total_supply": md.get("total_supply"),
            "market_cap_rank": coin.get("market_cap_rank"),
        }

        mc = output["market_data"]["market_cap_usd"]
        vol = output["market_data"]["total_volume_usd"]
        output["market_data"]["volume_to_market_cap_ratio"] = (
            round(vol / mc, 4) if mc and vol and mc > 0 else None
        )

        output["coin_name"] = coin.get("name")
        output["coin_description_snippet"] = (
            coin.get("description", {}).get("en", "")[:200]
            if coin.get("description", {}).get("en")
            else ""
        )

    except requests.exceptions.HTTPError as e:
        output["errors"].append(f"CoinGecko HTTP error: {str(e)} — check coin_id '{coin_id}'")
    except Exception as e:
        output["errors"].append(f"CoinGecko fetch error: {str(e)}")

    try:
        output["fear_and_greed"] = fetch_fear_greed()
    except Exception as e:
        output["errors"].append(f"Fear & Greed fetch error: {str(e)}")
        output["fear_and_greed"] = {}

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
