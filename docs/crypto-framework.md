# Crypto Framework — Analysis Methodology

> READ-ONLY. Do not edit during scans. Propose changes via self-improvement audit only.

## Overview

Crypto markets are driven by liquidity flows, leverage mechanics, and sentiment cycles rather than fundamentals. This framework scores four dimensions.

**Composite scoring:**
- Score ≥ +3: HIGH LONG
- Score +1 to +2: MODERATE LONG
- Score 0: NEUTRAL
- Score -1 to -2: MODERATE SHORT
- Score ≤ -3: HIGH SHORT

---

## Dimension 1 — Fear & Greed Index

**Source:** `api.alternative.me/fng/` (free, no auth)

The Fear & Greed Index aggregates volatility, market momentum, social media, dominance, and Google Trends into a 0–100 score.

| Score | Label | Trading Interpretation |
|-------|-------|----------------------|
| 0–24 | Extreme Fear | Contrarian BUY signal — retail capitulating |
| 25–44 | Fear | Mild bullish bias |
| 45–55 | Neutral | No edge |
| 56–74 | Greed | Mild bearish bias — de-risk |
| 75–100 | Extreme Greed | Contrarian SELL signal — retail euphoric |

**Scoring rule:**
- <25 → +1 (BULL)
- >75 → -1 (BEAR)
- 25–75 → 0 (NEUTRAL)

---

## Dimension 2 — Perpetual Funding Rate

**Source:** Binance public API `/fapi/v1/fundingRate`

Funding rate = the cost of holding a perp position. Longs pay shorts when positive (market biased long); shorts pay longs when negative (market biased short).

| Funding Rate | Interpretation |
|-------------|---------------|
| < -0.01% per 8h | Shorts crowded → contrarian BULL |
| -0.01% to 0.01% | Neutral |
| 0.01% to 0.05% | Mild long bias — watch |
| > 0.05% per 8h | Longs crowded → contrarian BEAR |
| > 0.1% per 8h | Extreme — high liquidation risk for longs |

**Scoring rule:**
- Rate < -0.01% → +1 (BULL)
- Rate > 0.1% → -1 (BEAR)
- Otherwise → 0 (NEUTRAL)

**Important:** Sustained negative funding during a downtrend = bearish, not bullish. Context matters. Use in conjunction with other dimensions.

---

## Dimension 3 — Open Interest Trend

**Source:** Binance public API `/fapi/v1/openInterest`

Open Interest (OI) = total number of open contracts. Rising OI = new money entering; falling OI = positions closing (conviction declining).

| Price | OI | Interpretation |
|-------|----|---------------|
| ↑ | ↑ | BULL — new longs entering, trend continuation |
| ↑ | ↓ | Short squeeze / weak rally — fading |
| ↓ | ↑ | BEAR — new shorts entering, trend continuation |
| ↓ | ↓ | Long squeeze / weak decline — bottoming possible |

**Scoring rule:**
- Price change +5% AND OI change +5% (30d) → +1 (BULL)
- Price change -5% AND OI change +5% (30d) → -1 (BEAR)
- Otherwise → 0 (NEUTRAL)

---

## Dimension 4 — Max Pain (Near Expiry Only)

**What it is:** The strike price at which the maximum number of option contracts expire worthless. Market makers are incentivized to pin price near max pain near expiry.

**When to use:** Only within 5 days of a major options expiry (monthly/quarterly). Ignore otherwise.

**Rule:** If current price is >5% above max pain and expiry <5 days away → mild BEAR bias (pin risk). If >5% below max pain → mild BULL bias.

---

## On-Chain Signals (Supplemental)

Use these qualitatively — they do not feed into the scoring yet (data requires paid APIs or manual lookup).

**Exchange Netflow:**
- Large outflows from exchanges = accumulation (users moving to cold storage)
- Large inflows to exchanges = distribution (users preparing to sell)

**SOPR (Spent Output Profit Ratio):**
- SOPR >1 = coins being sold at profit (profit-taking pressure)
- SOPR <1 = coins being sold at loss (capitulation — contrarian buy)

**MVRV Ratio (Market Value ÷ Realized Value):**
- MVRV >3.5 = historically overbought
- MVRV <1 = historically oversold (strong buy zone)

---

## Asset-Specific Notes

**BTC (Bitcoin):** Macro-correlated. Treat like risk-on tech when in Goldilocks; safe haven narrative only partial. Halving cycles matter — first 12–18 months post-halving historically bullish.

**ETH (Ethereum):** Correlated to BTC but with higher beta. Staking yield (currently ~3.5% APR) provides a floor narrative. Watch ETH/BTC ratio for relative strength.

**Altcoins:** High beta to BTC. Only scan with conviction in clear GOLDILOCKS or REFLATION macro regime. In RISK-OFF, altcoins lead to the downside.
