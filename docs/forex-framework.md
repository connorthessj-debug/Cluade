# Forex Framework — Analysis Methodology

> READ-ONLY. Do not edit during scans. Propose changes via self-improvement audit only.

## Overview

Forex markets are driven by three forces: **interest rate differentials**, **positioning** (CFTC COT), and **macro regime flows**. All three must align for a high-conviction trade. Score three dimensions.

**Composite scoring:**
- Score ≥ +2: MODERATE-HIGH LONG (base currency)
- Score +1: MODERATE LONG
- Score 0: NEUTRAL
- Score -1: MODERATE SHORT
- Score ≤ -2: MODERATE-HIGH SHORT

---

## Dimension 1 — CFTC COT Positioning

**Source:** CFTC Socrata API (free, no auth) via `fetch_cot.py`

The Commitments of Traders (COT) report shows positioning by trader category. We focus on **Non-Commercial (large speculator)** net position — these are the trend-following hedge funds.

**COT Index Formula:**
```
COT Index = (Current Net - 52W Min Net) ÷ (52W Max Net - 52W Min Net) × 100
```

| COT Index | Interpretation |
|-----------|---------------|
| 80–100 | Specs EXTREME LONG → contrarian BEAR signal |
| 60–79 | Specs LONG BIAS → mild bearish lean |
| 40–59 | NEUTRAL — no edge |
| 20–39 | Specs SHORT BIAS → mild bullish lean |
| 0–19 | Specs EXTREME SHORT → contrarian BULL signal |

**Why contrarian?** Large specs are momentum traders — they are most positioned at the wrong time (tops and bottoms). When they are all-in one direction, the move is often exhausted.

**Scoring rule:**
- COT Index < 20 → +1 (BULL — contrarian, specs crowded short)
- COT Index > 80 → -1 (BEAR — contrarian, specs crowded long)
- Otherwise → 0 (NEUTRAL)

---

## Dimension 2 — Interest Rate Differential

**Concept:** Capital flows to the currency offering higher real interest rates. Real rate = nominal rate − inflation expectation.

**For USD pairs:**
- Use FRED series DGS10 for US 10Y yield
- Foreign central bank rates must be manually entered (ECB, BOJ, BOE, etc.)
- Real rate differential = US_rate − foreign_rate − (US_CPI − foreign_CPI)

**Scoring rule (directional, base currency vs USD):**
| Condition | Signal |
|-----------|--------|
| Base currency real rate rising relative to USD | +1 BULL base |
| Base currency real rate falling relative to USD | -1 BEAR base |
| Rates converging or stable | 0 NEUTRAL |

**Common rate differential plays:**
- **EUR/USD**: ECB vs Fed rate expectations drive the pair
- **USD/JPY**: BOJ yield curve control vs US rates — when US rates rise, JPY weakens
- **GBP/USD**: BOE credibility premium / inflation premium
- **AUD/USD**: Commodity proxy — iron ore/copper correlate, RBA vs Fed

**Note:** `fetch_fred.py` provides US rates. Foreign rates require manual input or extension of `fetch_fred.py` to include ECB/BOJ feeds.

---

## Dimension 3 — Macro Regime Alignment

Cross-reference the current macro regime (from `/scan-macro`) with currency pair behavior:

| Regime | Strong Currency | Weak Currency |
|--------|----------------|---------------|
| GOLDILOCKS | Risk-on FX (AUD, NZD, EM) | USD, JPY, CHF |
| REFLATION | Commodity FX (AUD, CAD, NOK) | EUR, JPY |
| STAGFLATION | USD, CHF | AUD, NZD, EM, GBP |
| RISK-OFF | USD, JPY, CHF | AUD, NZD, EM, commodity FX |

**Scoring rule:**
- Pair direction aligns with regime playbook → +1
- Pair direction opposes regime playbook → -1
- No clear alignment → 0

---

## Key Forex Indicators

**Dollar Index (DXY):**
- DXY rising = broad USD strength (bearish for EUR/USD, AUD/USD, GBP/USD, bullish for USD/JPY)
- Watch: 50SMA and 200SMA on DXY for trend confirmation

**Retail Sentiment (contrarian proxy):**
- Most retail forex brokers publish retail positioning data
- When >70% of retail traders are long → fade the crowd → SHORT
- When >70% of retail traders are short → fade the crowd → LONG
- Source: IG/FXCM retail sentiment pages (manual lookup; not automated by current scripts)

**Central Bank Divergence:**
- Most reliable when one central bank is hiking while another is cutting/pausing
- Rate hike expectations (priced into futures) matter more than actual rate level

---

## Trade Structure for Forex

- **Stop placement:** Beyond the nearest significant level (daily high/low, weekly open, round number)
- **Minimum R:R target:** 1:1.5 for a 3-signal aligned trade, 1:2 preferred
- **Avoid trading:** In the 30 minutes before/after major data releases (NFP, CPI, FOMC, ECB)
- **Session awareness:** EUR/USD most liquid 08:00–12:00 ET; USD/JPY most volatile at Tokyo open and NY overlap
