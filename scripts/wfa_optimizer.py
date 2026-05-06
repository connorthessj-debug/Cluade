"""
wfa_optimizer.py — Walk-Forward Analysis with Optuna Bayesian optimisation.

Usage:
    python3 scripts/wfa_optimizer.py AAPL [--trials 40] [--train 252] [--test 63]
    python3 scripts/wfa_optimizer.py AAPL --interval 1h --strategy breakout
    python3 scripts/wfa_optimizer.py BTCUSDT --interval 1h --strategy mean_reversion

Output: JSON to stdout with per-window results + aggregate WFA metrics including
        permutation significance test and full institutional metric suite.
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

from backtest_engine import (
    BacktestParams, BacktestResult,
    compute_signals_from_params,
    run_backtest, get_signal_fn,
)
from fetch_intraday import fetch_ohlcv, to_dataframe, BARS_PER_YEAR


# ── per-strategy parameter spaces ────────────────────────────────────────────

PARAM_SPACES: dict[str, dict] = {
    "sma_rsi": {
        "fast_ma":       (5,   50),
        "slow_ma":       (20,  200),
        "rsi_period":    (7,   21),
        "rsi_buy":       (20., 45.),
        "rsi_sell":      (55., 80.),
        "stop_loss_pct": (0.02, 0.12),
        "tp_pct":        (0.03, 0.30),
    },
    "breakout": {
        "lookback_n":    (10,  50),
        "atr_period":    (7,   21),
        "atr_mult":      (0.5, 2.5),
        "stop_loss_pct": (0.02, 0.12),
        "tp_pct":        (0.03, 0.30),
    },
    "mean_reversion": {
        "bb_period":      (10,  50),
        "bb_std":         (1.5, 3.0),
        "rsi_period":     (7,   21),
        "rsi_oversold":   (20., 40.),
        "rsi_overbought": (60., 80.),
        "stop_loss_pct":  (0.02, 0.10),
        "tp_pct":         (0.02, 0.20),
    },
}


# ── Optuna objective ─────────────────────────────────────────────────────────

def _suggest_params(trial: optuna.Trial, space: dict) -> dict:
    """Suggest all parameters from a space dict using trial."""
    suggested = {}
    for name, bounds in space.items():
        lo, hi = bounds
        if isinstance(lo, int) and isinstance(hi, int):
            suggested[name] = trial.suggest_int(name, lo, hi)
        else:
            suggested[name] = trial.suggest_float(name, lo, hi)
    return suggested


def _objective(
    trial: optuna.Trial,
    ohlcv: pd.DataFrame,
    allow_short: bool,
    strategy: str,
    annualization: int,
) -> float:
    space = PARAM_SPACES[strategy]
    p = _suggest_params(trial, space)

    # strategy-specific constraints
    if strategy == "sma_rsi":
        if p["fast_ma"] >= p["slow_ma"] or p["rsi_buy"] >= p["rsi_sell"]:
            return -10.0
    elif strategy == "mean_reversion":
        if p["rsi_oversold"] >= p["rsi_overbought"]:
            return -10.0

    signal_fn = get_signal_fn(strategy)
    # pull only the keys the signal fn accepts (exclude stop/tp)
    sig_kwargs = {k: v for k, v in p.items() if k not in ("stop_loss_pct", "tp_pct")}
    signals = signal_fn(ohlcv, **sig_kwargs)

    params = BacktestParams(
        stop_loss_pct=p["stop_loss_pct"],
        take_profit_pct=p["tp_pct"],
        allow_short=allow_short,
        annualization=annualization,
    )
    result = run_backtest(ohlcv, signals, params)

    if result.n_trades < 3:
        return -5.0
    return result.sharpe_ratio


# ── permutation significance test ────────────────────────────────────────────

def _permutation_test(
    ohlcv_test: pd.DataFrame,
    best_params: dict,
    strategy: str,
    bt_params: BacktestParams,
    n_perms: int = 200,
) -> float:
    """
    Shuffle the OOS signal Series n_perms times and compare each null Sharpe
    against the real OOS Sharpe. Returns p-value = P(null >= real).
    Low p-value (< 0.10) means the strategy's edge is unlikely due to chance.
    """
    signal_fn = get_signal_fn(strategy)
    sig_kwargs = {k: v for k, v in best_params.items() if k not in ("stop_loss_pct", "tp_pct")}

    real_signals = signal_fn(ohlcv_test, **sig_kwargs)
    real_result  = run_backtest(ohlcv_test, real_signals, bt_params)
    real_sharpe  = real_result.sharpe_ratio

    rng = np.random.default_rng(99)
    null_sharpes: list[float] = []
    for _ in range(n_perms):
        shuffled = real_signals.values.copy()
        rng.shuffle(shuffled)
        null_sig = pd.Series(shuffled, index=ohlcv_test.index)
        null_res = run_backtest(ohlcv_test, null_sig, bt_params)
        null_sharpes.append(null_res.sharpe_ratio)

    p_value = float(np.mean([s >= real_sharpe for s in null_sharpes]))
    return round(p_value, 4)


# ── single walk-forward window ───────────────────────────────────────────────

def _run_window(
    ohlcv: pd.DataFrame,
    train_idx: slice,
    test_idx: slice,
    n_trials: int,
    allow_short: bool,
    window_num: int,
    strategy: str,
    annualization: int,
) -> dict:
    train_df = ohlcv.iloc[train_idx]
    test_df  = ohlcv.iloc[test_idx]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42 + window_num),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0),
    )
    study.optimize(
        lambda trial: _objective(trial, train_df, allow_short, strategy, annualization),
        n_trials=n_trials,
        show_progress_bar=False,
    )

    best = study.best_params
    best_is_sharpe = study.best_value

    # ── OOS evaluation ────────────────────────────────────────────────────
    signal_fn  = get_signal_fn(strategy)
    sig_kwargs = {k: v for k, v in best.items() if k not in ("stop_loss_pct", "tp_pct")}
    test_signals = signal_fn(test_df, **sig_kwargs)

    test_params = BacktestParams(
        stop_loss_pct=best["stop_loss_pct"],
        take_profit_pct=best["tp_pct"],
        allow_short=allow_short,
        annualization=annualization,
    )
    oos = run_backtest(test_df, test_signals, test_params)

    # ── permutation test ──────────────────────────────────────────────────
    perm_pval = _permutation_test(test_df, best, strategy, test_params, n_perms=200)

    return {
        "window":           window_num,
        "train_start":      str(train_df.index[0].date()),
        "train_end":        str(train_df.index[-1].date()),
        "test_start":       str(test_df.index[0].date()),
        "test_end":         str(test_df.index[-1].date()),
        "strategy":         strategy,
        "is_sharpe":        round(best_is_sharpe, 3),
        "oos_sharpe":       round(oos.sharpe_ratio, 3),
        "oos_return_pct":   round(oos.total_return_pct, 2),
        "oos_max_dd_pct":   round(oos.max_drawdown_pct, 2),
        "oos_n_trades":     oos.n_trades,
        "oos_win_rate_pct": round(oos.win_rate_pct, 1),
        "oos_ulcer_index":  round(oos.ulcer_index, 3),
        "oos_expectancy_pct": round(oos.expectancy_pct, 4),
        "mc_sharpe_p5":     oos.mc_sharpe_p5,
        "mc_sharpe_p95":    oos.mc_sharpe_p95,
        "perm_p_value":     perm_pval,
        "best_params":      {k: round(v, 4) if isinstance(v, float) else v for k, v in best.items()},
    }


# ── full WFA pipeline ────────────────────────────────────────────────────────

def run_wfa(
    symbol: str,
    n_trials: int = 40,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 21,
    allow_short: bool = True,
    period: str = "5y",
    interval: str = "1d",
    strategy: str = "sma_rsi",
) -> dict:
    """Full walk-forward analysis pipeline.

    interval: "1d"|"1h"|"15m"|"5m"|"1m"
        1d  → yfinance 5y daily (backward-compatible default)
        1h  → yfinance 730d hourly (equities) or Binance 365d (crypto)
        <1h → Binance only (crypto); yfinance data too short for WFA
    strategy: "sma_rsi"|"breakout"|"mean_reversion"
    """
    # ── fetch data ────────────────────────────────────────────────────────
    if interval == "1d":
        ohlcv = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if ohlcv.empty:
            return {"error": f"No price data for {symbol}"}
        if isinstance(ohlcv.columns, pd.MultiIndex):
            ohlcv.columns = ohlcv.columns.get_level_values(0)
        ohlcv = ohlcv.dropna()
    else:
        fetched = fetch_ohlcv(symbol, interval=interval)
        if fetched.get("error"):
            return {"error": fetched["error"]}
        if fetched.get("bar_count", 0) == 0:
            return {"error": f"No intraday data returned for {symbol} at {interval}"}
        ohlcv = to_dataframe(fetched)
        if ohlcv.empty:
            return {"error": f"Empty DataFrame after conversion for {symbol} {interval}"}

    annualization = BARS_PER_YEAR.get(interval, 252)

    min_needed = train_days + test_days
    if len(ohlcv) < min_needed:
        return {
            "error": (
                f"Not enough history for {symbol} at {interval}: "
                f"need {min_needed} bars, got {len(ohlcv)}. "
                f"Try a coarser interval or reduce train/test days."
            )
        }

    # ── build windows ─────────────────────────────────────────────────────
    windows = []
    start = 0
    while start + train_days + test_days <= len(ohlcv):
        windows.append((
            slice(start, start + train_days),
            slice(start + train_days, start + train_days + test_days),
        ))
        start += step_days

    if not windows:
        return {"error": "Could not construct any WFA windows with given parameters"}

    # ── run each window ───────────────────────────────────────────────────
    window_results: list[dict] = []
    for i, (tr, te) in enumerate(windows):
        res = _run_window(ohlcv, tr, te, n_trials, allow_short, i + 1, strategy, annualization)
        window_results.append(res)
        print(
            f"WFA window {i+1}/{len(windows)}: "
            f"OOS Sharpe={res['oos_sharpe']}  p={res['perm_p_value']}",
            file=sys.stderr,
        )

    # ── buy-and-hold benchmark ────────────────────────────────────────────
    bh_ret    = (ohlcv["Close"].iloc[-1] / ohlcv["Close"].iloc[0] - 1) * 100
    bh_daily  = ohlcv["Close"].pct_change().dropna()
    bh_sharpe = float(bh_daily.mean() / (bh_daily.std() + 1e-10) * np.sqrt(annualization))

    # ── aggregate ─────────────────────────────────────────────────────────
    oos_sharpes = [w["oos_sharpe"]        for w in window_results]
    oos_dds     = [w["oos_max_dd_pct"]    for w in window_results]
    oos_rets    = [w["oos_return_pct"]    for w in window_results]
    oos_ulcers  = [w["oos_ulcer_index"]   for w in window_results]
    oos_expects = [w["oos_expectancy_pct"] for w in window_results]
    mc_p5s      = [w["mc_sharpe_p5"]      for w in window_results]
    mc_p95s     = [w["mc_sharpe_p95"]     for w in window_results]
    perm_pvals  = [w["perm_p_value"]      for w in window_results]

    positive_windows = sum(1 for s in oos_sharpes if s > 0)
    sig_windows      = sum(1 for p in perm_pvals  if p <= 0.10)

    # stable params: median of best half of windows
    space = PARAM_SPACES.get(strategy, PARAM_SPACES["sma_rsi"])
    top_half = sorted(window_results, key=lambda w: w["oos_sharpe"], reverse=True)
    top_half = top_half[:max(1, len(top_half) // 2)]
    stable_params: dict = {}
    for key in space:
        vals = [w["best_params"].get(key) for w in top_half if w["best_params"].get(key) is not None]
        if vals:
            stable_params[key] = round(float(np.median(vals)), 4)

    aggregate = {
        "n_windows":            len(window_results),
        "wfa_sharpe_mean":      round(float(np.mean(oos_sharpes)), 3),
        "wfa_sharpe_std":       round(float(np.std(oos_sharpes)), 3),
        "wfa_return_mean_pct":  round(float(np.mean(oos_rets)), 2),
        "wfa_max_drawdown_pct": round(float(min(oos_dds)), 2),
        "wfa_consistency_pct":  round(positive_windows / len(window_results) * 100, 1),
        "bh_return_pct":        round(float(bh_ret), 2),
        "bh_sharpe":            round(float(bh_sharpe), 3),
        "wfa_vs_bh_sharpe":     round(float(np.mean(oos_sharpes)) - bh_sharpe, 3),
        # institutional extras
        "wfa_ulcer_mean":       round(float(np.mean(oos_ulcers)), 3),
        "wfa_expectancy_mean":  round(float(np.mean(oos_expects)), 4),
        "mc_sharpe_p5_mean":    round(float(np.mean(mc_p5s)), 3),
        "mc_sharpe_p95_mean":   round(float(np.mean(mc_p95s)), 3),
        # significance
        "perm_p_value_mean":    round(float(np.mean(perm_pvals)), 4),
        "perm_significant_pct": round(sig_windows / len(window_results) * 100, 1),
    }

    verdict = _wfa_verdict(aggregate)

    return {
        "symbol":              symbol,
        "interval":            interval,
        "strategy":            strategy,
        "n_trials_per_window": n_trials,
        "train_days":          train_days,
        "test_days":           test_days,
        "step_days":           step_days,
        "data_bars":           len(ohlcv),
        "data_start":          str(ohlcv.index[0].date()),
        "data_end":            str(ohlcv.index[-1].date()),
        "aggregate":           aggregate,
        "stable_params":       stable_params,
        "verdict":             verdict,
        "windows":             window_results,
    }


def _wfa_verdict(agg: dict) -> str:
    sharpe      = agg["wfa_sharpe_mean"]
    consistency = agg["wfa_consistency_pct"]
    vs_bh       = agg["wfa_vs_bh_sharpe"]
    p_val       = agg.get("perm_p_value_mean", 0.0)

    sig_warning = (
        f" [WARNING: p={p_val:.3f}, not statistically significant]"
        if p_val > 0.10 else ""
    )

    if sharpe > 0.8 and consistency >= 70 and vs_bh > 0:
        return "STRONG EDGE — strategy shows consistent OOS alpha above buy-and-hold" + sig_warning
    elif sharpe > 0.4 and consistency >= 55:
        return "MODERATE EDGE — positive OOS Sharpe but moderate consistency; trade with caution" + sig_warning
    elif sharpe > 0 and consistency >= 45:
        return "WEAK EDGE — marginal OOS performance; likely needs further refinement" + sig_warning
    elif sharpe <= 0:
        return "NO EDGE — strategy underperforms in OOS; do not trade live" + sig_warning
    else:
        return "INCONSISTENT — high variance across windows; unstable strategy" + sig_warning


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-Forward Analysis with Optuna")
    parser.add_argument("symbol",              help="Ticker symbol (e.g. AAPL, BTCUSDT)")
    parser.add_argument("--trials",  type=int,   default=40,           help="Optuna trials per window")
    parser.add_argument("--train",   type=int,   default=252,          help="Train window in bars")
    parser.add_argument("--test",    type=int,   default=63,           help="Test window in bars")
    parser.add_argument("--steps",   type=int,   default=21,           help="Step size in bars")
    parser.add_argument("--no-short", action="store_true",             help="Long-only mode")
    parser.add_argument("--period",  default="5y",                     help="yfinance period (1d only)")
    parser.add_argument("--interval", default="1d",
                        help="Bar interval: 1d|1h|15m|5m|1m (default: 1d)")
    parser.add_argument("--strategy", default="sma_rsi",
                        help="Strategy: sma_rsi|breakout|mean_reversion (default: sma_rsi)")
    args = parser.parse_args()

    result = run_wfa(
        symbol=args.symbol,
        n_trials=args.trials,
        train_days=args.train,
        test_days=args.test,
        step_days=args.steps,
        allow_short=not args.no_short,
        period=args.period,
        interval=args.interval,
        strategy=args.strategy,
    )
    print(json.dumps(result, indent=2, default=str))
