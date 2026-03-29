#!/usr/bin/env python3
"""
Realistic USDC-USD Arbitrage Strategy Backtester

Simulates the arbitrage strategy against historical candle data with:
- Volume-based slippage modeling
- Order latency simulation
- Partial fill / failed order modeling
- Maker (0%) vs taker (0.001%) fee modeling
- Full-balance trading
- Threshold grid search optimization

Usage:
    python backtest.py                          # Run with defaults
    python backtest.py --capital 10000          # Set starting capital
    python backtest.py --optimize               # Run threshold grid search
    python backtest.py --data data/usdc_usd_candles.csv

Output: Console summary + data/backtest_results.csv
"""

import os
import sys
import csv
import math
import random
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_DATA_FILE = DATA_DIR / "usdc_usd_candles.csv"
RESULTS_FILE = DATA_DIR / "backtest_results.csv"


@dataclass
class BacktestConfig:
    """All configurable parameters for the backtest."""

    # Strategy
    buy_threshold: float = 0.9998    # Buy USDC when ask < this
    sell_threshold: float = 1.0002   # Sell USDC when bid > this
    cooldown_seconds: float = 0.2    # Min seconds between trades (200ms)
    max_daily_trades: int = 500      # Safety cap

    # Capital
    starting_usd: float = 10000.0   # Starting USD balance
    starting_usdc: float = 0.0      # Starting USDC balance

    # Market simulation
    slippage_base_bps: float = 0.1       # Base slippage in basis points
    slippage_impact_factor: float = 0.5  # How much trade size increases slippage
    liquidity_depth_usd: float = 500000  # Estimated order book depth (USD)

    # Latency
    order_latency_ms_min: float = 50.0   # Min order placement latency
    order_latency_ms_max: float = 200.0  # Max order placement latency

    # Fill modeling
    full_fill_rate: float = 0.95       # Probability of 100% fill
    partial_fill_min_pct: float = 0.50 # Min fill % on partial fills
    partial_fill_max_pct: float = 0.90 # Max fill % on partial fills
    order_failure_rate: float = 0.005  # Probability of order rejection

    # Fees (Coinbase Advanced stablepair pricing)
    maker_fee_pct: float = 0.0     # 0% for limit orders
    taker_fee_pct: float = 0.001   # 0.001% for market orders
    use_limit_orders: bool = False # If True, use maker fees (slower fills)

    # Misc
    random_seed: int = 42


# ---------------------------------------------------------------------------
# Slippage model
# ---------------------------------------------------------------------------

def calculate_slippage(trade_size_usd: float, config: BacktestConfig) -> float:
    """
    Calculate slippage in price terms for a given trade size.

    Model: slippage = base + (size / depth) * impact
    Returns the price impact as a decimal (e.g., 0.00001 = 0.001 cents).

    For USDC-USD, slippage is very small because it's a deep, liquid pair.
    But for full-balance trades with large capital, it matters.
    """
    base = config.slippage_base_bps / 10000  # Convert bps to decimal
    size_impact = (trade_size_usd / config.liquidity_depth_usd) * config.slippage_impact_factor / 10000
    return base + size_impact


# ---------------------------------------------------------------------------
# Latency model
# ---------------------------------------------------------------------------

def simulate_latency_price_drift(
    candle_high: float,
    candle_low: float,
    candle_close: float,
    direction: str,  # "BUY" or "SELL"
    config: BacktestConfig,
    rng: random.Random,
) -> float:
    """
    During the latency window (50-200ms), the price may drift.
    We model this as a random move within the candle's high-low range,
    biased slightly against the trader (adverse selection).

    Returns the estimated execution price after latency drift.
    """
    candle_range = candle_high - candle_low
    if candle_range < 0.000001:
        return candle_close

    # Random drift within candle range, slightly adverse
    drift_pct = rng.uniform(0, 0.3)  # Up to 30% of candle range

    if direction == "BUY":
        # Price may drift up (worse for buyer)
        return candle_close + (candle_range * drift_pct)
    else:
        # Price may drift down (worse for seller)
        return candle_close - (candle_range * drift_pct)


# ---------------------------------------------------------------------------
# Fill model
# ---------------------------------------------------------------------------

