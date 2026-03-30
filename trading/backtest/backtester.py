"""
Backtester — runs SMC engine over historical data and computes performance metrics.
Supports single-run backtesting and walk-forward analysis.
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime
from .smc_engine import SMCEngine, DEFAULT_PARAMS
from .rsi2_engine import RSI2Engine, RSI2_DEFAULT_PARAMS


def run_backtest(data: pd.DataFrame, params: dict = None,
                 engine_type: str = "smc") -> dict:
    """
    Run a single backtest over the provided data.

    Args:
        data: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Strategy parameters (uses defaults if None)

    Returns:
        Dict with trades list and performance metrics
    """
    if engine_type == "rsi2":
        engine = RSI2Engine(params or RSI2_DEFAULT_PARAMS)
        params = params or RSI2_DEFAULT_PARAMS
    else:
        engine = SMCEngine(params)
        params = params or DEFAULT_PARAMS

    timestamps = data["timestamp"].values
    opens = data["open"].values
    highs = data["high"].values
    lows = data["low"].values
    closes = data["close"].values
    volumes = data["volume"].values if "volume" in data.columns else np.zeros(len(data))

    for i in range(len(data)):
        ts = pd.Timestamp(timestamps[i])
        engine.process_bar(ts, float(opens[i]), float(highs[i]),
                           float(lows[i]), float(closes[i]),
                           float(volumes[i]))

    trades = engine.trades
    metrics = compute_metrics(trades, data, params)

    return {
        "params": params,
        "trades": [_trade_to_dict(t) for t in trades],
        "metrics": metrics,
    }


def _trade_to_dict(t) -> dict:
    return {
        "entry_bar": t.entry_bar,
        "entry_price": round(t.entry_price, 2),
        "direction": "long" if t.direction == 1 else "short",
        "stop_loss": round(t.stop_loss, 2),
        "take_profit": round(t.take_profit, 2),
        "exit_bar": t.exit_bar,
        "exit_price": round(t.exit_price, 2),
        "pnl": round(t.pnl, 2),
        "r_multiple": round(t.r_multiple, 4),
        "exit_reason": t.exit_reason,
    }


def compute_metrics(trades: list, data: pd.DataFrame, params: dict) -> dict:
    """Compute performance metrics from a list of trades."""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "avg_r_multiple": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "long_trades": 0,
            "short_trades": 0,
            "wins": 0,
            "losses": 0,
        }

    pnls = [t.pnl for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    total = len(trades)
    wins = len(winners)
    losses = len(losers)
    win_rate = wins / total if total > 0 else 0.0

    gross_profit = sum(winners) if winners else 0.0
    gross_loss = abs(sum(losers)) if losers else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    net_pnl = sum(pnls)

    # Max drawdown
    equity_curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = peak - equity_curve
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Max drawdown as percentage of peak equity
    initial_capital = float(params.get("account_balance", 10000))
    equity_with_capital = initial_capital + equity_curve
    peak_with_capital = np.maximum.accumulate(equity_with_capital)
    dd_pct = (peak_with_capital - equity_with_capital) / peak_with_capital * 100
    max_dd_pct = float(np.max(dd_pct)) if len(dd_pct) > 0 else 0.0

    # Sharpe ratio (annualized, assuming ~26 bars/day, 252 days/year)
    if len(pnls) > 1:
        avg_pnl = np.mean(pnls)
        std_pnl = np.std(pnls, ddof=1)
        if std_pnl > 0:
            # Per-trade Sharpe, annualized by sqrt of trades per year estimate
            bars_per_year = 26 * 252
            total_bars = len(data)
            trades_per_year = total / total_bars * bars_per_year if total_bars > 0 else total
            sharpe = (avg_pnl / std_pnl) * np.sqrt(trades_per_year)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # Sortino ratio (annualized, using downside deviation only)
    if len(pnls) > 1:
        downside = [min(0, p) for p in pnls]
        downside_std = np.std(downside, ddof=1)
        if downside_std > 0:
            sortino = (avg_pnl / downside_std) * np.sqrt(trades_per_year)
        else:
            sortino = 0.0 if avg_pnl <= 0 else float("inf")
    else:
        sortino = 0.0

    # Calmar ratio (annualized return / max drawdown)
    if max_dd > 0 and len(pnls) > 0:
        annualized_return = net_pnl * (bars_per_year / max(len(data), 1))
        calmar = annualized_return / max_dd
    else:
        calmar = 0.0 if net_pnl <= 0 else float("inf")

    avg_r = np.mean([t.r_multiple for t in trades])
    long_count = sum(1 for t in trades if t.direction == 1)
    short_count = sum(1 for t in trades if t.direction == -1)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 4),
        "net_pnl": round(net_pnl, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4) if sortino != float("inf") else 999.0,
        "calmar_ratio": round(calmar, 4) if calmar != float("inf") else 999.0,
        "avg_r_multiple": round(float(avg_r), 4),
        "avg_win": round(np.mean(winners), 2) if winners else 0.0,
        "avg_loss": round(np.mean(losers), 2) if losers else 0.0,
        "long_trades": long_count,
        "short_trades": short_count,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }


def walk_forward(data: pd.DataFrame, params: dict = None,
                 n_folds: int = 5, train_ratio: float = 0.7) -> dict:
    """
    Walk-forward analysis: train on one window, test on the next.

    Args:
        data: Full OHLCV dataset
        params: Base parameters
        n_folds: Number of walk-forward windows
        train_ratio: Fraction of each window used for training

    Returns:
        Dict with in-sample and out-of-sample results per fold
    """
    total_bars = len(data)
    fold_size = total_bars // n_folds
    results = []

    for fold in range(n_folds):
        start = fold * fold_size
        end = min(start + fold_size, total_bars)
        split = start + int((end - start) * train_ratio)

        train_data = data.iloc[start:split].reset_index(drop=True)
        test_data = data.iloc[split:end].reset_index(drop=True)

        if len(train_data) < 100 or len(test_data) < 50:
            continue

        train_result = run_backtest(train_data, params)
        test_result = run_backtest(test_data, params)

        results.append({
            "fold": fold + 1,
            "train_bars": len(train_data),
            "test_bars": len(test_data),
            "train_period": f"{train_data['timestamp'].iloc[0].date()} to {train_data['timestamp'].iloc[-1].date()}",
            "test_period": f"{test_data['timestamp'].iloc[0].date()} to {test_data['timestamp'].iloc[-1].date()}",
            "in_sample": train_result["metrics"],
            "out_of_sample": test_result["metrics"],
        })

    # Aggregate OOS metrics
    oos_metrics = {}
    if results:
        oos_trades = sum(r["out_of_sample"]["total_trades"] for r in results)
        oos_pnl = sum(r["out_of_sample"]["net_pnl"] for r in results)
        oos_wins = sum(r["out_of_sample"]["wins"] for r in results)

        oos_metrics = {
            "total_oos_trades": oos_trades,
            "total_oos_pnl": round(oos_pnl, 2),
            "avg_oos_win_rate": round(oos_wins / oos_trades * 100, 2) if oos_trades > 0 else 0.0,
            "avg_oos_sharpe": round(np.mean([r["out_of_sample"]["sharpe_ratio"] for r in results]), 4),
        }

    return {
        "n_folds": len(results),
        "folds": results,
        "aggregate_oos": oos_metrics,
    }


def monte_carlo(trades: list, n_simulations: int = 1000, seed: int = 42) -> dict:
    """
    Monte Carlo simulation — shuffle trade order to test robustness.

    Args:
        trades: List of Trade objects (or dicts with 'pnl' key)
        n_simulations: Number of random shuffles
        seed: Random seed for reproducibility

    Returns:
        Dict with percentile distributions for key metrics
    """
    if not trades:
        return {"n_simulations": 0, "robust": False}

    rng = np.random.RandomState(seed)
    pnls = np.array([t.pnl if hasattr(t, 'pnl') else t['pnl'] for t in trades])
    n_trades = len(pnls)
    initial_capital = 10000.0

    sim_pnl = np.zeros(n_simulations)
    sim_max_dd = np.zeros(n_simulations)
    sim_sharpe = np.zeros(n_simulations)
    sim_pf = np.zeros(n_simulations)

    for i in range(n_simulations):
        shuffled = rng.permutation(pnls)
        equity = np.cumsum(shuffled)

        sim_pnl[i] = equity[-1]

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        dd = peak - equity
        sim_max_dd[i] = np.max(dd) if len(dd) > 0 else 0.0

        # Sharpe
        if n_trades > 1 and np.std(shuffled, ddof=1) > 0:
            sim_sharpe[i] = np.mean(shuffled) / np.std(shuffled, ddof=1) * np.sqrt(252)
        else:
            sim_sharpe[i] = 0.0

        # Profit factor
        wins = shuffled[shuffled > 0].sum()
        losses = abs(shuffled[shuffled <= 0].sum())
        sim_pf[i] = wins / losses if losses > 0 else (999.0 if wins > 0 else 0.0)

    percentiles = [5, 25, 50, 75, 95]

    return {
        "n_simulations": n_simulations,
        "n_trades": n_trades,
        "pnl": {f"p{p}": round(float(np.percentile(sim_pnl, p)), 2) for p in percentiles},
        "max_drawdown": {f"p{p}": round(float(np.percentile(sim_max_dd, p)), 2) for p in percentiles},
        "sharpe": {f"p{p}": round(float(np.percentile(sim_sharpe, p)), 4) for p in percentiles},
        "profit_factor": {f"p{p}": round(float(np.percentile(sim_pf, p)), 4) for p in percentiles},
        "robust": bool(np.percentile(sim_pnl, 5) > 0),
        "pct_profitable": round(float(np.mean(sim_pnl > 0) * 100), 1),
    }
