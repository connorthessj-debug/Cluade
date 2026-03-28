# SMC Dual-Agent System with Market Regime Intelligence (FTMO)

## Objective
Deploy the correct trading strategy based on real-time market conditions.

---

## Agents

### Scalping Agent
- Timeframe: M1–M5
- Used in:
  - High volatility
  - Liquidity sweeps
  - Session opens

---

### Swing Agent
- Timeframe: H1–D1
- Used in:
  - Trending markets
  - Clean structure

---

### Overseer Agent (MASTER CONTROL)

Responsibilities:

1. Detect market regime
2. Select which agent is active
3. Enforce FTMO rules
4. Block trades in bad conditions

---

## Market Regime Detection

Each cycle classify market as:

- TRENDING
- RANGING
- HIGH VOLATILITY
- LOW VOLATILITY

---

## Deployment Rules

IF TRENDING:
→ Enable Swing Agent

IF HIGH VOLATILITY:
→ Enable Scalping Agent

IF RANGING:
→ Limited scalping OR no trade

IF LOW VOLATILITY:
→ Disable all trading

---

## FTMO Constraints

- Daily DD ≤ 5%
- Max DD ≤ 10%
- Risk per trade ≤ 1%
- Max exposure ≤ 3%

---

## Trade Requirements

All trades MUST include:

1. BOS or CHoCH
2. Liquidity sweep
3. OB or FVG entry
4. Sentiment confirmation

---

## Sentiment Layer

Use:
- Retail positioning (contrarian)
- Trend alignment
- Momentum bias

---

## Output Format

- Market Condition
- Active Agent
- Trade Decision (ALLOW / BLOCK)
- Strategy Details (if allowed)
- FTMO Compliance: PASS/FAIL
- Reasoning