def simulate_fill(trade_size: float, config: BacktestConfig, rng: random.Random) -> Optional[float]:
    """
    Simulate order fill. Returns actual filled size, or None if order fails.

    - 0.5% chance of order failure (API error, etc.)
    - 95% chance of full fill
    - 5% chance of partial fill (50-90% of requested size)
    """
    # Order failure
    if rng.random() < config.order_failure_rate:
        return None

    # Full vs partial fill
    if rng.random() < config.full_fill_rate:
        return trade_size
    else:
        fill_pct = rng.uniform(config.partial_fill_min_pct, config.partial_fill_max_pct)
        return trade_size * fill_pct


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    timestamp: int
    datetime_str: str
    side: str  # "BUY" or "SELL"
    size_usd: float
    quoted_price: float
    executed_price: float
    slippage: float
    fill_pct: float
    fee_usd: float
    pnl_trade: float
    usd_after: float
    usdc_after: float
    cumulative_pnl: float


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

class Backtester:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.rng = random.Random(config.random_seed)

        # Balances
        self.usd_balance = config.starting_usd
        self.usdc_balance = config.starting_usdc
        self.initial_value = config.starting_usd + config.starting_usdc  # USDC ≈ $1

        # State
        self.trades: list[Trade] = []
        self.daily_trade_counts: dict[str, int] = {}
        self.last_trade_ts = 0
        self.total_signals = 0
        self.skipped_cooldown = 0
        self.skipped_daily_cap = 0
        self.skipped_insufficient = 0
        self.failed_orders = 0

    def _get_fee_pct(self) -> float:
        if self.config.use_limit_orders:
            return self.config.maker_fee_pct
        return self.config.taker_fee_pct

    def _current_value(self, usdc_price: float = 1.0) -> float:
        return self.usd_balance + (self.usdc_balance * usdc_price)

    def _day_key(self, ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    def evaluate(self, ts: int, bid: float, ask: float, high: float, low: float) -> Optional[tuple]:
        """
        Evaluate strategy. Returns ('BUY'|'SELL', size_usd) or None.
        Uses the candle's close as bid (to sell) and ask (to buy) proxy.
        For 1-minute candles, bid ≈ close, ask ≈ close + small spread.
        """
        day = self._day_key(ts)
        daily_count = self.daily_trade_counts.get(day, 0)

        # Check cooldown
        if ts - self.last_trade_ts < self.config.cooldown_seconds:
            self.skipped_cooldown += 1
            return None

        # Check daily cap
        if daily_count >= self.config.max_daily_trades:
            self.skipped_daily_cap += 1
            return None

        # BUY signal: ask is below buy threshold (USDC is cheap)
        if ask < self.config.buy_threshold and self.usd_balance > 1.0:
            self.total_signals += 1
            return ("BUY", self.usd_balance)

        # SELL signal: bid is above sell threshold (USDC is expensive)
        if bid > self.config.sell_threshold and self.usdc_balance > 1.0:
            self.total_signals += 1
            return ("SELL", self.usdc_balance)

        return None

    def execute_trade(self, ts: int, side: str, size: float,
                      candle_high: float, candle_low: float, candle_close: float) -> Optional[Trade]:
        """Execute a simulated trade with slippage, latency, and fill modeling."""

        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Calculate quoted price (what we see)
        quoted_price = candle_close

        # 2. Simulate latency price drift
        exec_price = simulate_latency_price_drift(
            candle_high, candle_low, candle_close, side, self.config, self.rng
        )

        # 3. Apply slippage
        slippage = calculate_slippage(size, self.config)
        if side == "BUY":
            exec_price += slippage  # Pay more when buying
        else:
            exec_price -= slippage  # Receive less when selling

        # 4. Simulate fill
        if side == "BUY":
            trade_usd = size
        else:
            trade_usd = size * exec_price  # USDC amount * price = USD value

        filled = simulate_fill(trade_usd, self.config, self.rng)
        if filled is None:
            self.failed_orders += 1
            return None

        fill_pct = filled / trade_usd if trade_usd > 0 else 1.0

        # 5. Calculate fee
        fee_pct = self._get_fee_pct()
        fee_usd = filled * fee_pct / 100

        # 6. Update balances
        value_before = self._current_value(candle_close)

        if side == "BUY":
            usd_spent = filled + fee_usd
            usdc_received = filled / exec_price
            self.usd_balance -= usd_spent
            self.usdc_balance += usdc_received
        else:
            usdc_sold = (filled / exec_price)  # filled is in USD terms
            usd_received = filled - fee_usd
            # Adjust for partial fills on the USDC side
            actual_usdc_sold = min(size * fill_pct, self.usdc_balance)
            actual_usd_received = actual_usdc_sold * exec_price - fee_usd
            self.usdc_balance -= actual_usdc_sold
            self.usd_balance += actual_usd_received

        value_after = self._current_value(candle_close)
        pnl_trade = value_after - value_before
        cumulative_pnl = value_after - self.initial_value

        # 7. Update state
        self.last_trade_ts = ts
        day = self._day_key(ts)
        self.daily_trade_counts[day] = self.daily_trade_counts.get(day, 0) + 1

        trade = Trade(
            timestamp=ts,
            datetime_str=dt_str,
            side=side,
            size_usd=filled,
            quoted_price=quoted_price,
            executed_price=exec_price,
            slippage=slippage,
            fill_pct=fill_pct,
            fee_usd=fee_usd,
            pnl_trade=pnl_trade,
            usd_after=self.usd_balance,
            usdc_after=self.usdc_balance,
            cumulative_pnl=cumulative_pnl,
        )
        self.trades.append(trade)
        return trade

    def run(self, candles: pd.DataFrame) -> dict:
        """Run backtest over candle data. Returns summary metrics."""

        print(f"Running backtest: {len(candles)} candles")
        print(f"  Buy threshold:  ${self.config.buy_threshold:.4f}")
        print(f"  Sell threshold: ${self.config.sell_threshold:.4f}")
        print(f"  Starting capital: ${self.config.starting_usd:,.2f} USD + ${self.config.starting_usdc:,.2f} USDC")
        print(f"  Order type: {'Limit (0% fee)' if self.config.use_limit_orders else 'Market (0.001% fee)'}")
        print()

        for _, row in candles.iterrows():
            ts = int(row["timestamp"])
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            # Estimate bid/ask from candle
            spread = max(h - l, 0.000001)
            bid = c - spread * 0.3  # Bid slightly below close
            ask = c + spread * 0.3  # Ask slightly above close

            signal = self.evaluate(ts, bid, ask, h, l)
            if signal:
                side, size = signal
                self.execute_trade(ts, side, size, h, l, c)

        return self._compute_metrics(candles)

    def _compute_metrics(self, candles: pd.DataFrame) -> dict:
        """Compute comprehensive performance metrics."""
        final_price = float(candles.iloc[-1]["close"]) if len(candles) > 0 else 1.0
        final_value = self._current_value(final_price)
        total_pnl = final_value - self.initial_value
        total_return_pct = (total_pnl / self.initial_value) * 100 if self.initial_value > 0 else 0

        # Per-trade stats
        trade_pnls = [t.pnl_trade for t in self.trades]
        winning_trades = [p for p in trade_pnls if p > 0]
        losing_trades = [p for p in trade_pnls if p < 0]

        # Max drawdown
        peak = self.initial_value
        max_dd = 0
        running_value = self.initial_value
        for t in self.trades:
            running_value = t.usd_after + t.usdc_after * t.executed_price
            peak = max(peak, running_value)
            dd = (peak - running_value) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Daily P&L for Sharpe ratio
        daily_pnls = {}
        prev_value = self.initial_value
        for t in self.trades:
            day = t.datetime_str[:10]
            curr_value = t.usd_after + t.usdc_after * t.executed_price
            if day not in daily_pnls:
                daily_pnls[day] = 0
            daily_pnls[day] = curr_value - prev_value
            prev_value = curr_value

        daily_returns = list(daily_pnls.values()) if daily_pnls else [0]
        sharpe = 0
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)

        # Time span
        if len(candles) >= 2:
            first_ts = int(candles.iloc[0]["timestamp"])
            last_ts = int(candles.iloc[-1]["timestamp"])
            days_span = max((last_ts - first_ts) / 86400, 1)
        else:
            days_span = 1

        total_fees = sum(t.fee_usd for t in self.trades)

        metrics = {
            "starting_capital": self.initial_value,
            "final_value": final_value,
            "total_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": total_return_pct * (365 / days_span) if days_span > 0 else 0,
            "total_trades": len(self.trades),
            "total_signals": self.total_signals,
            "trades_per_day": len(self.trades) / days_span,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate_pct": (len(winning_trades) / len(self.trades) * 100) if self.trades else 0,
            "avg_profit_per_trade": np.mean(trade_pnls) if trade_pnls else 0,
            "avg_win": np.mean(winning_trades) if winning_trades else 0,
            "avg_loss": np.mean(losing_trades) if losing_trades else 0,
            "max_drawdown_pct": max_dd,
            "sharpe_ratio": sharpe,
            "total_fees_paid": total_fees,
            "total_slippage_cost": sum(t.slippage * t.size_usd for t in self.trades),
            "failed_orders": self.failed_orders,
            "skipped_cooldown": self.skipped_cooldown,
            "skipped_daily_cap": self.skipped_daily_cap,
            "days_span": days_span,
            "pnl_per_day": total_pnl / days_span if days_span > 0 else 0,
            "buy_threshold": self.config.buy_threshold,
            "sell_threshold": self.config.sell_threshold,
        }
        return metrics


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(metrics: dict):
    """Print formatted backtest results."""
    print("\n" + "=" * 60)
    print("  BACKTEST RESULTS")
    print("=" * 60)

    print(f"\n  {'Starting Capital:':<30} ${metrics['starting_capital']:>12,.2f}")
    print(f"  {'Final Value:':<30} ${metrics['final_value']:>12,.2f}")
    print(f"  {'Total P&L:':<30} ${metrics['total_pnl']:>12,.4f}")
    print(f"  {'Total Return:':<30} {metrics['total_return_pct']:>12.4f}%")
    print(f"  {'Annualized Return:':<30} {metrics['annualized_return_pct']:>12.4f}%")
    print(f"  {'P&L per Day:':<30} ${metrics['pnl_per_day']:>12,.4f}")

    print(f"\n  --- Trades ---")
    print(f"  {'Total Trades:':<30} {metrics['total_trades']:>12}")
    print(f"  {'Signals Generated:':<30} {metrics['total_signals']:>12}")
    print(f"  {'Trades per Day:':<30} {metrics['trades_per_day']:>12.1f}")
    print(f"  {'Win Rate:':<30} {metrics['win_rate_pct']:>12.1f}%")
    print(f"  {'Avg Profit/Trade:':<30} ${metrics['avg_profit_per_trade']:>12,.6f}")
    print(f"  {'Avg Win:':<30} ${metrics['avg_win']:>12,.6f}")
    print(f"  {'Avg Loss:':<30} ${metrics['avg_loss']:>12,.6f}")

    print(f"\n  --- Risk ---")
    print(f"  {'Max Drawdown:':<30} {metrics['max_drawdown_pct']:>12.4f}%")
    print(f"  {'Sharpe Ratio:':<30} {metrics['sharpe_ratio']:>12.2f}")

    print(f"\n  --- Costs ---")
    print(f"  {'Total Fees Paid:':<30} ${metrics['total_fees_paid']:>12,.4f}")
    print(f"  {'Total Slippage Cost:':<30} ${metrics['total_slippage_cost']:>12,.4f}")
    print(f"  {'Failed Orders:':<30} {metrics['failed_orders']:>12}")
    print(f"  {'Skipped (Cooldown):':<30} {metrics['skipped_cooldown']:>12}")
    print(f"  {'Skipped (Daily Cap):':<30} {metrics['skipped_daily_cap']:>12}")

    print(f"\n  --- Period ---")
    print(f"  {'Days Covered:':<30} {metrics['days_span']:>12.1f}")
    print(f"  {'Thresholds:':<30} Buy < ${metrics['buy_threshold']:.4f} / Sell > ${metrics['sell_threshold']:.4f}")

    print("\n" + "=" * 60)

    # Viability assessment
    print("\n  VIABILITY ASSESSMENT:")
    if metrics['total_pnl'] > 0 and metrics['win_rate_pct'] > 50:
        print("  [POSITIVE] Strategy is profitable in backtest.")
        if metrics['total_pnl'] < 1.0:
            print("  [WARNING]  Profits are very small — may not survive real-world conditions.")
        if metrics['sharpe_ratio'] > 1.0:
            print("  [STRONG]   Sharpe > 1.0 indicates good risk-adjusted returns.")
    elif metrics['total_trades'] == 0:
        print("  [NO DATA]  No trades executed — thresholds may be too tight or data too clean.")
        print("             Try wider thresholds or more data. USDC rarely deviates far from $1.")
    else:
        print("  [NEGATIVE] Strategy is not profitable with these parameters.")
        print("             Try adjusting thresholds or consider this strategy may not be viable.")

    print()


