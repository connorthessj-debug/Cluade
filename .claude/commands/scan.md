You are running a trading research scan for the symbol: $ARGUMENTS

Follow every step below in order. Do not skip steps. If a step fails (API error, missing data), note it and continue.

---

## STEP 0 — Read the Protocol

Before doing anything else, read the file `guide/scan-protocol.md`. That file is the master checklist you will follow. This prompt is a thin wrapper — the intelligence lives in the docs.

Also read `guide/verdict-format.md` now so you know exactly what your output must look like.

---

## STEP 1 — Detect Asset Class

Classify `$ARGUMENTS` using these rules:
- Ends with USDT/BTC/ETH, or is BTC/ETH/SOL/BNB/XRP/ADA/AVAX/DOGE/DOT/LINK/LTC → **crypto**
- Exactly 6 chars, both halves are currency codes (EURUSD, GBPJPY, AUDUSD, etc.) → **forex**
- One of: SPX, SPY, QQQ, NDX, IWM, DIA, VIX, ES, NQ → **index**
- Otherwise → **equity**

State the detected asset class explicitly.

---

## STEP 2 — Fetch Macro Context (ALL asset classes)

Run this regardless of asset class:
```
python3 scripts/fetch_fred.py
```

Read `docs/macro-framework.md`. Map the output to a regime (GOLDILOCKS / REFLATION / STAGFLATION / RISK-OFF). State the regime and the 2–3 indicators that determined it.

Note: `fetch_fred.py` requires the `FRED_API_KEY` environment variable. If not set, note it as a data gap and continue.

---

## STEP 3 — Fetch Asset-Specific Data

**If equity:**
```
python3 scripts/fetch_equity.py $ARGUMENTS
python3 scripts/fetch_edgar.py $ARGUMENTS
python3 scripts/fetch_options.py $ARGUMENTS
python3 scripts/fetch_news.py $ARGUMENTS
```
Read: `docs/equity-fundamentals.md`, `docs/volume-profile-vwap.md`

**If crypto:**
```
python3 scripts/fetch_crypto.py $ARGUMENTS
python3 scripts/fetch_binance.py $ARGUMENTS
python3 scripts/fetch_news.py $ARGUMENTS
```
Read: `docs/crypto-framework.md`

**If index:**
```
python3 scripts/fetch_equity.py $ARGUMENTS
python3 scripts/fetch_options.py $ARGUMENTS
python3 scripts/fetch_news.py $ARGUMENTS
```
Read: `docs/equity-fundamentals.md` (pillars 5–6), `docs/volume-profile-vwap.md`

**If forex:**
```
python3 scripts/fetch_cot.py $ARGUMENTS
python3 scripts/fetch_news.py $ARGUMENTS
```
Read: `docs/forex-framework.md`

---

## STEP 4 — Score Each Dimension

Apply the exact scoring thresholds from the framework docs you just read. For each dimension:
- Extract the relevant value from the JSON
- Apply the rule
- Record: name, score (+1/0/-1), 1-sentence rationale

Do not invent thresholds. If a rule doesn't cover a specific case, score 0 and flag it in the audit.

---

## STEP 5 — Identify Key Price Levels

For equity/index: extract from fetch_equity.py output: current price, 52W high/low, POC, VAH, VAL, top HVNs, SMA50, SMA200, anchored VWAP.

For crypto: current price, 24h/30d high/low, key round numbers.

For forex: current rate, weekly high/low.

---

## STEP 6 — Build Trade Structure

Using scores and levels, determine:
- Direction (positive score = LONG, negative = SHORT, zero = NO TRADE)
- Entry zone (VAL/HVN for longs, VAH/HVN for shorts)
- Stop (below VAL or nearest LVN; minimum 2×ATR)
- Target 1 (next significant level in trade direction)
- Target 2 (beyond T1)
- R:R = (T1 - Entry) ÷ (Entry - Stop) — if < 1.5, label "SKIPPED — insufficient R:R"

---

## STEP 7 — Construct ASCII Price Ladder

Follow the instructions in `docs/volume-profile-vwap.md`. Minimum 8 rows, maximum 15. Mark current price with ◄.

---

## STEP 8 — Write the Verdict

Follow the exact format in `guide/verdict-format.md`. Include every section. Fill in all fields. No partial verdicts.

---

## STEP 9 — Self-Improvement Audit

Read `guide/self-improvement.md`. Review every step you just performed:
- Did each step work as documented?
- Were any thresholds ambiguous?
- Did any API call fail?
- Was any output format unclear?

Write the full audit block.

---

## STEP 10 — Save and Report

1. Write the complete verdict to: `scanned/YYYY-MM-DD_$ARGUMENTS.md`
2. Confirm the file was saved.
3. Give the user a 2–3 sentence summary: asset class, regime, composite score/conviction, trade direction and key levels (or no-trade reason).
4. If audit found issues, mention the count and that they're in the file.

---

## CRITICAL CONSTRAINTS

- NEVER edit `docs/` files. They are read-only truth.
- NEVER edit `guide/` files during a scan. Propose fixes in the audit block only.
- Always write the scanned/ file before reporting to the user.
- A scan with 3+ data gaps is LOW CONFIDENCE — say so in the summary.
