"""
sync_to_vault.py — Push trading-ops scan results into an Obsidian vault.

Pulls scan history from your Render (or local) server and writes:
  02_Projects/trading-ops/
  ├── README.md                  ← project overview (auto-research reads this)
  ├── daily-digest.md            ← latest signals across all recent scans
  └── scans/
      ├── 2026-05-06_AAPL.md
      ├── 2026-05-06_BTCUSDT.md
      └── ...

Configuration (set via environment variables or edit the DEFAULTS below):
    VAULT_PROJECT_PATH   — full path to 02_Projects folder
    TRADING_OPS_URL      — your Render URL (https://your-app.onrender.com)
    TRADING_OPS_USER     — ACCESS_USER (default: trader)
    TRADING_OPS_PASSWORD — ACCESS_PASSWORD

Run:
    python3 scripts/sync_to_vault.py

Schedule on Windows (Task Scheduler every 5 min):
    Action: python.exe  C:\\path\\to\\Cluade\\scripts\\sync_to_vault.py

Schedule on macOS/Linux (crontab -e):
    */5 * * * * python3 /path/to/Cluade/scripts/sync_to_vault.py >> /tmp/vault-sync.log 2>&1
"""

import json
import os
import sys
import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ── configuration ─────────────────────────────────────────────────────────────

VAULT_PROJECT_PATH = os.environ.get(
    "VAULT_PROJECT_PATH",
    r"C:\Users\conno\OneDrive\ResearchOS\02_Projects",
)
TRADING_OPS_URL  = os.environ.get("TRADING_OPS_URL",  "").rstrip("/")
TRADING_OPS_USER = os.environ.get("TRADING_OPS_USER", "trader")
TRADING_OPS_PASS = os.environ.get("TRADING_OPS_PASSWORD", "")

PROJECT_DIR  = Path(VAULT_PROJECT_PATH) / "trading-ops"
SCANS_DIR    = PROJECT_DIR / "scans"

MAX_SCANS_TO_SYNC = 50   # how many recent scans to keep in vault


# ── helpers ───────────────────────────────────────────────────────────────────

def _auth():
    if TRADING_OPS_PASS:
        return (TRADING_OPS_USER, TRADING_OPS_PASS)
    return None


def _get(path: str) -> dict | list:
    url = TRADING_OPS_URL + path
    r = requests.get(url, auth=_auth(), timeout=30)
    r.raise_for_status()
    return r.json()


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f'{k}: "{v}"')
    lines.append("---")
    return "\n".join(lines)


# ── scan note writer ──────────────────────────────────────────────────────────

def _conviction_emoji(c: str) -> str:
    c = (c or "").upper()
    if "HIGH LONG" in c:    return "🟢🟢"
    if "MODERATE LONG" in c: return "🟢"
    if "HIGH SHORT" in c:   return "🔴🔴"
    if "MODERATE SHORT" in c: return "🔴"
    return "⚪"


def _write_scan_note(scan_meta: dict) -> Path:
    """Fetch full scan detail and write an Obsidian note."""
    filename = scan_meta.get("filename", "")
    symbol   = scan_meta.get("symbol", filename)
    date     = scan_meta.get("date", "")
    conviction = scan_meta.get("conviction", "?")
    asset_class = scan_meta.get("asset_class", "?")

    detail = _get(f"/api/history/{filename}")
    raw_md = detail.get("markdown", "")
    signals = detail.get("signals", [])
    trade   = detail.get("trade", {})

    emoji = _conviction_emoji(conviction)

    fm = _frontmatter({
        "title": f"{symbol} Scan — {date}",
        "symbol": symbol,
        "date": date,
        "asset_class": asset_class,
        "conviction": conviction,
        "tags": ["trading-ops", "scan", asset_class, symbol.lower()],
        "source": "trading-ops auto-sync",
        "synced_at": _now_str(),
    })

    lines = [fm, "", f"# {emoji} {symbol} — {date}", ""]

    # Quick conviction badge
    lines += [
        f"> **Conviction:** {conviction}  ",
        f"> **Asset Class:** {asset_class}  ",
        f"> **Date:** {date}",
        "",
    ]

    # Signals table
    if signals:
        lines += ["## Signals", ""]
        lines += ["| Dimension | Score | Signal | Rationale |",
                  "|-----------|-------|--------|-----------|"]
        for s in signals:
            lines.append(f"| {s.get('dimension','')} | {s.get('score','')} | {s.get('signal','')} | {s.get('rationale','')} |")
        lines.append("")

    # Trade table
    if trade:
        lines += ["## Trade Structure", ""]
        lines += ["| Field | Value |", "|-------|-------|"]
        for k, v in trade.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    # Full raw verdict
    if raw_md:
        lines += ["## Full Verdict", "", "```", raw_md, "```", ""]

    # Auto-research prompt block
    lines += [
        "## 🤖 Auto-Research Notes",
        "",
        "> This section is for the auto-research routine to populate.",
        "> Analyse the signals above and suggest:",
        "> - Any regime mismatches vs current macro",
        "> - Correlated assets to watch",
        "> - Improvements to the scan protocol",
        "> - Risk factors not captured by the current framework",
        "",
    ]

    note = "\n".join(lines)
    out_path = SCANS_DIR / filename.replace(".md", "") / f"{filename}"
    out_path = SCANS_DIR / filename
    out_path.write_text(note, encoding="utf-8")
    return out_path


