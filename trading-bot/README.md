# Multi-Agent Trading Bot System

An auto-improving trading system with three specialized bots and a real-time web dashboard.

## Bots

### 1. Stablecoin Arbitrage Bot
- Trades USD/USDC/USDT spreads across Binance and Coinbase
- Monitors real-time order books for profitable spreads
- Near-simultaneous execution on both exchanges

### 2. SMC Scalper Bot (OANDA)
- Forex scalping using Smart Money Concepts
- Multi-timeframe analysis: H1 → M15 → M5 → M1
- Targets 1:2+ R:R with max 0.5% risk per trade
- Instruments: EUR/USD, GBP/USD, USD/JPY, XAU/USD

### 3. SMC Swing Bot (OANDA)
- Swing trading using Smart Money Concepts
- Multi-timeframe: W1 → D1 → H4 → H1
- Targets 1:3+ R:R with partial profit taking
- Max 1% risk per trade

## Auto-Improvement
- Bayesian parameter optimization
- Pattern memory with historical success rates
- Performance analysis with actionable recommendations

## Setup

1. Copy `.env.example` to `.env` and add your API keys
2. Install Python dependencies: `pip install -r requirements.txt`
3. Install dashboard dependencies: `cd dashboard && npm install`
4. Run all bots: `python scripts/run_all.py`
5. Open dashboard: http://localhost:8080

## Development

Run a single bot: `python scripts/run_bot.py scalper`
Run tests: `python -m pytest tests/`
Backtest: `python scripts/backtest.py --bot scalper --instrument EUR_USD --start 2024-01-01 --end 2024-12-31`

## 24/7 Operation

For production, use systemd:
```
[Unit]
Description=Trading Bot System
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/trading-bot
ExecStart=/usr/bin/python3 scripts/run_all.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Disclaimer
This software is for educational purposes. Trading carries risk. Use at your own discretion. Always start with paper trading (OANDA practice account).
