# Changelog — SMC MNQ Strategy

All auto-improvements by the Claude Code scheduled agent are logged here.

## [1.0.0] - 2026-03-29

### Initial Release
- Full SMC suite: BOS, CHoCH, Order Blocks, FVGs, Liquidity Sweeps, Premium/Discount
- Multi-timeframe: 4H bias + 15m entries
- Risk management: ATR-based SL, configurable R:R, optional trailing stop
- Slippage simulation: 2 ticks per fill
- Commission simulation: $0.62 round-trip
- Session filter: 0930-1600 ET
- Max 3 trades per day
- Visual overlays optimized for iPhone
- Push notification alerts for entries, CHoCH, and liquidity sweeps