# ── daily digest ──────────────────────────────────────────────────────────────

def _write_digest(scans: list[dict]) -> None:
    today = datetime.date.today().isoformat()
    recent = scans[:20]

    fm = _frontmatter({
        "title": f"trading-ops digest — {today}",
        "date": today,
        "tags": ["trading-ops", "digest"],
        "synced_at": _now_str(),
    })

    lines = [fm, "", f"# trading-ops Daily Digest — {today}", ""]

    # Conviction summary table
    lines += ["## Recent Signals", ""]
    lines += ["| Symbol | Asset | Date | Conviction |",
              "|--------|-------|------|------------|"]
    for s in recent:
        emoji = _conviction_emoji(s.get("conviction", ""))
        lines.append(
            f"| [[scans/{s.get('filename','')}|{s.get('symbol','')}]] "
            f"| {s.get('asset_class','')} "
            f"| {s.get('date','')} "
            f"| {emoji} {s.get('conviction','')} |"
        )
    lines += [""]

    # Bull/Bear breakdown
    bulls = [s for s in recent if "LONG" in (s.get("conviction") or "").upper()]
    bears = [s for s in recent if "SHORT" in (s.get("conviction") or "").upper()]
    lines += [
        "## Bull/Bear Count",
        "",
        f"- 🟢 **LONG signals:** {len(bulls)} — " + ", ".join(s["symbol"] for s in bulls[:10]),
        f"- 🔴 **SHORT signals:** {len(bears)} — " + ", ".join(s["symbol"] for s in bears[:10]),
        "",
        "## 🤖 Auto-Research Prompt",
        "",
        "> Given the signal mix above:",
        "> 1. Which signals conflict with the current macro regime?",
        "> 2. Are any correlated pairs diverging unusually?",
        "> 3. What sectors/themes are emerging across multiple scans?",
        "> 4. Suggest one improvement to the trading-ops scan protocol.",
        "",
        f"*Auto-synced from trading-ops at {_now_str()}*",
    ]

    digest_path = PROJECT_DIR / "daily-digest.md"
    digest_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ digest → {digest_path}")


# ── project overview note ─────────────────────────────────────────────────────

