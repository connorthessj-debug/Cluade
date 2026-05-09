#!/usr/bin/env python3
"""
fetch_news.py — Google News RSS headlines for any symbol or query.
Usage: python3 scripts/fetch_news.py <SYMBOL_OR_QUERY>
Output: JSON to stdout
Free — no API key required.
"""

import sys
import json
import datetime
import urllib.parse

try:
    import feedparser
except ImportError:
    print(json.dumps({"error": "feedparser not installed. Run: pip install feedparser"}))
    sys.exit(1)

POSITIVE_WORDS = [
    "surge", "rally", "gain", "rise", "soar", "jump", "beat", "record",
    "growth", "profit", "upgrade", "buy", "bullish", "strong", "breakout",
    "outperform", "exceed", "positive", "upside", "momentum", "recovery",
    "boost", "higher", "expand", "win", "deal", "partnership",
]
NEGATIVE_WORDS = [
    "fall", "drop", "decline", "loss", "miss", "cut", "downgrade", "sell",
    "bearish", "weak", "crash", "warning", "risk", "concern", "lower",
    "disappoint", "underperform", "debt", "layoff", "recall", "lawsuit",
    "fine", "fraud", "bankruptcy", "default", "fear", "plunge", "slump",
]


def fetch_google_news(query, max_results=10):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    entries = []
    for entry in feed.entries[:max_results]:
        entries.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": entry.get("source", {}).get("title", "") if hasattr(entry.get("source", {}), "get") else "",
        })
    return entries


def score_sentiment(headlines):
    positive = 0
    negative = 0
    for h in headlines:
        text = h.get("title", "").lower()
        pos_hits = sum(1 for w in POSITIVE_WORDS if w in text)
        neg_hits = sum(1 for w in NEGATIVE_WORDS if w in text)
        positive += pos_hits
        negative += neg_hits

    if positive > negative * 1.5:
        label = "BULLISH"
    elif negative > positive * 1.5:
        label = "BEARISH"
    else:
        label = "MIXED"

    return {
        "label": label,
        "positive_count": positive,
        "negative_count": negative,
        "total_headlines": len(headlines),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_news.py <SYMBOL_OR_QUERY>"}))
        sys.exit(1)

    query = " ".join(sys.argv[1:]).strip()
    output = {
        "query": query,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    try:
        headlines = fetch_google_news(query, max_results=10)
        output["headlines"] = headlines
        output["sentiment_summary"] = score_sentiment(headlines)
        output["headline_count"] = len(headlines)
    except Exception as e:
        output["errors"].append(f"News fetch error: {str(e)}")
        output["headlines"] = []
        output["sentiment_summary"] = {"label": "UNKNOWN", "positive_count": 0, "negative_count": 0}

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
