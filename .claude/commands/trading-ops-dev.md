# trading-ops Development Skill

You are continuing development on the **trading-ops AI Bloomberg Terminal** — a
version-controlled trading research workspace with a FastAPI mobile web app,
Textual desktop TUI, backtesting engine, Obsidian vault sync, and iOS Shortcuts
integration. Everything is deployed on Render and lives in this repo.

---

## Architecture at a Glance

```
Cluade/
├── app.py                    Desktop TUI entry point (Textual)
├── trading-ops.sh/.bat       Desktop launchers
├── web-start.sh/.bat         Mobile web launchers
├── web/
│   ├── server.py             FastAPI — all API endpoints
│   └── templates/index.html  Mobile PWA — 4 nav tabs, 5 scan sub-tabs
├── core/
│   ├── scanner.py            Async subprocess wrapper → compute_signals.py
│   ├── scan_parser.py        Parses scanned/*.md → structured dicts
│   ├── macro_monitor.py      Background FRED polling
│   ├── news_feed.py          Background news polling
│   └── asset_class.py        Symbol → equity/crypto/forex/index/macro
├── scripts/
│   ├── compute_signals.py    Parallel orchestrator (ThreadPoolExecutor)
│   ├── fetch_equity.py       yfinance OHLCV + fundamentals + volume profile
│   ├── fetch_edgar.py        SEC EDGAR Form 4 + XBRL
│   ├── fetch_crypto.py       CoinGecko + Fear & Greed
│   ├── fetch_binance.py      Binance perp funding + OI
│   ├── fetch_fred.py         FRED macro indicators + regime
│   ├── fetch_news.py         Google News RSS + sentiment
│   ├── fetch_options.py      GEX + max pain + P/C ratio
│   ├── fetch_cot.py          CFTC COT positioning
│   ├── backtest_engine.py    Vectorized backtester + metrics
│   ├── wfa_optimizer.py      Optuna TPE Bayesian WFA
│   └── sync_to_vault.py      Obsidian vault sync (pulls from Render API)
├── docs/                     READ-ONLY framework knowledge base
├── guide/                    Editable protocol (self-improvement loop)
├── scanned/                  Dated scan output .md files
├── shortcuts/README.md       iOS Shortcuts setup guide
├── vault-sync.bat/.sh        Obsidian vault sync launchers
├── Dockerfile                Container build
├── render.yaml               Render.com one-click deploy
├── fly.toml                  Fly.io deploy config
└── DEPLOY.md                 Full deployment guide
```

---

## Key Conventions

### Adding a new API endpoint
1. Add the route to `web/server.py`
2. If it needs caching, use `_cache_get` / `_cache_set` (SCAN_TTL=900, MACRO_TTL=3600, NEWS_TTL=300)
3. If it needs auth, add `_user: str = Depends(auth_required)` parameter
4. Add a plain-text `/api/siri/<name>` variant for iOS Shortcuts if user-facing

### Adding a new UI tab (scan result sub-tabs)
1. Add a `render<TabName>(data)` function in `web/templates/index.html`
2. Add a `<button data-rtab="name">Label</button>` to the `.result-tabs` div
3. Add `<div class="panel hidden" id="rtab-name">` panel below
4. Update the `grid-template-columns` count in `.result-tabs` CSS
5. Update `attachResultHandlers()` to include the new tab name

### Adding a new fetch script
1. Write `scripts/fetch_<name>.py` — outputs JSON to stdout, takes symbol as argv[1]
2. Add it to `compute_signals.py` `run_parallel()` call in the relevant `score_*` function
3. Add the dep to `scripts/requirements.txt` if needed
4. Scripts use `sys.executable` (not hardcoded `python3`) for cross-platform compat

### Deploying
- All work is on branch `claude/ai-trading-system-f5mt6`
- `git push -u origin claude/ai-trading-system-f5mt6` → Render auto-deploys
- Render reads `render.yaml` + `Dockerfile`
- Env vars set in Render dashboard: `FRED_API_KEY`, `ACCESS_USER`, `ACCESS_PASSWORD`

---

