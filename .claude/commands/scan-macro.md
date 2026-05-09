You are running a macro regime scan. This is a top-down read of the current macro environment.

Follow every step below in order.

---

## STEP 0 — Read the Framework

Read `docs/macro-framework.md` now. That document defines the four regimes, their indicators, and the asset class implications. Your job is to determine which quadrant we are in today.

Also read `guide/verdict-format.md` to know the output format (the macro verdict uses a simplified version).

---

## STEP 1 — Fetch Macro Data

Run:
```
python3 scripts/fetch_fred.py
python3 scripts/fetch_news.py "macro economy federal reserve"
```

Note: `fetch_fred.py` requires `FRED_API_KEY` environment variable (free key from fred.stlouisfed.org). If not set, note it as a data gap and work with whatever indicators are available.

---

## STEP 2 — Map Indicators to Regime

Using the indicator table in `docs/macro-framework.md`:

For each of the 4–5 key indicators (yield spread, HY spread, CPI YoY, breakeven inflation, VIX), determine whether it points GROWTH UP/DOWN or INFLATION UP/DOWN.

Count votes on each axis:
- Majority GROWTH UP + Majority INFLATION DOWN → GOLDILOCKS
- Majority GROWTH UP + Majority INFLATION UP → REFLATION
- Majority GROWTH DOWN + Majority INFLATION UP → STAGFLATION
- Majority GROWTH DOWN + Majority INFLATION DOWN → RISK-OFF

If it's a tie on either axis, label that axis TRANSITIONING.

---

## STEP 3 — Write the Macro Verdict

Write a structured verdict using this format:

```
# MACRO SCAN — YYYY-MM-DD HH:MM UTC

## Regime: {GOLDILOCKS | REFLATION | STAGFLATION | RISK-OFF | TRANSITIONING}

### Indicator Scorecard
| Indicator | Value | Signal |
|-----------|-------|--------|
| 10Y–2Y Yield Spread | {value} bps | {GROWTH UP/DOWN} |
| HY Credit Spread | {value} bps | {GROWTH UP/DOWN} |
| CPI YoY | {value}% | {INFLATION UP/DOWN} |
| 5Y Breakeven | {value}% | {INFLATION UP/DOWN} |
| VIX | {value} | {context} |
| Fed Funds Rate | {value}% | {context} |

Growth axis: {UP | DOWN | TRANSITIONING} ({N}/{M} indicators)
Inflation axis: {UP | DOWN | TRANSITIONING} ({N}/{M} indicators)

### Asset Class Implications

| Asset Class | Bias | Rationale |
|-------------|------|-----------|
| US Equities (Growth) | {BULL/NEUTRAL/BEAR} | |
| US Equities (Value) | {BULL/NEUTRAL/BEAR} | |
| Commodities | {BULL/NEUTRAL/BEAR} | |
| Gold | {BULL/NEUTRAL/BEAR} | |
| Long-Duration Bonds | {BULL/NEUTRAL/BEAR} | |
| USD | {BULL/NEUTRAL/BEAR} | |
| Bitcoin/Crypto | {BULL/NEUTRAL/BEAR} | |

### Key Risks / Transition Signals to Watch
{2–4 bullet points: what would flip the regime in the next 30–60 days}

### News Sentiment
{2–3 sentences from fetch_news.py headlines}

## Self-Improvement Audit
### Issues Found
- [ ] {Issue or "No issues found this scan."}
### Proposed Fixes
- {Fix or "No improvements proposed."}
**AWAITING USER CONSENT before editing any guide/ or docs/ files.**
```

---

## STEP 4 — Save and Report

1. Write the verdict to: `scanned/YYYY-MM-DD_MACRO.md`
2. Confirm saved.
3. Give a 3–4 sentence user-facing summary: the regime, the 2 strongest supporting indicators, and the top 1–2 asset class implications.
4. Mention any audit findings.

---

## CRITICAL CONSTRAINTS

- NEVER edit `docs/` files during this scan.
- NEVER edit `guide/` files during this scan — propose fixes in the audit block only.
- Always save the file before reporting.
