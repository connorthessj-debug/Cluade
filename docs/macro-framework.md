# Macro Framework — Regime Quadrants

> READ-ONLY. Do not edit during scans. Propose changes via self-improvement audit only.

## Overview

The macro regime defines the environment every asset trades in. Identify the quadrant first — it overrides individual-asset signals in cases of conflict.

## The Four Regimes

Determined by two axes: **Growth** (UP / DOWN) and **Inflation** (UP / DOWN).

```
                    INFLATION UP
                         │
         STAGFLATION      │      REFLATION
         (Growth↓, CPI↑) │    (Growth↑, CPI↑)
                          │
  ───────────────────────┼───────────────────────
                          │
           RISK-OFF       │      GOLDILOCKS
         (Growth↓, CPI↓) │    (Growth↑, CPI↓)
                          │
                    INFLATION DOWN
```

---

## Regime Definitions

### GOLDILOCKS (Growth UP, Inflation DOWN)
- **Characteristics**: Strong economic expansion, falling or contained inflation, Fed neutral-to-accommodative
- **What works**: Growth equities, tech, consumer discretionary, small caps, credit spreads tighten
- **What struggles**: Gold, defensive sectors, long-duration bonds (if growth expectations rise)
- **Key signals**: Yield spread >0bps, HY spread <350bps, CPI <3%, PMI >52

### REFLATION (Growth UP, Inflation UP)
- **Characteristics**: Economy accelerating with rising prices, often early-cycle recovery or commodity supercycle
- **What works**: Commodities (oil, copper, gold), value stocks, financials (benefit from rate rises), real assets
- **What struggles**: Long-duration bonds, high-multiple growth stocks
- **Key signals**: Yield spread >0bps, CPI >3%, breakeven inflation >2.5%, PMI >52

### STAGFLATION (Growth DOWN, Inflation UP)
- **Characteristics**: Worst regime — economy slowing while prices rise, Fed constrained from cutting
- **What works**: Gold, commodities, short equities, TIPs, energy
- **What struggles**: Almost everything — equities fall, bonds fall (inflation), growth stocks crushed
- **Key signals**: Yield spread <0bps (inverted), CPI >3%, PMI <50, unemployment rising

### RISK-OFF (Growth DOWN, Inflation DOWN)
- **Characteristics**: Deflationary slowdown or recession, capital preservation mode
- **What works**: US Treasuries, USD, gold, yen, defensive equities (utilities, staples)
- **What struggles**: Equities broadly, commodities, credit (spreads widen), EM assets
- **Key signals**: Yield spread <0bps, CPI <2%, PMI <48, VIX >25, HY spread >600bps

---

## Classification Rules

Use these FRED series to determine the regime:

| Indicator | Series | Threshold |
|-----------|--------|-----------|
| Growth signal | T10Y2Y (10Y-2Y yield spread) | >0 = UP, <0 = DOWN |
| Growth confirmation | BAMLH0A0HYM2 (HY spread) | <400bps = UP, >500bps = DOWN |
| Inflation signal | CPIAUCSL (CPI YoY change) | >3% = UP, <2.5% = DOWN |
| Inflation confirmation | T5YIE (5Y breakeven) | >2.5% = UP, <2% = DOWN |

When indicators conflict (e.g. yield spread positive but HY spreads wide), use the average signal direction.

---

## Asset Class Playbook by Regime

| Asset Class | Goldilocks | Reflation | Stagflation | Risk-Off |
|-------------|-----------|-----------|-------------|----------|
| US Large Cap Growth | ★★★ | ★★ | ★ | ★★ |
| US Large Cap Value | ★★ | ★★★ | ★★ | ★★ |
| Small Cap | ★★★ | ★★ | ★ | ★ |
| Commodities | ★ | ★★★ | ★★★ | ★★ |
| Gold | ★ | ★★ | ★★★ | ★★★ |
| Long-Duration Bonds | ★★ | ★ | ★ | ★★★ |
| Short-Duration Bonds | ★★ | ★★ | ★★ | ★★★ |
| USD | ★★ | ★ | ★★ | ★★★ |
| Bitcoin/Crypto | ★★★ | ★★★ | ★ | ★ |

★★★ = Favored  ★★ = Neutral  ★ = Avoid

---

## Regime Transition Signals

Watch for these to detect regime shifts early:

- **Goldilocks → Reflation**: CPI breaking above 3%, oil breaking out, commodities running
- **Reflation → Stagflation**: PMI rolling over while CPI stays high, yield curve flattening
- **Stagflation → Risk-Off**: Commodities collapsing, CPI finally falling, credit spreads exploding
- **Risk-Off → Goldilocks**: Fed pivots, yield spread re-steepening, credit spreads tightening
