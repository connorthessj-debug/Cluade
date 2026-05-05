# CLAUDE.md

This file provides guidance for AI assistants (and developers) working in this repository.

## Project Overview

**Cluade** is a project repository for Claude-related tools and utilities. The project is in its early stages with foundational structure being established.

## Repository Structure

```
Cluade/
├── CLAUDE.md              # AI assistant guidance (this file)
├── README.md              # Project description
├── docs/                  # READ-ONLY knowledge base — never edit during scans
│   ├── macro-framework.md         # 4 regime quadrants + asset playbook
│   ├── equity-fundamentals.md     # 6-pillar scoring framework
│   ├── volume-profile-vwap.md     # VP/VWAP methodology
│   ├── crypto-framework.md        # Crypto analysis framework
│   └── forex-framework.md         # COT + rate differential framework
├── guide/                 # Protocol docs — editable via self-improvement loop with consent
│   ├── scan-protocol.md           # Master step-by-step scan checklist
│   ├── verdict-format.md          # Exact output format specification
│   └── self-improvement.md        # Audit loop rules and consent gate
├── .claude/
│   └── commands/          # Claude Code slash commands
│       ├── scan.md                # /scan <SYMBOL> — multi-asset scan
│       └── scan-macro.md          # /scan-macro — macro regime scan
├── scanned/               # Dated scan output files (gittracked)
│   └── archive/           # Scans older than 30 days
└── scripts/               # Python data pre-compute scripts (9 total)
    ├── requirements.txt
    ├── fetch_equity.py    # yfinance: OHLCV, fundamentals, volume profile
    ├── fetch_edgar.py     # SEC EDGAR: Form 4, XBRL financials
    ├── fetch_crypto.py    # CoinGecko: price, Fear & Greed
    ├── fetch_binance.py   # Binance: perp funding, open interest, klines
    ├── fetch_fred.py      # FRED: yield curve, CPI, VIX, regime indicators
    ├── fetch_news.py      # Google News RSS: headlines + sentiment
    ├── fetch_options.py   # yfinance: GEX, max pain, P/C ratio
    ├── fetch_cot.py       # CFTC: COT positioning + 52W COT index
    └── compute_signals.py # Aggregate all scripts into unified signals JSON
```

## Development Workflow

### Branching

- The default branch is `main`
- Feature branches should use the `claude/` prefix (e.g., `claude/feature-name-<id>`)
- Always push feature branches with `git push -u origin <branch-name>`

### Commits

- Write clear, descriptive commit messages
- Use imperative mood in commit subjects (e.g., "Add feature" not "Added feature")
- Keep commits focused — one logical change per commit

### Code Style

- Follow existing patterns and conventions in the codebase
- Keep files focused and avoid unnecessary bloat
- Prefer editing existing files over creating new ones when practical

## Key Conventions

- **No over-engineering**: Only add what is needed for the current task
- **Security first**: Never commit secrets, credentials, or `.env` files
- **Simplicity**: Favor straightforward solutions over clever abstractions

## Commands

### Trading System Setup
```bash
pip install -r scripts/requirements.txt
export FRED_API_KEY=your_free_key_here   # get at fred.stlouisfed.org
```

### Run a Scan (Claude Code slash commands)
```
/scan AAPL          # equity scan — 6-pillar fundamentals + volume profile
/scan BTCUSDT       # crypto scan — F&G + funding + OI
/scan SPX           # index scan — GEX + VIX + breadth
/scan EURUSD        # forex scan — COT + rate differentials
/scan-macro         # macro regime quadrant scan
```

### Run Scripts Directly
```bash
python3 scripts/fetch_equity.py AAPL
python3 scripts/fetch_crypto.py BTCUSDT
python3 scripts/fetch_options.py SPY
python3 scripts/fetch_cot.py EURUSD
FRED_API_KEY=... python3 scripts/fetch_fred.py
python3 scripts/compute_signals.py AAPL equity
```

### No build system or test framework configured yet.

---

## Trading System — Key Rules for AI Assistants

1. **`docs/` is read-only** — never edit during a scan. These are immutable truth documents. Only propose edits in the audit block; apply only with explicit user consent.

2. **`guide/` is editable via the self-improvement loop** — but ONLY after user grants consent. Never edit guide/ files during a scan.

3. **`scanned/` is always writable** — every scan saves a dated `.md` verdict file here.

4. **Self-improvement audit is mandatory** — every scan (including failed ones) must end with an audit block in `guide/self-improvement.md` format.

5. **Asset class detection order** (in `scan.md`): crypto → forex → index → equity. Do not rely on user to specify.

6. **FRED_API_KEY** is required for macro context. If missing, score macro context as 0 and note data gap.

7. **Free APIs only** — no paid subscriptions. All scripts use: yfinance, CoinGecko free tier, Binance public API, SEC EDGAR public API, CFTC Socrata API, Google News RSS, FRED (free key).

## For AI Assistants

- Read existing files before proposing changes
- Do not create files unless necessary
- Match the style and conventions already present in the codebase
- When in doubt, ask the user for clarification
- The trading system docs (`docs/`, `guide/`) are version-controlled intelligence — treat them with care
