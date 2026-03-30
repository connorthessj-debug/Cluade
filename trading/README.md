# SMC MNQ Trading Agent

AI-powered Smart Money Concepts strategy for Mini Nasdaq futures (MNQ), auto-improved by Claude Code.

## What This Does

A PineScript v5 strategy that trades MNQ using institutional Smart Money Concepts:
- **Market Structure:** Break of Structure (BOS) and Change of Character (CHoCH)
- **Order Blocks:** Institutional supply/demand zones
- **Fair Value Gaps:** Price imbalances for entry refinement
- **Liquidity Sweeps:** Stop hunt detection
- **Premium/Discount Zones:** Fibonacci-based trade direction filter
- **Multi-Timeframe:** 4H bias + 15m entries

## Setup Instructions (iPhone)

### Step 1: Open TradingView
1. Download **TradingView** from the App Store if you don't have it
2. Create a free account (paper trading works on free plans)

### Step 2: Add the Strategy
1. Open TradingView on your iPhone (or use desktop for easier initial paste)
2. Search for **MNQ1!** (Micro E-mini Nasdaq 100 Futures) and open the chart
3. Set the chart timeframe to **15 minutes**
4. Tap the **+** button at the bottom → **Indicators** → **Pine Editor** (or use desktop Pine Editor)
5. Delete all default code in the editor
6. Copy the entire contents of `smc_mnq_strategy.pine` and paste it in
7. Click **Add to Chart**

### Step 3: Connect Paper Trading
1. At the bottom of the chart, tap the **Trading Panel**
2. Select **Paper Trading** as your broker
3. Connect (no credentials needed — it's simulated)
4. The strategy will now auto-execute paper trades based on SMC signals

### Step 4: Set Up Alerts (Push Notifications)
1. With the strategy on the chart, tap the **Alert** icon (clock/bell)
2. Set condition to: **SMC MNQ Agent v1.0**
3. Select **Any alert() function call**
4. Under notifications, enable **Push notification to app**
5. Set expiration to **Open-ended**
6. Create the alert

You'll now receive iPhone push notifications for:
- Long/Short entries with price, SL, and TP levels
- Change of Character (trend reversals)
- Liquidity sweeps

### Step 5: Monitor from iPhone
- **Chart:** Visual overlays show OBs (green/red boxes), FVGs (teal/orange), BOS/CHoCH labels
- **Trading Panel:** View open positions, P&L, and trade history
- **Notifications:** Real-time alerts on entries and key SMC events

## Strategy Parameters

All parameters are adjustable via the strategy settings gear icon:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Swing Lookback | 5 | Bars to confirm swing high/low |
| ATR Period | 14 | Average True Range calculation period |
| ATR SL Multiplier | 1.5 | Stop loss = ATR × this value |
| Risk:Reward | 2.0 | Take profit ratio relative to stop |
| HTF Timeframe | 4H | Higher timeframe for directional bias |
| Max Daily Trades | 3 | Trade limit per session |
| Session | 0930-1600 ET | Only trades during regular hours |
| Slippage | 2 ticks | Simulated slippage per fill |
| Commission | $0.62 | Round-trip commission per contract |

## Auto-Improvement System

A Claude Code scheduled agent runs every 30 minutes:
1. Checks if 10+ new trades have occurred since last update
2. If yes: analyzes performance, optimizes parameters, pushes updated code
3. If no: waits for next cycle

### Getting Updates
1. Check this repo for new commits on the `claude/ai-trading-agent-pinescript-d6K1I` branch
2. Copy the updated `smc_mnq_strategy.pine` code
3. Paste into TradingView Pine Editor → Save → strategy auto-applies

Changes are logged in `CHANGELOG.md`.

## Risk Disclaimer

This is a **paper trading** strategy for educational and testing purposes. Past backtest performance does not guarantee future results. Do not use real money without extensive testing and understanding of the risks involved in futures trading.