def _write_overview() -> None:
    overview_path = PROJECT_DIR / "README.md"
    if overview_path.exists():
        return  # don't overwrite if already exists

    fm = _frontmatter({
        "title": "trading-ops — AI Bloomberg Terminal",
        "tags": ["trading-ops", "project", "auto-research"],
        "status": "active",
        "created": _now_str(),
    })

    content = fm + """

# trading-ops — AI Bloomberg Terminal

## What It Is
An AI-powered trading research workspace that scans stocks, crypto, forex, and macro data using a version-controlled framework. Claude Code reads the framework docs and runs Python scripts to produce structured scan verdicts with:
- 6-pillar equity scoring (earnings, balance sheet, valuation, insider/institutional, options, technical)
- 4 macro regime quadrants (GOLDILOCKS / REFLATION / STAGFLATION / RISK-OFF)
- Volume Profile analysis (POC, VAH, VAL, HVNs, LVNs)
- Backtesting engine with Optuna Bayesian WFA

## Architecture
```
trading-ops/
├── docs/            ← READ-ONLY knowledge base (framework truth)
│   ├── macro-framework.md
│   ├── equity-fundamentals.md
│   ├── volume-profile-vwap.md
│   ├── crypto-framework.md
│   └── forex-framework.md
├── guide/           ← editable protocol (self-improvement loop)
│   ├── scan-protocol.md
│   ├── verdict-format.md
│   └── self-improvement.md
├── scripts/         ← data fetch + compute (9 Python scripts)
│   ├── fetch_equity.py      ← yfinance OHLCV + fundamentals
│   ├── fetch_edgar.py       ← SEC EDGAR Form 4 + XBRL
│   ├── fetch_crypto.py      ← CoinGecko + Fear & Greed
│   ├── fetch_binance.py     ← perp funding + open interest
│   ├── fetch_fred.py        ← FRED macro indicators
│   ├── fetch_news.py        ← Google News RSS + sentiment
│   ├── fetch_options.py     ← GEX + max pain + P/C ratio
│   ├── fetch_cot.py         ← CFTC COT positioning
│   ├── compute_signals.py   ← parallel orchestrator → JSON
│   ├── backtest_engine.py   ← vectorized backtester
│   └── wfa_optimizer.py     ← Optuna Bayesian WFA
├── web/             ← FastAPI mobile web server
│   └── server.py
└── scanned/         ← dated scan verdicts (Obsidian-synced)
```

## Signal Framework

### Equity (6 pillars, +1/0/-1 each)
| Pillar | BULL | BEAR |
|--------|------|------|
| Earnings | ≥6/8Q beat, >10% growth | ≤3/8Q beat or <-5% growth |
| Balance Sheet | D/E<50, CR>2, FCF>3% | D/E>200 or CR<1 |
| Valuation | PEG<1, P/E<25 | PEG>2.5 or P/E>50 |
| Insider/Inst | ≥3 Form4 + inst>70% | 0 Form4 + short>30% |
| Options | PCR<0.7 + GEX>0 | PCR>1.3 + GEX<0 |
| Technical | Price>SMA50>SMA200, RSI 45-70 | Price<SMA50<SMA200 |

Composite: ≥4=HIGH LONG, 1-3=MOD LONG, -1 to -3=MOD SHORT, ≤-4=HIGH SHORT

### Macro Regimes
| Regime | Growth | Inflation | Play |
|--------|--------|-----------|------|
| GOLDILOCKS | UP | DOWN | Long equities, short vol |
| REFLATION | UP | UP | Long commodities, value |
| STAGFLATION | DOWN | UP | Long gold, short equities |
| RISK-OFF | DOWN | DOWN | Long bonds/USD |

## Current Signals
See [[daily-digest]] for the latest scan summary.
See [[scans/]] for individual symbol verdicts.

## Self-Improvement Loop
Every scan ends with an audit block proposing improvements to `guide/`.
Changes require explicit user consent before being applied.
The protocol version is tracked in `guide/scan-protocol.md`.

## Backtesting
Walk-Forward Analysis using Optuna TPE Bayesian optimisation:
- Parameters: fast/slow MA, RSI period/thresholds, stop-loss, take-profit
- Objective: maximise OOS Sharpe ratio
- Verdict: STRONG EDGE / MODERATE EDGE / WEAK EDGE / NO EDGE

## Auto-Research Integration
This vault note and the `daily-digest.md` are updated every few minutes
by `scripts/sync_to_vault.py` running via Windows Task Scheduler.

### Suggested Research Questions for the Routine
1. Which current signals conflict with the macro regime?
2. Are there improvements to the 6-pillar scoring thresholds?
3. What data sources could improve signal quality?
4. Are the WFA results consistent with live signal performance?
5. What new asset classes or frameworks should be added?
"""

    overview_path.write_text(content, encoding="utf-8")
    print(f"  ✓ overview → {overview_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not TRADING_OPS_URL:
        print("ERROR: TRADING_OPS_URL not set.")
        print("Add to .env:  TRADING_OPS_URL=https://your-app.onrender.com")
        sys.exit(1)

    vault_root = Path(VAULT_PROJECT_PATH)
    if not vault_root.exists():
        print(f"ERROR: vault path not found: {vault_root}")
        sys.exit(1)

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    SCANS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[vault-sync] {_now_str()} — syncing to {PROJECT_DIR}")

    # 1. Project overview (first run only)
    _write_overview()

    # 2. Fetch scan list
    try:
        data = _get("/api/history")
    except Exception as e:
        print(f"  ERROR fetching history: {e}")
        sys.exit(1)

    scans = data.get("scans", [])
    print(f"  {len(scans)} scans on server")

    # 3. Sync each scan note
    existing = {p.name for p in SCANS_DIR.glob("*.md")}
    synced = 0
    for scan in scans[:MAX_SCANS_TO_SYNC]:
        fname = scan.get("filename", "")
        if not fname:
            continue
        if fname in existing:
            continue  # already synced
        try:
            path = _write_scan_note(scan)
            print(f"  ✓ {path.name}")
            synced += 1
        except Exception as e:
            print(f"  ✗ {fname}: {e}")

    if synced == 0:
        print("  (no new scans)")

    # 4. Daily digest (always refresh)
    _write_digest(scans)

    print(f"[vault-sync] done — {synced} new notes written")


if __name__ == "__main__":
    main()