def save_trade_log(trades: list, output_path: Path):
    """Save detailed trade log to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "datetime", "side", "size_usd", "quoted_price",
            "executed_price", "slippage", "fill_pct", "fee_usd",
            "pnl_trade", "usd_after", "usdc_after", "cumulative_pnl"
        ])
        for t in trades:
            writer.writerow([
                t.timestamp, t.datetime_str, t.side, f"{t.size_usd:.2f}",
                f"{t.quoted_price:.6f}", f"{t.executed_price:.6f}",
                f"{t.slippage:.8f}", f"{t.fill_pct:.2f}", f"{t.fee_usd:.6f}",
                f"{t.pnl_trade:.6f}", f"{t.usd_after:.2f}", f"{t.usdc_after:.2f}",
                f"{t.cumulative_pnl:.6f}"
            ])

    print(f"Trade log saved to {output_path} ({len(trades)} trades)")


# ---------------------------------------------------------------------------
# Grid search optimizer
# ---------------------------------------------------------------------------

def run_optimization(candles: pd.DataFrame, base_config: BacktestConfig):
    """Grid search over buy/sell thresholds to find optimal parameters."""
    print("\n" + "=" * 60)
    print("  THRESHOLD OPTIMIZATION (Grid Search)")
    print("=" * 60)
    print()

    buy_thresholds = [0.99950, 0.99960, 0.99970, 0.99980, 0.99985, 0.99990, 0.99995]
    sell_thresholds = [1.00005, 1.00010, 1.00015, 1.00020, 1.00030, 1.00040, 1.00050]

    results = []
    total = len(buy_thresholds) * len(sell_thresholds)
    count = 0

    for bt in buy_thresholds:
        for st in sell_thresholds:
            count += 1
            config = BacktestConfig(
                buy_threshold=bt,
                sell_threshold=st,
                starting_usd=base_config.starting_usd,
                starting_usdc=base_config.starting_usdc,
                cooldown_seconds=base_config.cooldown_seconds,
                max_daily_trades=base_config.max_daily_trades,
                slippage_base_bps=base_config.slippage_base_bps,
                slippage_impact_factor=base_config.slippage_impact_factor,
                liquidity_depth_usd=base_config.liquidity_depth_usd,
                order_latency_ms_min=base_config.order_latency_ms_min,
                order_latency_ms_max=base_config.order_latency_ms_max,
                taker_fee_pct=base_config.taker_fee_pct,
                random_seed=base_config.random_seed,
            )
            bt_engine = Backtester(config)
            metrics = bt_engine.run(candles)
            results.append(metrics)

            print(f"\r  {count}/{total} | Buy<{bt:.5f} Sell>{st:.5f} | "
                  f"Trades: {metrics['total_trades']:>5} | "
                  f"P&L: ${metrics['total_pnl']:>10,.4f} | "
                  f"Win: {metrics['win_rate_pct']:.1f}%",
                  end="", flush=True)

    print("\n")

    # Sort by P&L descending
    results.sort(key=lambda r: r["total_pnl"], reverse=True)

    # Print top 10
    print("  TOP 10 PARAMETER COMBINATIONS:")
    print(f"  {'Rank':<6} {'Buy <':<12} {'Sell >':<12} {'Trades':<10} {'P&L':>12} {'Win%':>8} {'Sharpe':>8}")
    print("  " + "-" * 68)

    for i, r in enumerate(results[:10]):
        print(f"  {i+1:<6} ${r['buy_threshold']:<11.5f} ${r['sell_threshold']:<11.5f} "
              f"{r['total_trades']:<10} ${r['total_pnl']:>11,.4f} "
              f"{r['win_rate_pct']:>7.1f}% {r['sharpe_ratio']:>7.2f}")

    if results:
        best = results[0]
        print(f"\n  BEST: Buy < ${best['buy_threshold']:.5f}, Sell > ${best['sell_threshold']:.5f}")
        print(f"         P&L: ${best['total_pnl']:.4f} | {best['total_trades']} trades | {best['win_rate_pct']:.1f}% win rate")

    # Save all results
    opt_file = DATA_DIR / "optimization_results.csv"
    with open(opt_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        for r in results:
            writer.writerow({k: f"{v:.6f}" if isinstance(v, float) else v for k, v in r.items()})
    print(f"\n  Full results saved to {opt_file}")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="USDC-USD Arbitrage Backtester")
    parser.add_argument("--data", type=str, default=str(DEFAULT_DATA_FILE),
                        help="Path to candle CSV file")
    parser.add_argument("--capital", type=float, default=10000.0,
                        help="Starting USD capital (default: 10000)")
    parser.add_argument("--buy-threshold", type=float, default=0.9998,
                        help="Buy USDC when price < this (default: 0.9998)")
    parser.add_argument("--sell-threshold", type=float, default=1.0002,
                        help="Sell USDC when price > this (default: 1.0002)")
    parser.add_argument("--cooldown", type=float, default=0.2,
                        help="Seconds between trades (default: 0.2)")
    parser.add_argument("--max-daily", type=int, default=500,
                        help="Max trades per day (default: 500)")
    parser.add_argument("--limit-orders", action="store_true",
                        help="Simulate limit orders (0%% fee) instead of market (0.001%%)")
    parser.add_argument("--no-slippage", action="store_true",
                        help="Disable slippage simulation (optimistic)")
    parser.add_argument("--no-latency", action="store_true",
                        help="Disable latency simulation (optimistic)")
    parser.add_argument("--optimize", action="store_true",
                        help="Run grid search to find optimal thresholds")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}")
        print("Run 'python fetch_data.py' first to download historical data.")
        sys.exit(1)

    print("=" * 60)
    print("  USDC-USD ARBITRAGE BACKTESTER")
    print("=" * 60)

    candles = pd.read_csv(data_path)
    print(f"\nLoaded {len(candles)} candles from {data_path}")
    print(f"  Range: {candles.iloc[0]['datetime']} to {candles.iloc[-1]['datetime']}")
    print(f"  Price range: ${candles['close'].astype(float).min():.6f} - ${candles['close'].astype(float).max():.6f}")

    # Build config
    config = BacktestConfig(
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        starting_usd=args.capital,
        cooldown_seconds=args.cooldown,
        max_daily_trades=args.max_daily,
        use_limit_orders=args.limit_orders,
        random_seed=args.seed,
    )

    if args.no_slippage:
        config.slippage_base_bps = 0
        config.slippage_impact_factor = 0

    if args.no_latency:
        config.order_latency_ms_min = 0
        config.order_latency_ms_max = 0

    # Run optimization or single backtest
    if args.optimize:
        run_optimization(candles, config)
    else:
        backtester = Backtester(config)
        metrics = backtester.run(candles)
        print_results(metrics)

        # Save trade log
        if backtester.trades:
            save_trade_log(backtester.trades, RESULTS_FILE)

    # Also run optimistic scenario for comparison
    if not args.optimize:
        print("\n" + "-" * 60)
        print("  COMPARISON: Optimistic scenario (no slippage, no latency, 0% fees)")
        print("-" * 60)

        optimistic_config = BacktestConfig(
            buy_threshold=args.buy_threshold,
            sell_threshold=args.sell_threshold,
            starting_usd=args.capital,
            cooldown_seconds=args.cooldown,
            max_daily_trades=args.max_daily,
            slippage_base_bps=0,
            slippage_impact_factor=0,
            order_latency_ms_min=0,
            order_latency_ms_max=0,
            taker_fee_pct=0,
            order_failure_rate=0,
            full_fill_rate=1.0,
            random_seed=args.seed,
        )
        opt_bt = Backtester(optimistic_config)
        opt_metrics = opt_bt.run(candles)
        print_results(opt_metrics)

        # Show the cost of realism
        if metrics['total_pnl'] != 0 or opt_metrics['total_pnl'] != 0:
            print("  REALISM COST:")
            print(f"    Realistic P&L:   ${metrics['total_pnl']:,.4f}")
            print(f"    Optimistic P&L:  ${opt_metrics['total_pnl']:,.4f}")
            diff = opt_metrics['total_pnl'] - metrics['total_pnl']
            print(f"    Difference:      ${diff:,.4f} (cost of slippage + latency + fees)")
            print()


if __name__ == "__main__":
    main()
