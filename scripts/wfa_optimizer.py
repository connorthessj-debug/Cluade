"""
wfa_optimizer.py — Walk-Forward Analysis with Optuna Bayesian optimisation.

Usage:
    python3 scripts/wfa_optimizer.py AAPL [--trials 40] [--train 252] [--test 63] [--steps 21]

Output: JSON to stdout with per-window results + aggregate WFA metrics.

WFA structure:
    |← train →|← test →|
                |← train →|← test →|
                           |← train →|← test →|

For each window:
  1. Fit Optuna study on train slice (maximise Sharpe).
  2. Apply best params to test slice → OOS metric.
Aggregate: mean OOS Sharpe, worst OOS drawdown, consistency %.
"""

import argparse
import json
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd
import optuna
import yfinance as yf

optuna.logging.set_verbosity(optuna.logging.WARNING)

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtest_engine import BacktestParams, BacktestResult, compute_signals_from_params, run_backtest


# ── parameter search space ────────────────────────────────────────────────────

PARAM_SPACE = {
    "fast_ma":       (5,   50),
    "slow_ma":       (20,  200),
    "rsi_period":    (7,   21),
    "rsi_buy":       (20., 45.),
    "rsi_sell":      (55., 80.),
    "stop_loss_pct": (0.02, 0.12),
    "tp_pct":        (0.03, 0.30),
}


def _objective(trial: optuna.Trial, ohlcv: pd.DataFrame, allow_short: bool) -> float:
    fast_ma   = trial.suggest_int("fast_ma",   *PARAM_SPACE["fast_ma"])
    slow_ma   = trial.suggest_int("slow_ma",   *PARAM_SPACE["slow_ma"])
    rsi_period = trial.suggest_int("rsi_period", *PARAM_SPACE["rsi_period"])
    rsi_buy   = trial.suggest_float("rsi_buy",  *PARAM_SPACE["rsi_buy"])
    rsi_sell  = trial.suggest_float("rsi_sell", *PARAM_SPACE["rsi_sell"])
    stop_pct  = trial.suggest_float("stop_loss_pct", *PARAM_SPACE["stop_loss_pct"])
    tp_pct    = trial.suggest_float("tp_pct",   *PARAM_SPACE["tp_pct"])

    if fast_ma >= slow_ma or rsi_buy >= rsi_sell:
        return -10.0

    signals = compute_signals_from_params(
        ohlcv,
        fast_ma=fast_ma,
        slow_ma=slow_ma,
        rsi_period=rsi_period,
        rsi_buy=rsi_buy,
        rsi_sell=rsi_sell,
    )

    params = BacktestParams(
        stop_loss_pct=stop_pct,
        take_profit_pct=tp_pct,
        allow_short=allow_short,
    )
    result = run_backtest(ohlcv, signals, params)

    # Penalise degenerate runs
    if result.n_trades < 3:
        return -5.0
    return result.sharpe_ratio


def _run_window(
    ohlcv: pd.DataFrame,
    train_idx: slice,
    test_idx: slice,
    n_trials: int,
    allow_short: bool,
    window_num: int,
) -> dict:
    """Optimise on train slice, evaluate on test slice."""
    train_df = ohlcv.iloc[train_idx]
    test_df  = ohlcv.iloc[test_idx]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42 + window_num),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0),
    )
    study.optimize(
        lambda trial: _objective(trial, train_df, allow_short),
        n_trials=n_trials,
        show_progress_bar=False,
    )

    best = study.best_params
    best_is_sharpe = study.best_value

    # Apply best params to OOS test slice
    test_signals = compute_signals_from_params(
        test_df,
        fast_ma=best["fast_ma"],
        slow_ma=best["slow_ma"],
        rsi_period=best["rsi_period"],
        rsi_buy=best["rsi_buy"],
        rsi_sell=best["rsi_sell"],
    )
    test_params = BacktestParams(
        stop_loss_pct=best["stop_loss_pct"],
        take_profit_pct=best["tp_pct"],
        allow_short=allow_short,
    )
    oos_result = run_backtest(test_df, test_signals, test_params)

    return {
        "window": window_num,
        "train_start": str(train_df.index[0].date()),
        "train_end":   str(train_df.index[-1].date()),
        "test_start":  str(test_df.index[0].date()),
        "test_end":    str(test_df.index[-1].date()),
        "is_sharpe":   round(best_is_sharpe, 3),
        "oos_sharpe":  round(oos_result.sharpe_ratio, 3),
        "oos_return_pct":   round(oos_result.total_return_pct, 2),
        "oos_max_dd_pct":   round(oos_result.max_drawdown_pct, 2),
        "oos_n_trades":     oos_result.n_trades,
        "oos_win_rate_pct": round(oos_result.win_rate_pct, 1),
        "best_params": {k: round(v, 4) if isinstance(v, float) else v for k, v in best.items()},
    }