## Web Server — Endpoint Map

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Mobile PWA UI |
| GET | `/api/health` | Health check (used by UptimeRobot) |
| GET | `/api/macro` | FRED regime + indicators (cached 1h) |
| GET | `/api/news?query=` | Google News RSS (cached 5m) |
| POST | `/api/scan` | Run compute_signals.py (cached 15m) |
| GET | `/api/history` | List scanned/*.md files |
| GET | `/api/history/{filename}` | Parse single scan file |
| POST | `/api/backtest` | Launch async Optuna WFA job |
| GET | `/api/backtest/{job_id}` | Poll WFA job status/result |
| GET | `/api/siri/scan/{symbol}` | Plain-text scan for Siri |
| GET | `/api/siri/macro` | Plain-text regime for Siri |
| GET | `/api/siri/watchlist` | Plain-text watchlist for Siri |

---

## Mobile UI — Component Map

**Nav tabs:** Scan · Macro · News · History

**Scan result sub-tabs:** Overview · Technical · Insider · Report · WFA

**Key field names from compute_signals.py output:**
- Equity: `key_metrics.price`, `key_metrics.poc/vah/val` (flat, NOT nested)
- Crypto: `key_metrics.price_usd`, `key_metrics.fear_greed_value`
- Forex:  `key_metrics.cot_index_52w`, `key_metrics.cot_positioning`

**Caching:** Scans cached 15m in `_cache` dict. Pass `{refresh: true}` to bypass.

---

## Obsidian Vault Sync

- Script: `scripts/sync_to_vault.py`
- Vault path: `C:\Users\conno\OneDrive\ResearchOS\02_Projects`
- Output: `02_Projects/trading-ops/` with README.md, daily-digest.md, scans/
- Launcher: `vault-sync.bat` — schedule via Windows Task Scheduler every 5 min
- Config in `.env`: `TRADING_OPS_URL`, `TRADING_OPS_PASSWORD`, `VAULT_PROJECT_PATH`

---

## Backtesting Engine

- `scripts/backtest_engine.py` — vectorized backtest, accepts OHLCV + signal Series
- `scripts/wfa_optimizer.py` — Optuna TPE WFA runner
- Parameters optimized: fast_ma, slow_ma, rsi_period, rsi_buy/sell, stop_loss, take_profit
- Objective: OOS Sharpe ratio
- Verdict: STRONG EDGE / MODERATE EDGE / WEAK EDGE / NO EDGE / INCONSISTENT
- Web: POST /api/backtest → job_id → poll GET /api/backtest/{job_id}

---

## Self-Improvement Loop

Every `/scan` Claude Code command ends with an audit block proposing improvements
to `guide/`. Files in `docs/` are READ-ONLY truth — never edit during a scan.
Only edit `guide/` files after explicit user consent ("apply fix N").

---

## iOS Shortcuts

Plain-text endpoints at `/api/siri/*` allow iOS Shortcuts + Siri integration.
Setup guide: `shortcuts/README.md`
Shortcuts: Scan Stock · Market Regime · Watchlist Summary · Scan from Share Sheet

---

## Common Tasks

**Add a new signal pillar to equity scoring:**
Edit `scripts/compute_signals.py` → `score_equity()`, add to signals/scores dicts,
update the composite threshold if needed, update `docs/equity-fundamentals.md`.

**Add a new market data source:**
Create `scripts/fetch_<source>.py` (JSON to stdout), add to `scripts/requirements.txt`,
wire into `compute_signals.py`, add display logic in appropriate UI tab.

**Add a new strategy to the backtester:**
Add a `compute_signals_<strategy>` function to `scripts/backtest_engine.py`,
expose the strategy name as a parameter in `wfa_optimizer.py` and `/api/backtest`.

**Debug a failing scan:**
Check Render logs → look for the subprocess stderr in the scan response's
`stderr` field. Run the failing script directly:
`python3 scripts/fetch_equity.py AAPL | python3 -m json.tool`

**Repackage the zip:**
```bash
zip -r /home/user/trading-ops-full.zip app.py trading-ops.* web-start.* \
  requirements*.txt Dockerfile .dockerignore render.yaml fly.toml \
  .env.example .gitignore CLAUDE.md README.md DEPLOY.md \
  docs/ guide/ scripts/ scanned/ .claude/commands/ core/ ui/ web/ shortcuts/ \
  vault-sync.* -x '*.pyc' '*/__pycache__/*'
```
