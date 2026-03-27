#!/usr/bin/env python3
"""Backtest trading strategies against historical data."""

import argparse
import asyncio
import csv
import logging
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on the import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest")

OUTPUT_DIR = PROJECT_ROOT / "data" / "backtest"


# ---------------------------------------------------------------------------
# OANDA historical data fetcher
# ---------------------------------------------------------------------------

class OandaDataFetcher:
    """Fetch historical candles from the OANDA REST API."""

    GRANULARITY_MAP = {
        "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
        "H1": "H1", "H4": "H4", "D1": "D", "W1": "W",
    }

    def __init__(self, config):
        self.base_url = config.oanda.base_url
        self.token = config.oanda.access_token
        self.account_id = config.oanda.account_id

    async def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        start: str,
        end: str,
    ) -> List[Dict[str, Any]]:
        """Fetch candles from OANDA v20 API.

        Args:
            instrument: e.g. 'EUR_USD'.
            granularity: e.g. 'H1', 'D1'.
            start: ISO date string (YYYY-MM-DD).
            end: ISO date string.

        Returns:
            List of dicts with keys: timestamp, open, high, low, close, volume.
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp is required for OANDA data fetching. "
                         "Install with: pip install aiohttp")
            return []

        gran = self.GRANULARITY_MAP.get(granularity, granularity)
        url = f"{self.base_url}/v3/accounts/{self.account_id}/instruments/{instrument}/candles"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        all_candles: List[Dict[str, Any]] = []
        current_start = f"{start}T00:00:00.000000000Z"
        end_dt = datetime.fromisoformat(end)

        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    "granularity": gran,
                    "from": current_start,
                    "count": 5000,
                    "price": "M",  # mid prices
                }

                try:
                    async with session.get(url, headers=headers, params=params) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            logger.error("OANDA API error %d: %s", resp.status, text)
                            break

                        data = await resp.json()
                        candles = data.get("candles", [])

                        if not candles:
                            break

                        for c in candles:
                            if not c.get("complete", False):
                                continue
                            mid = c["mid"]
                            ts = datetime.fromisoformat(
                                c["time"].replace("000Z", "+00:00").rstrip("Z")
                            )
                            if ts > end_dt:
                                return all_candles

                            all_candles.append({
                                "timestamp": ts.timestamp(),
                                "open": float(mid["o"]),
                                "high": float(mid["h"]),
                                "low": float(mid["l"]),
                                "close": float(mid["c"]),
                                "volume": float(c.get("volume", 0)),
                            })

                        # Advance the start to after the last candle
                        last_time = candles[-1]["time"]
                        if current_start == last_time:
                            break
                        current_start = last_time

                except Exception as e:
                    logger.error("Error fetching candles: %s", e)
                    break

        return all_candles


# ---------------------------------------------------------------------------
# Simulated order execution
# ---------------------------------------------------------------------------

class SimulatedExecution:
    """Simulate trade execution with configurable slippage."""

    def __init__(self, slippage_pips: float = 0.5, spread_pips: float = 1.0):
        self.slippage_pips = slippage_pips
        self.spread_pips = spread_pips

    def fill_price(self, price: float, direction: str, pip_value: float = 0.0001) -> float:
        """Apply slippage to get simulated fill price."""
        slippage = self.slippage_pips * pip_value
        if direction == "long":
            return price + slippage
        else:
            return price - slippage


# ---------------------------------------------------------------------------
# Trade record for backtesting
# ---------------------------------------------------------------------------

class BacktestTrade:
    """Record of a single backtest trade."""

    def __init__(
        self,
        entry_time: float,
        entry_price: float,
        direction: str,
        stop_loss: float,
        take_profit: float,
        confluence_score: float = 0.0,
    ):
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.direction = direction
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.confluence_score = confluence_score
        self.exit_time: Optional[float] = None
        self.exit_price: Optional[float] = None
        self.pnl: float = 0.0
        self.exit_reason: str = ""
        self.r_multiple: float = 0.0

    @property
    def risk(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0


# ---------------------------------------------------------------------------
# Backtesting engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Replay candles through a strategy and track results."""

    def __init__(
        self,
        bot_type: str,
        instrument: str,
        slippage_pips: float = 0.5,
    ):
        self.bot_type = bot_type
        self.instrument = instrument
        self.execution = SimulatedExecution(slippage_pips=slippage_pips)
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[Tuple[float, float]] = []
        self.initial_balance = 10000.0
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.max_drawdown = 0.0
        self.pip_value = 0.01 if "JPY" in instrument else 0.0001

    def run(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run the backtest on historical candle data.

        Args:
            candles: List of dicts with timestamp, open, high, low, close, volume.

        Returns:
            Dict of performance metrics.
        """
        from smc.models import OHLCV
        from smc.market_structure import detect_swing_points, get_trend
        from smc.order_blocks import find_order_blocks
        from smc.fair_value_gaps import find_fvg
        from smc.market_structure import detect_bos
        from smc.confluence import score_setup, calculate_sl_tp
        from smc.fibonacci import calculate_ote_zone

        if not candles:
            logger.error("No candle data to backtest")
            return {}

        # Convert to OHLCV objects
        ohlcv_list = [
            OHLCV(
                timestamp=c["timestamp"],
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c["volume"],
            )
            for c in candles
        ]

        logger.info(
            "Backtesting %s on %s: %d candles",
            self.bot_type, self.instrument, len(ohlcv_list),
        )

        # Determine lookback window based on bot type
        if self.bot_type == "scalper":
            lookback = 50
            min_confluence = 60
            min_rr = 2.0
        else:  # swing
            lookback = 100
            min_confluence = 65
            min_rr = 3.0

        open_trade: Optional[BacktestTrade] = None
        self.equity_curve = [(ohlcv_list[0].timestamp, self.balance)]

        for i in range(lookback, len(ohlcv_list)):
            window = ohlcv_list[max(0, i - lookback):i + 1]
            current = ohlcv_list[i]

            # Check if we have an open trade -- manage it
            if open_trade is not None:
                closed = self._check_trade_exit(open_trade, current)
                if closed:
                    self.trades.append(open_trade)
                    open_trade = None
                continue

            # Analyze market structure
            swing_points = detect_swing_points(window, lookback=3)
            if len(swing_points) < 4:
                continue

            trend = get_trend(swing_points)
            if trend == "ranging":
                continue

            # Detect BOS for order blocks
            bos_list = detect_bos(window, swing_points)
            order_blocks = find_order_blocks(window, bos_list, lookback=15)

            # Detect FVGs
            fvgs = find_fvg(window)

            # Determine direction based on trend
            if trend == "bullish":
                direction = "long"
            else:
                direction = "short"

            # Calculate Fibonacci / OTE zone
            swing_highs = [sp.price for sp in swing_points if sp.type == "high"]
            swing_lows = [sp.price for sp in swing_points if sp.type == "low"]
            if not swing_highs or not swing_lows:
                continue
            sh = max(swing_highs)
            sl_price = min(swing_lows)
            if sh <= sl_price:
                continue
            fib_data = calculate_ote_zone(sl_price, sh)

            # Score using the confluence module
            setup = score_setup(
                trend=trend,
                order_blocks=order_blocks,
                fvgs=fvgs,
                liquidity_levels=[],
                fib_data=fib_data,
                current_price=current.close,
                direction=direction,
            )

            if setup.confluence_score < min_confluence:
                continue

            # Calculate SL/TP
            # Find the matching OB for SL placement
            matching_ob = None
            target_type = "bullish" if direction == "long" else "bearish"
            for ob in order_blocks:
                if ob.type == target_type and not ob.mitigated:
                    matching_ob = ob
                    break

            sl_tp = calculate_sl_tp(
                direction=direction,
                entry_price=current.close,
                order_block=matching_ob,
                liquidity_levels=[],
                min_rr=min_rr,
            )

            # Apply slippage to entry
            fill = self.execution.fill_price(current.close, direction, self.pip_value)

            open_trade = BacktestTrade(
                entry_time=current.timestamp,
                entry_price=fill,
                direction=direction,
                stop_loss=sl_tp["stop_loss"],
                take_profit=sl_tp["take_profit"],
                confluence_score=setup.confluence_score,
            )

            self.equity_curve.append((current.timestamp, self.balance))

        # Close any remaining open trade at last price
        if open_trade is not None:
            open_trade.exit_time = ohlcv_list[-1].timestamp
            open_trade.exit_price = ohlcv_list[-1].close
            risk = open_trade.risk
            if open_trade.direction == "long":
                open_trade.pnl = open_trade.exit_price - open_trade.entry_price
            else:
                open_trade.pnl = open_trade.entry_price - open_trade.exit_price
            open_trade.r_multiple = open_trade.pnl / risk if risk > 0 else 0
            open_trade.exit_reason = "end_of_data"
            if risk > 0:
                self.balance += open_trade.pnl * (self.initial_balance * 0.01 / risk)
            self.trades.append(open_trade)

        return self._calculate_metrics()

    def _check_trade_exit(self, trade: BacktestTrade, candle) -> bool:
        """Check if a trade should be closed on this candle."""
        risk = trade.risk
        if risk <= 0:
            trade.exit_price = candle.close
            trade.exit_time = candle.timestamp
            trade.pnl = 0
            trade.exit_reason = "zero_risk"
            return True

        if trade.direction == "long":
            if candle.low <= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.exit_time = candle.timestamp
                trade.pnl = trade.stop_loss - trade.entry_price
                trade.r_multiple = trade.pnl / risk
                trade.exit_reason = "stop_loss"
                self.balance += trade.pnl * (self.initial_balance * 0.01 / risk)
                self._update_drawdown()
                return True
            if candle.high >= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.exit_time = candle.timestamp
                trade.pnl = trade.take_profit - trade.entry_price
                trade.r_multiple = trade.pnl / risk
                trade.exit_reason = "take_profit"
                self.balance += trade.pnl * (self.initial_balance * 0.01 / risk)
                self._update_drawdown()
                return True
        else:
            if candle.high >= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.exit_time = candle.timestamp
                trade.pnl = trade.entry_price - trade.stop_loss
                trade.r_multiple = trade.pnl / risk
                trade.exit_reason = "stop_loss"
                self.balance += trade.pnl * (self.initial_balance * 0.01 / risk)
                self._update_drawdown()
                return True
            if candle.low <= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.exit_time = candle.timestamp
                trade.pnl = trade.entry_price - trade.take_profit
                trade.r_multiple = trade.pnl / risk
                trade.exit_reason = "take_profit"
                self.balance += trade.pnl * (self.initial_balance * 0.01 / risk)
                self._update_drawdown()
                return True

        self.equity_curve.append((candle.timestamp, self.balance))
        return False

    def _update_drawdown(self):
        """Update peak balance and max drawdown."""
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        drawdown = (self.peak_balance - self.balance) / self.peak_balance
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive backtest metrics."""
        total_trades = len(self.trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "final_balance": self.balance,
                "total_return_pct": 0.0,
            }

        winners = [t for t in self.trades if t.is_winner]
        losers = [t for t in self.trades if not t.is_winner]
        win_rate = len(winners) / total_trades * 100

        gross_profit = sum(t.pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        r_multiples = [t.r_multiple for t in self.trades]
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0
        if len(r_multiples) > 1:
            variance = sum((r - avg_r) ** 2 for r in r_multiples) / (len(r_multiples) - 1)
            std_r = math.sqrt(variance)
            sharpe = avg_r / std_r if std_r > 0 else 0
        else:
            sharpe = 0

        total_return = (self.balance - self.initial_balance) / self.initial_balance * 100
        avg_winner = sum(t.r_multiple for t in winners) / len(winners) if winners else 0
        avg_loser = sum(t.r_multiple for t in losers) / len(losers) if losers else 0

        return {
            "total_trades": total_trades,
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "avg_r_multiple": round(avg_r, 3),
            "avg_winner_r": round(avg_winner, 3),
            "avg_loser_r": round(avg_loser, 3),
            "final_balance": round(self.balance, 2),
            "total_return_pct": round(total_return, 2),
        }

    def save_results(self, output_dir: Path) -> None:
        """Save equity curve and trade log as CSV files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        prefix = f"{self.bot_type}_{self.instrument}_{timestamp}"

        # Equity curve
        equity_path = output_dir / f"{prefix}_equity.csv"
        with open(equity_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "balance"])
            for ts, bal in self.equity_curve:
                dt = datetime.utcfromtimestamp(ts).isoformat() if ts > 1e9 else ts
                writer.writerow([dt, round(bal, 2)])
        logger.info("Equity curve saved: %s", equity_path)

        # Trade log
        trades_path = output_dir / f"{prefix}_trades.csv"
        with open(trades_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "entry_time", "exit_time", "direction", "entry_price",
                "exit_price", "stop_loss", "take_profit", "pnl",
                "r_multiple", "confluence_score", "exit_reason",
            ])
            for t in self.trades:
                entry_dt = datetime.utcfromtimestamp(t.entry_time).isoformat() if t.entry_time > 1e9 else t.entry_time
                exit_dt = datetime.utcfromtimestamp(t.exit_time).isoformat() if t.exit_time and t.exit_time > 1e9 else t.exit_time
                writer.writerow([
                    entry_dt, exit_dt, t.direction,
                    round(t.entry_price, 6),
                    round(t.exit_price, 6) if t.exit_price else "",
                    round(t.stop_loss, 6), round(t.take_profit, 6),
                    round(t.pnl, 6), round(t.r_multiple, 3),
                    round(t.confluence_score, 1), t.exit_reason,
                ])
        logger.info("Trade log saved: %s", trades_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def async_main(args):
    """Run the backtest asynchronously (needed for OANDA data fetching)."""
    from core.config import Config

    config = Config()

    logger.info(
        "Starting backtest: bot=%s instrument=%s period=%s to %s",
        args.bot, args.instrument, args.start, args.end,
    )

    if args.bot == "scalper":
        granularity = args.granularity or "M15"
    else:
        granularity = args.granularity or "H4"

    fetcher = OandaDataFetcher(config)
    candles = await fetcher.fetch_candles(
        instrument=args.instrument,
        granularity=granularity,
        start=args.start,
        end=args.end,
    )

    if not candles:
        logger.error("No candle data retrieved. Check your OANDA credentials and date range.")
        sys.exit(1)

    logger.info("Retrieved %d candles (%s)", len(candles), granularity)

    engine = BacktestEngine(
        bot_type=args.bot,
        instrument=args.instrument,
        slippage_pips=args.slippage,
    )
    metrics = engine.run(candles)

    print("\n" + "=" * 60)
    print(f"  BACKTEST RESULTS: {args.bot.upper()} on {args.instrument}")
    print("=" * 60)
    for key, value in metrics.items():
        label = key.replace("_", " ").title()
        print(f"  {label:.<35} {value}")
    print("=" * 60)

    engine.save_results(OUTPUT_DIR)


def main():
    parser = argparse.ArgumentParser(description="Backtest trading strategies")
    parser.add_argument(
        "--bot", required=True, choices=["scalper", "swing"],
        help="Bot strategy to backtest",
    )
    parser.add_argument(
        "--instrument", required=True,
        help="Instrument to trade (e.g. EUR_USD, GBP_USD, XAU_USD)",
    )
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--granularity", default=None,
        help="Candle granularity (default: M15 for scalper, H4 for swing)",
    )
    parser.add_argument(
        "--slippage", type=float, default=0.5,
        help="Simulated slippage in pips (default: 0.5)",
    )
    args = parser.parse_args()

    try:
        datetime.fromisoformat(args.start)
        datetime.fromisoformat(args.end)
    except ValueError:
        parser.error("Dates must be in YYYY-MM-DD format")

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