def run_wfa(
    symbol: str,
    n_trials: int = 40,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 21,
    allow_short: bool = True,
    period: str = "5y",
) -> dict:
    """Full walk-forward analysis pipeline."""

    # ── fetch data ────────────────────────────────────────────────────────
    ohlcv = yf.download(symbol, period=period, progress=False, auto_adjust=True)
    if ohlcv.empty:
        return {"error": f"No price data for {symbol}"}
    if isinstance(ohlcv.columns, pd.MultiIndex):
        ohlcv.columns = ohlcv.columns.get_level_values(0)
    ohlcv = ohlcv.dropna()

    min_needed = train_days + test_days
    if len(ohlcv) < min_needed:
        return {"error": f"Not enough history: need {min_needed} bars, got {len(ohlcv)}"}

    # ── build windows ─────────────────────────────────────────────────────
    windows = []
    start = 0
    while start + train_days + test_days <= len(ohlcv):
        train_slice = slice(start, start + train_days)
        test_slice  = slice(start + train_days, start + train_days + test_days)
        windows.append((train_slice, test_slice))
        start += step_days

    if not windows:
        return {"error": "Could not construct any WFA windows with given parameters"}

    # ── run each window ───────────────────────────────────────────────────
    window_results = []
    for i, (tr, te) in enumerate(windows):
        res = _run_window(ohlcv, tr, te, n_trials, allow_short, i + 1)
        window_results.append(res)
        # stream progress to stderr so server can monitor
        print(f"WFA window {i+1}/{len(windows)}: OOS Sharpe={res['oos_sharpe']}", file=sys.stderr)

    # ── run buy-and-hold benchmark ────────────────────────────────────────
    bh_ret = (ohlcv["Close"].iloc[-1] / ohlcv["Close"].iloc[0] - 1) * 100
    bh_daily = ohlcv["Close"].pct_change().dropna()
    bh_sharpe = float(bh_daily.mean() / (bh_daily.std() + 1e-10) * np.sqrt(252))

    # ── aggregate metrics ─────────────────────────────────────────────────
    oos_sharpes  = [w["oos_sharpe"]  for w in window_results]
    oos_dds      = [w["oos_max_dd_pct"] for w in window_results]
    oos_rets     = [w["oos_return_pct"] for w in window_results]
    positive_windows = sum(1 for s in oos_sharpes if s > 0)

    # Stability: find params that appear most often in best quartile windows
    top_windows = sorted(window_results, key=lambda w: w["oos_sharpe"], reverse=True)
    top_half = top_windows[:max(1, len(top_windows)//2)]
    stable_params = {}
    for key in PARAM_SPACE:
        vals = [w["best_params"].get(key) for w in top_half if w["best_params"].get(key) is not None]
        if vals:
            stable_params[key] = round(float(np.median(vals)), 4)

    aggregate = {
        "n_windows": len(window_results),
        "wfa_sharpe_mean":   round(float(np.mean(oos_sharpes)), 3),
        "wfa_sharpe_std":    round(float(np.std(oos_sharpes)), 3),
        "wfa_return_mean_pct": round(float(np.mean(oos_rets)), 2),
        "wfa_max_drawdown_pct": round(float(min(oos_dds)), 2),
        "wfa_consistency_pct": round(positive_windows / len(window_results) * 100, 1),
        "bh_return_pct":     round(bh_ret, 2),
        "bh_sharpe":         round(bh_sharpe, 3),
        "wfa_vs_bh_sharpe":  round(float(np.mean(oos_sharpes)) - bh_sharpe, 3),
    }

    verdict = _wfa_verdict(aggregate)

    return {
        "symbol": symbol,
        "n_trials_per_window": n_trials,
        "train_days": train_days,
        "test_days": test_days,
        "step_days": step_days,
        "data_bars": len(ohlcv),
        "data_start": str(ohlcv.index[0].date()),
        "data_end":   str(ohlcv.index[-1].date()),
        "aggregate": aggregate,
        "stable_params": stable_params,
        "verdict": verdict,
        "windows": window_results,
    }


def _wfa_verdict(agg: dict) -> str:
    sharpe = agg["wfa_sharpe_mean"]
    consistency = agg["wfa_consistency_pct"]
    vs_bh = agg["wfa_vs_bh_sharpe"]

    if sharpe > 0.8 and consistency >= 70 and vs_bh > 0:
        return "STRONG EDGE — strategy shows consistent OOS alpha above buy-and-hold"
    elif sharpe > 0.4 and consistency >= 55:
        return "MODERATE EDGE — positive OOS Sharpe but moderate consistency; trade with caution"
    elif sharpe > 0 and consistency >= 45:
        return "WEAK EDGE — marginal OOS performance; likely needs further refinement"
    elif sharpe <= 0:
        return "NO EDGE — strategy underperforms in OOS; do not trade live"
    else:
        return "INCONSISTENT — high variance across windows; unstable strategy"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-Forward Analysis with Optuna")
    parser.add_argument("symbol",        help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--trials",  type=int,   default=40,  help="Optuna trials per window")
    parser.add_argument("--train",   type=int,   default=252, help="Train window in bars")
    parser.add_argument("--test",    type=int,   default=63,  help="Test window in bars")
    parser.add_argument("--steps",   type=int,   default=21,  help="Step size in bars")
    parser.add_argument("--no-short", action="store_true",    help="Long-only mode")
    parser.add_argument("--period",  default="5y",            help="yfinance period (3y, 5y, 10y)")
    args = parser.parse_args()

    result = run_wfa(
        symbol=args.symbol,
        n_trials=args.trials,
        train_days=args.train,
        test_days=args.test,
        step_days=args.steps,
        allow_short=not args.no_short,
        period=args.period,
    )
    print(json.dumps(result, indent=2, default=str))
