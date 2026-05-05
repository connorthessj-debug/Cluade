# Scan Protocol — Master Checklist

> VERSION: 1.0 | This file may be improved by the self-improvement loop with user consent.

## Purpose

This is the step-by-step protocol Claude follows for every `/scan` command. Every step is mandatory. If a step cannot be completed (API failure, missing data), note it in the audit block and continue.

---

## Step 0 — Setup

1. Note the current date and time (UTC)
2. Identify the symbol from `$ARGUMENTS` (strip whitespace, uppercase)
3. Read `guide/verdict-format.md` — this is the output contract
4. Read `guide/self-improvement.md` — this is the audit contract

---

## Step 1 — Detect Asset Class

Classify the symbol using these rules (in order):

| Rule | Asset Class |
|------|-------------|
| Ends with "USDT", "BTC", "ETH", or is a known coin name (BTC, ETH, SOL, etc.) | **crypto** |
| Is exactly 6 characters and both halves are 3-letter currency codes (EURUSD, GBPJPY, etc.) | **forex** |
| Is one of: SPX, SPY, QQQ, NDX, IWM, DIA, VIX | **index** |
| Otherwise (AAPL, TSLA, NVDA, etc.) | **equity** |

State the detected asset class explicitly at the start of your output.

---

## Step 2 — Macro Context

Run `fetch_fred.py` regardless of asset class. Read `docs/macro-framework.md`.

1. Map the FRED indicators to a regime quadrant (GOLDILOCKS / REFLATION / STAGFLATION / RISK-OFF)
2. State the regime and list the 2–3 indicators that determined it
3. Note the regime's implication for this specific asset class (use the playbook table)

---

## Step 3 — Fetch Asset Data

Run the scripts appropriate for the detected asset class:

**Equity:**
```bash
python3 scripts/fetch_equity.py SYMBOL
python3 scripts/fetch_edgar.py SYMBOL
python3 scripts/fetch_options.py SYMBOL
python3 scripts/fetch_news.py SYMBOL
```

**Crypto:**
```bash
python3 scripts/fetch_crypto.py SYMBOL
python3 scripts/fetch_binance.py SYMBOL
python3 scripts/fetch_news.py SYMBOL
```

**Index:**
```bash
python3 scripts/fetch_equity.py SYMBOL
python3 scripts/fetch_options.py SYMBOL
python3 scripts/fetch_news.py SYMBOL
```

**Forex:**
```bash
python3 scripts/fetch_cot.py SYMBOL
python3 scripts/fetch_news.py SYMBOL
```

Capture each script's JSON output. Note any errors in the audit block.

---

## Step 4 — Read Framework Docs

Read the docs relevant to the detected asset class:

| Asset Class | Docs to Read |
|-------------|-------------|
| equity | `docs/equity-fundamentals.md`, `docs/volume-profile-vwap.md` |
| crypto | `docs/crypto-framework.md` |
| index | `docs/equity-fundamentals.md` (pillars 5–6 only), `docs/volume-profile-vwap.md` |
| forex | `docs/forex-framework.md` |

---

## Step 5 — Score Each Dimension

Apply the scoring rules from the relevant framework doc. For each dimension:
- Extract the relevant data from the script JSON output
- Apply the explicit scoring threshold from the framework doc
- Record: dimension name, score (+1/0/-1), and 1-sentence rationale

Do not invent thresholds. If the framework doc does not specify a rule for a condition, score 0 and flag it in the audit block.

---

## Step 6 — Identify Key Price Levels

For equities and indices, extract from `fetch_equity.py` output:
- Current price
- 52-week high and low
- POC, VAH, VAL
- Top 3 HVNs above and below current price
- Anchored VWAP(s)
- SMA50, SMA200

For crypto, extract from `fetch_crypto.py`:
- Current price, 24h high/low
- 30-day high/low
- Key round numbers (psychological levels)

For forex:
- Current rate
- Weekly high/low
- Daily S/R levels (previous week's high/low/open)

---

## Step 7 — Build Trade Structure

Using the scored signals and key levels:

1. **Direction**: determined by composite score — positive = LONG, negative = SHORT, zero = NO TRADE
2. **Entry zone**: for longs: VAL / nearest HVN below price / SMA50 (whichever is most relevant). For shorts: VAH / nearest HVN above price
3. **Stop**: for longs: below VAL or below nearest LVN below entry. Use 2×ATR minimum distance
4. **Target 1**: nearest significant level in the direction of the trade (POC if entering at VAL, VAH if entering at POC)
5. **Target 2**: beyond T1 — the next HVN or 52W high/low
6. **R:R**: (T1 - Entry) ÷ (Entry - Stop). Only proceed to output if R:R ≥ 1.5
7. **Timeframe**: estimate based on level distance vs ATR (daily moves)

If R:R < 1.5, label the trade "SKIPPED — insufficient R:R" and note the levels anyway.

---

## Step 8 — Construct ASCII Price Ladder

Follow the instructions in `docs/volume-profile-vwap.md` (ASCII ladder section).

Minimum 8 rows, maximum 15 rows. Include:
- 52W high and low (bookends)
- All named levels (POC, VAH, VAL)
- Current price (marked with ◄)
- Key HVNs (top 3 above and below current price)
- VWAP anchors

---

## Step 9 — Write the Verdict

Follow the exact format in `guide/verdict-format.md`. Include every section.

---

## Step 10 — Self-Improvement Audit

Read `guide/self-improvement.md`. For every step of this protocol:
- Did the step work as documented?
- Was any threshold ambiguous?
- Did any API call fail?
- Was any output section unclear?

Write the audit block at the end of the verdict file.

---

## Step 11 — Save Output

Write the complete verdict to:
```
scanned/YYYY-MM-DD_SYMBOL.md
```

If a file for this symbol already exists today, append `_2`, `_3`, etc.

---

## Step 12 — Report to User

Give the user a 2–3 sentence summary:
1. Asset class detected and macro regime
2. Composite score and conviction label
3. Trade direction and key levels (or "no trade" rationale)

Then mention the audit block findings if any were found.
