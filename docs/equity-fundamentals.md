# Equity Fundamentals — 6-Pillar Framework

> READ-ONLY. Do not edit during scans. Propose changes via self-improvement audit only.

## Overview

Every equity scan scores six pillars. Each scores +1 (BULL), 0 (NEUTRAL), or -1 (BEAR).
Composite score determines conviction level.

```
Score ≥ +4  → HIGH LONG
Score +1 to +3 → MODERATE LONG
Score  0       → NEUTRAL — NO TRADE
Score -1 to -3 → MODERATE SHORT
Score ≤ -4  → HIGH SHORT
```

---

## Pillar 1 — Earnings

**What to measure:**
- EPS beat rate over last 8 quarters (from fetch_edgar.py / yfinance earnings history)
- YoY earnings growth rate (most recent quarter vs same quarter prior year)
- Revenue growth rate (same basis)
- Guidance trend: raised / maintained / lowered

**Scoring:**
| Condition | Score |
|-----------|-------|
| Beat rate ≥6/8 AND YoY EPS growth >10% | +1 BULL |
| Beat rate ≤3/8 OR YoY EPS growth <-5% | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Key data source:** `fetch_equity.py` → `earnings_history[]`, `fetch_edgar.py` → `financials`

---

## Pillar 2 — Balance Sheet

**What to measure:**
- Debt-to-Equity ratio (%)
- Current ratio
- Free Cash Flow yield (FCF / Market Cap × 100)
- Trend: is debt growing or shrinking?

**Scoring:**
| Condition | Score |
|-----------|-------|
| D/E <50% AND Current ratio >2.0 AND FCF yield >3% | +1 BULL |
| D/E >200% OR Current ratio <1.0 OR FCF yield <0% | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Key data source:** `fetch_equity.py` → `fundamental.debt_to_equity`, `current_ratio`, `free_cashflow`, `market_cap`

---

## Pillar 3 — Valuation

**What to measure:**
- Forward P/E vs sector median
- PEG ratio (P/E ÷ earnings growth rate)
- Price/Sales vs historical average
- EV/EBITDA (when available)

**Scoring:**
| Condition | Score |
|-----------|-------|
| PEG <1.0 AND Forward P/E <25 | +1 BULL |
| PEG >2.5 OR Forward P/E >50 | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Note:** Adjust thresholds for sector. Tech may warrant higher P/E; utilities should be scored vs 15–20x.

**Key data source:** `fetch_equity.py` → `fundamental.pe_forward`, `peg_ratio`, `price_to_sales`

---

## Pillar 4 — Insider & Institutional Activity

**What to measure:**
- Form 4 filings (last 90 days): net shares acquired vs disposed
- Institutional ownership % and recent change
- Short interest % of float (high = potential squeeze or fundamental concern)

**Scoring:**
| Condition | Score |
|-----------|-------|
| Net insider buying >10,000 shares last 90d AND inst ownership trending up | +1 BULL |
| Net insider selling >50,000 shares last 90d AND short interest rising | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Nuance:** Insider selling at-the-money option exercises is noise. Focus on open-market purchases — those signal conviction.

**Key data source:** `fetch_edgar.py` → `insider_activity`, `fetch_equity.py` → `positioning`

---

## Pillar 5 — Options Flow & Positioning

**What to measure:**
- Put/Call ratio (per expiry and blended): <0.7 = bullish, >1.3 = bearish
- Net Gamma Exposure (GEX): positive = market makers long gamma (dampens moves), negative = short gamma (amplifies moves)
- Short interest % of float: >20% = elevated (squeeze candidate or fundamental short)
- Dark pool / block trade skew (if available)

**Scoring:**
| Condition | Score |
|-----------|-------|
| P/C ratio <0.7 AND net GEX >0 (positive) | +1 BULL |
| P/C ratio >1.3 AND net GEX <0 (negative) | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Key data source:** `fetch_options.py` → `summary.avg_pcr`, `total_net_gex`

---

## Pillar 6 — Technical Structure

**What to measure:**
- Price relative to SMA-50 and SMA-200
- RSI-14 zone (oversold <30 / neutral 40-70 / overbought >75)
- Volume Profile: is price above or below POC? At VAH/VAL?
- Anchored VWAP: above = healthy, below = under distribution
- ATR-14: for position sizing (use 2×ATR as max stop distance)

**Scoring:**
| Condition | Score |
|-----------|-------|
| Price > SMA50 > SMA200 AND RSI 45–70 AND price near or above POC | +1 BULL |
| Price < SMA50 < SMA200 AND (RSI <35 falling OR RSI >75 and declining) | -1 BEAR |
| Otherwise | 0 NEUTRAL |

**Key data source:** `fetch_equity.py` → `technical`, `volume_profile`

---

## Position Sizing

Use ATR-14 to size positions. Never risk more than 1R on a single trade.

```
Stop distance = max(chart_stop_distance, 2 × ATR14)
Position size = (Account × risk_pct) ÷ stop_distance_in_dollars
```

Example: $100,000 account, 1% risk, stop $5 below entry → 200 shares max.
