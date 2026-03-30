#!/usr/bin/env python3
"""
Auto-improvement system for SMC MNQ strategy.
Supports grid search, Bayesian (Optuna), and refinement optimization with guard rails.
"""

import json
import os
import itertools
from datetime import datetime

import numpy as np
import pandas as pd

from trading.backtest.backtester import run_backtest, monte_carlo
from trading.backtest.smc_engine import DEFAULT_PARAMS
from trading.backtest.report import print_optimization_report, print_monte_carlo_report


# Parameter search space — key parameters that affect performance most
SEARCH_SPACE = {
    "swingLen":    [3, 5, 7, 10],
    "obMaxAge":    [50, 100, 150],
    "atrSlMult":   [1.0, 1.5, 2.0, 2.5],
    "rrRatio":     [1.5, 2.0, 2.5, 3.0],
    "fvgMinSize":  [0.25, 0.5, 1.0],
    "pdLookback":  [30, 50, 75],
}

# Quick search space for faster runs
QUICK_SEARCH_SPACE = {
    "swingLen":    [3, 5, 7],
    "atrSlMult":   [1.0, 1.5, 2.5],
    "rrRatio":     [1.5, 2.0, 3.0],
    "pdLookback":  [30, 50],
}

# Guard rails
MIN_TRADES = 10
MAX_DRAWDOWN_PCT = 20.0
MIN_WIN_RATE = 30.0

# Objective functions
OBJECTIVES = {
    "sharpe": lambda m: m["sharpe_ratio"] + 0.1 * min(m["profit_factor"], 5.0) + 0.01 * m["win_rate"],
    "sortino": lambda m: m.get("sortino_ratio", 0) + 0.1 * min(m["profit_factor"], 5.0) + 0.01 * m["win_rate"],
    "calmar": lambda m: m.get("calmar_ratio", 0) + 0.1 * min(m["profit_factor"], 5.0) + 0.01 * m["win_rate"],
    "composite": lambda m: (
        0.4 * m["sharpe_ratio"]
        + 0.3 * m.get("sortino_ratio", 0)
        + 0.3 * min(m.get("calmar_ratio", 0), 10.0)
        + 0.1 * min(m["profit_factor"], 5.0)
        + 0.01 * m["win_rate"]
    ),
}

_active_objective = "composite"


def set_objective(name: str):
    """Set the active objective function."""
    global _active_objective
    if name not in OBJECTIVES:
        raise ValueError(f"Unknown objective: {name}. Available: {list(OBJECTIVES.keys())}")
    _active_objective = name


def _objective(metrics: dict) -> float:
    """
    Score a parameter set. Higher is better.
    Returns -inf for parameter sets that violate guard rails.
    """
    if metrics["total_trades"] < MIN_TRADES:
        return float("-inf")
    if metrics["max_drawdown_pct"] > MAX_DRAWDOWN_PCT:
        return float("-inf")
    if metrics["win_rate"] < MIN_WIN_RATE:
        return float("-inf")

    return OBJECTIVES[_active_objective](metrics)


def optimize(data: pd.DataFrame, output_dir: str = None,
             search_space: dict = None, quick: bool = False) -> dict:
    """
    Run grid search optimization over parameter space.

    Args:
        data: OHLCV DataFrame
        output_dir: Directory to save results (default: trading/)
        search_space: Custom search space (uses default if None)

    Returns:
        Dict with baseline, best result, and all tested combos
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    space = search_space or (QUICK_SEARCH_SPACE if quick else SEARCH_SPACE)

    # Baseline run with default params
    print("Running baseline backtest with default parameters...")
    baseline = run_backtest(data, DEFAULT_PARAMS)
    baseline_score = _objective(baseline["metrics"])
    print(f"  Baseline: {baseline['metrics']['total_trades']} trades, "
          f"Sharpe={baseline['metrics']['sharpe_ratio']:.4f}, "
          f"PnL=${baseline['metrics']['net_pnl']:.2f}")

    # Generate all parameter combinations
    keys = list(space.keys())
    values = list(space.values())
    combos = list(itertools.product(*values))
    total_combos = len(combos)

    print(f"\nOptimizing over {total_combos} parameter combinations...")

    best_score = baseline_score
    best_params = DEFAULT_PARAMS.copy()
    best_result = baseline
    all_results = []

    for i, combo in enumerate(combos):
        params = DEFAULT_PARAMS.copy()
        for k, v in zip(keys, combo):
            params[k] = v

        result = run_backtest(data, params)
        score = _objective(result["metrics"])

        all_results.append({
            "params": {k: v for k, v in zip(keys, combo)},
            "score": score,
            "metrics": result["metrics"],
        })

        if score > best_score:
            best_score = score
            best_params = params.copy()
            best_result = result

        # Progress update every 10%
        if (i + 1) % max(1, total_combos // 10) == 0:
            pct = (i + 1) / total_combos * 100
            print(f"  [{pct:5.1f}%] Tested {i + 1}/{total_combos} | "
                  f"Best Sharpe: {best_result['metrics']['sharpe_ratio']:.4f}")

    # Extract only the changed params for display
    changed_params = {k: best_params[k] for k in keys if best_params[k] != DEFAULT_PARAMS.get(k)}
    if not changed_params:
        changed_params = {k: best_params[k] for k in keys}

    # Print comparison report
    print_optimization_report(baseline, best_result, changed_params)

    # Save optimized parameters
    opt_params_path = os.path.join(output_dir, "optimized_params.json")
    opt_params_out = {k: best_params[k] for k in keys}
    opt_params_out["_metadata"] = {
        "optimized_at": datetime.now().isoformat(),
        "baseline_sharpe": baseline["metrics"]["sharpe_ratio"],
        "optimized_sharpe": best_result["metrics"]["sharpe_ratio"],
        "combos_tested": total_combos,
        "objective": "maximize sharpe_ratio",
        "guard_rails": {
            "min_trades": MIN_TRADES,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
            "min_win_rate": MIN_WIN_RATE,
        },
    }

    with open(opt_params_path, "w") as f:
        json.dump(opt_params_out, f, indent=2)
    print(f"\nOptimized parameters saved to: {opt_params_path}")

    # Update trade_log.json with optimization entry
    trade_log_path = os.path.join(output_dir, "trade_log.json")
    _update_trade_log(trade_log_path, baseline["metrics"], best_result["metrics"],
                      changed_params)

    # Update CHANGELOG.md
    changelog_path = os.path.join(output_dir, "CHANGELOG.md")
    _update_changelog(changelog_path, baseline["metrics"], best_result["metrics"],
                      changed_params)

    # Sort all results by score for analysis
    all_results.sort(key=lambda x: x["score"], reverse=True)

    # Print top 5
    print(f"\nTop 5 parameter sets:")
    print(f"  {'Rank':>4s}  {'Sharpe':>8s}  {'Win%':>6s}  {'PF':>6s}  {'Trades':>7s}  {'PnL':>10s}")
    for i, r in enumerate(all_results[:5]):
        m = r["metrics"]
        print(f"  {i + 1:>4d}  {m['sharpe_ratio']:>8.4f}  {m['win_rate']:>5.1f}%  "
              f"{m['profit_factor']:>6.2f}  {m['total_trades']:>7d}  ${m['net_pnl']:>9,.2f}")

    return {
        "baseline": baseline,
        "best": best_result,
        "best_params": changed_params,
        "all_results": all_results[:20],  # Top 20
    }


def optimize_bayesian(data: pd.DataFrame, output_dir: str = None,
                      n_trials: int = 300, base_params: dict = None,
                      extra_space: dict = None) -> dict:
    """
    Bayesian optimization using Optuna's TPE sampler.
    Finds good params in ~200-500 trials instead of 15k grid combos.

    Args:
        data: OHLCV DataFrame
        output_dir: Directory to save results
        n_trials: Number of Optuna trials (default 300)
        base_params: Starting parameters
        extra_space: Additional params to search (for expansion iterations)

    Returns:
        Dict with baseline, best result, and top results
    """
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    bp = base_params or DEFAULT_PARAMS.copy()

    # Baseline
    print("Running baseline backtest...")
    baseline = run_backtest(data, bp)
    print(f"  Baseline: {baseline['metrics']['total_trades']} trades, "
          f"Sharpe={baseline['metrics']['sharpe_ratio']:.4f}, "
          f"PnL=${baseline['metrics']['net_pnl']:.2f}")

    all_results = []

    def trial_objective(trial):
        params = bp.copy()
        params["swingLen"] = trial.suggest_int("swingLen", 2, 12)
        params["obMaxAge"] = trial.suggest_int("obMaxAge", 25, 200, step=25)
        params["atrSlMult"] = trial.suggest_float("atrSlMult", 0.5, 3.5, step=0.1)
        params["rrRatio"] = trial.suggest_float("rrRatio", 0.8, 4.0, step=0.25)
        params["fvgMinSize"] = trial.suggest_float("fvgMinSize", 0.05, 2.0, step=0.05)
        params["pdLookback"] = trial.suggest_int("pdLookback", 15, 100, step=5)

        if extra_space:
            for k, v in extra_space.items():
                if isinstance(v[0], bool):
                    params[k] = trial.suggest_categorical(k, v)
                elif isinstance(v[0], int):
                    params[k] = trial.suggest_int(k, min(v), max(v))
                else:
                    params[k] = trial.suggest_float(k, min(v), max(v))

        result = run_backtest(data, params)
        score = _objective(result["metrics"])

        changed = {k: params[k] for k in SEARCH_SPACE.keys()}
        all_results.append({
            "params": changed,
            "score": score,
            "metrics": result["metrics"],
        })

        return score

    print(f"\nBayesian optimization: {n_trials} trials...")
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(trial_objective, n_trials=n_trials,
                   callbacks=[lambda study, trial: print(
                       f"  [{trial.number + 1}/{n_trials}] "
                       f"Best: {study.best_value:.4f}") if (trial.number + 1) % 50 == 0 else None])

    # Get best result
    best_trial = study.best_trial
    best_params = bp.copy()
    for k, v in best_trial.params.items():
        best_params[k] = v
    best_result = run_backtest(data, best_params)

    changed = {k: best_params[k] for k in SEARCH_SPACE.keys()}
    print_optimization_report(baseline, best_result, changed)

    # Save
    opt_params_path = os.path.join(output_dir, "optimized_params.json")
    opt_out = {k: best_params[k] for k in SEARCH_SPACE.keys()}
    opt_out["_metadata"] = {
        "optimized_at": datetime.now().isoformat(),
        "method": "bayesian_tpe",
        "n_trials": n_trials,
        "objective": _active_objective,
        "baseline_sharpe": baseline["metrics"]["sharpe_ratio"],
        "optimized_sharpe": best_result["metrics"]["sharpe_ratio"],
    }
    with open(opt_params_path, "w") as f:
        json.dump(opt_out, f, indent=2)

    _update_trade_log(os.path.join(output_dir, "trade_log.json"),
                      baseline["metrics"], best_result["metrics"], changed)
    _update_changelog(os.path.join(output_dir, "CHANGELOG.md"),
                      baseline["metrics"], best_result["metrics"], changed)

    all_results.sort(key=lambda x: x["score"], reverse=True)

    print(f"\nTop 5 parameter sets:")
    print(f"  {'Rank':>4s}  {'Score':>8s}  {'Sharpe':>8s}  {'Win%':>6s}  {'PF':>6s}  {'PnL':>10s}")
    for i, r in enumerate(all_results[:5]):
        m = r["metrics"]
        print(f"  {i + 1:>4d}  {r['score']:>8.4f}  {m['sharpe_ratio']:>8.4f}  {m['win_rate']:>5.1f}%  "
              f"{m['profit_factor']:>6.2f}  ${m['net_pnl']:>9,.2f}")

    return {
        "baseline": baseline,
        "best": best_result,
        "best_params": changed,
        "all_results": all_results[:20],
    }


def _update_trade_log(path: str, baseline_metrics: dict, opt_metrics: dict,
                      params: dict):
    """Append optimization entry to trade_log.json."""
    try:
        with open(path) as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = {
            "strategy_version": "1.0.0",
            "last_update": "",
            "last_trade_count": 0,
            "update_history": [],
        }

    # Bump version
    parts = log.get("strategy_version", "1.0.0").split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = ".".join(parts)

    log["strategy_version"] = new_version
    log["last_update"] = datetime.now().isoformat()
    log["last_trade_count"] = opt_metrics["total_trades"]
    log["update_history"].append({
        "version": new_version,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trade_count_at_update": opt_metrics["total_trades"],
        "changes": f"Parameter optimization: Sharpe {baseline_metrics['sharpe_ratio']:.4f} -> {opt_metrics['sharpe_ratio']:.4f}",
        "optimized_params": params,
    })

    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def _update_changelog(path: str, baseline_metrics: dict, opt_metrics: dict,
                      params: dict):
    """Prepend optimization entry to CHANGELOG.md."""
    try:
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = "# Changelog\n"

    date_str = datetime.now().strftime("%Y-%m-%d")
    param_lines = "\n".join(f"  - `{k}`: {v}" for k, v in params.items())

    entry = f"""
## v1.1.0 - {date_str}

### Added
- Python backtesting framework with SMC engine
- Grid search parameter optimization
- Walk-forward analysis
- Performance reporting

### Optimized Parameters
{param_lines}

### Performance (Backtest)
- Sharpe: {baseline_metrics['sharpe_ratio']:.4f} -> {opt_metrics['sharpe_ratio']:.4f}
- Win Rate: {baseline_metrics['win_rate']:.2f}% -> {opt_metrics['win_rate']:.2f}%
- Profit Factor: {baseline_metrics['profit_factor']:.4f} -> {opt_metrics['profit_factor']:.4f}
- Net P&L: ${baseline_metrics['net_pnl']:.2f} -> ${opt_metrics['net_pnl']:.2f}

"""

    # Insert after the first heading line
    lines = existing.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            header_end = i + 1
            break

    new_content = "\n".join(lines[:header_end]) + "\n" + entry + "\n".join(lines[header_end:])

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)


def _save_profitable_snapshot(output_dir: str, params: dict, metrics: dict,
                              iteration: int, mc_results: dict = None,
                              oos_metrics: dict = None):
    """Save a profitable parameter set as profitable_smcV1."""
    snapshot_dir = os.path.join(output_dir, "profitable_smcV1")
    os.makedirs(snapshot_dir, exist_ok=True)

    snapshot = {
        "version": "profitable_smcV1",
        "found_at_iteration": iteration,
        "found_at": datetime.now().isoformat(),
        "objective": _active_objective,
        "params": params,
        "metrics": {
            "sharpe_ratio": metrics["sharpe_ratio"],
            "sortino_ratio": metrics.get("sortino_ratio", 0),
            "calmar_ratio": metrics.get("calmar_ratio", 0),
            "net_pnl": metrics["net_pnl"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"],
            "total_trades": metrics["total_trades"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
        },
    }

    if oos_metrics:
        snapshot["out_of_sample"] = {
            "sharpe_ratio": oos_metrics["sharpe_ratio"],
            "net_pnl": oos_metrics["net_pnl"],
            "win_rate": oos_metrics["win_rate"],
            "profit_factor": oos_metrics["profit_factor"],
            "total_trades": oos_metrics["total_trades"],
        }

    if mc_results:
        snapshot["monte_carlo"] = {
            "robust": mc_results["robust"],
            "pct_profitable": mc_results["pct_profitable"],
            "pnl_p5": mc_results["pnl"]["p5"],
            "pnl_p50": mc_results["pnl"]["p50"],
            "max_dd_p95": mc_results["max_drawdown"]["p95"],
        }

    path = os.path.join(snapshot_dir, "profitable_smcV1.json")
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"  Profitable snapshot saved to: {path}")


# Fine-grained refinement steps around a seed parameter set
# Tighter range + coarser steps (~500 combos per seed, ~1500 total)
REFINE_STEPS = {
    "swingLen":   {"step": 1,     "range": 1,    "min": 2,    "max": 15},
    "obMaxAge":   {"step": 25,    "range": 25,   "min": 25,   "max": 300},
    "atrSlMult":  {"step": 0.2,   "range": 0.4,  "min": 0.3,  "max": 4.0},
    "rrRatio":    {"step": 0.25,  "range": 0.5,  "min": 0.5,  "max": 5.0},
    "fvgMinSize": {"step": 0.25,  "range": 0.25, "min": 0.01, "max": 3.0},
    "pdLookback": {"step": 10,    "range": 10,   "min": 10,   "max": 150},
}


def _build_fine_grid(seed_params: dict) -> dict:
    """Build a fine-grained search space around a seed parameter set."""
    space = {}
    for param, cfg in REFINE_STEPS.items():
        seed_val = seed_params.get(param, DEFAULT_PARAMS.get(param))
        if seed_val is None:
            continue

        step = cfg["step"]
        rng = cfg["range"]
        lo = max(cfg["min"], seed_val - rng)
        hi = min(cfg["max"], seed_val + rng)

        if isinstance(seed_val, int) or cfg.get("type") == int:
            values = list(range(int(lo), int(hi) + 1, int(step)))
        else:
            values = []
            v = lo
            while v <= hi + step * 0.01:
                values.append(round(v, 4))
                v += step

        # Ensure seed value is in the list
        if seed_val not in values:
            values.append(seed_val)
            values.sort()

        space[param] = values

    return space


def refine(data: pd.DataFrame, seed_params: dict = None,
           seed_results: list = None, top_n: int = 3,
           output_dir: str = None) -> dict:
    """
    Fine-grained refinement search around top parameter sets.

    Args:
        data: OHLCV DataFrame
        seed_params: Single seed parameter dict to refine around
        seed_results: List of grid search result dicts (takes top N by score)
        top_n: Number of top results to use as seeds
        output_dir: Directory to save results

    Returns:
        Dict with best refined result
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    # Determine seed points
    seeds = []
    if seed_results:
        scored = sorted(seed_results, key=lambda x: x["score"], reverse=True)
        for r in scored[:top_n]:
            p = DEFAULT_PARAMS.copy()
            p.update(r["params"])
            seeds.append(p)
    elif seed_params:
        p = DEFAULT_PARAMS.copy()
        p.update(seed_params)
        seeds.append(p)
    else:
        # Try loading from optimized_params.json
        opt_path = os.path.join(output_dir, "optimized_params.json")
        if os.path.exists(opt_path):
            with open(opt_path) as f:
                loaded = json.load(f)
            loaded.pop("_metadata", None)
            p = DEFAULT_PARAMS.copy()
            p.update(loaded)
            seeds.append(p)
        else:
            seeds.append(DEFAULT_PARAMS.copy())

    # Build fine grids and deduplicate
    all_combos = set()
    keys = list(REFINE_STEPS.keys())

    for seed in seeds:
        fine_space = _build_fine_grid(seed)
        fine_keys = [k for k in keys if k in fine_space]
        fine_values = [fine_space[k] for k in fine_keys]

        for combo in itertools.product(*fine_values):
            all_combos.add(tuple(zip(fine_keys, combo)))

    combos = [dict(c) for c in all_combos]
    total = len(combos)

    # Baseline
    print(f"Refining around {len(seeds)} seed(s), {total} fine-grained combinations...")
    baseline = run_backtest(data, seeds[0])
    baseline_score = _objective(baseline["metrics"])
    print(f"  Seed baseline: {baseline['metrics']['total_trades']} trades, "
          f"Sharpe={baseline['metrics']['sharpe_ratio']:.4f}, "
          f"PnL=${baseline['metrics']['net_pnl']:.2f}")

    best_score = baseline_score
    best_params = seeds[0].copy()
    best_result = baseline

    for i, combo in enumerate(combos):
        params = DEFAULT_PARAMS.copy()
        # Carry over instrument-specific params from seed
        for k, v in seeds[0].items():
            if k not in REFINE_STEPS:
                params[k] = v
        params.update(combo)

        result = run_backtest(data, params)
        score = _objective(result["metrics"])

        if score > best_score:
            best_score = score
            best_params = params.copy()
            best_result = result

        if (i + 1) % max(1, total // 5) == 0:
            pct = (i + 1) / total * 100
            print(f"  [{pct:5.1f}%] {i + 1}/{total} | "
                  f"Best Sharpe: {best_result['metrics']['sharpe_ratio']:.4f}")

    changed = {k: best_params[k] for k in keys if k in best_params}
    print_optimization_report(baseline, best_result, changed)

    # Save
    opt_params_path = os.path.join(output_dir, "optimized_params.json")
    opt_out = {k: best_params[k] for k in keys if k in best_params}
    opt_out["_metadata"] = {
        "optimized_at": datetime.now().isoformat(),
        "method": "refinement",
        "seeds": len(seeds),
        "combos_tested": total,
        "baseline_sharpe": baseline["metrics"]["sharpe_ratio"],
        "optimized_sharpe": best_result["metrics"]["sharpe_ratio"],
    }
    with open(opt_params_path, "w") as f:
        json.dump(opt_out, f, indent=2)
    print(f"\nRefined parameters saved to: {opt_params_path}")

    _update_trade_log(os.path.join(output_dir, "trade_log.json"),
                      baseline["metrics"], best_result["metrics"], changed)

    return {
        "baseline": baseline,
        "best": best_result,
        "best_params": changed,
    }


def loop_until_profitable(data: pd.DataFrame, output_dir: str = None,
                          max_iterations: int = 5, base_params: dict = None,
                          use_bayesian: bool = True) -> dict:
    """
    Repeatedly optimize and refine until the strategy is profitable.

    Each iteration:
    1. Bayesian optimization (or grid search) on 70% train data
    2. Refine top results
    3. Validate on 30% test data (walk-forward)
    4. If profitable on BOTH train AND test → save snapshot + Monte Carlo
    5. Keep looping to improve further

    Args:
        data: OHLCV DataFrame
        output_dir: Directory to save results
        max_iterations: Max optimization loops
        base_params: Starting parameter set (uses DEFAULT_PARAMS if None)
        use_bayesian: Use Optuna Bayesian optimization (default True)

    Returns:
        Best result found (profitable or best-effort)
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    best_overall = None
    best_overall_score = float("-inf")
    current_params = (base_params or DEFAULT_PARAMS).copy()

    # Walk-forward split: 70% train, 30% test
    split_idx = int(len(data) * 0.7)
    train_data = data.iloc[:split_idx].reset_index(drop=True)
    test_data = data.iloc[split_idx:].reset_index(drop=True)
    print(f"  Walk-forward split: {len(train_data)} train bars, {len(test_data)} test bars")

    # Expanding search spaces for each iteration
    expansion_params = [
        {},  # Iteration 0: use defaults
        {"atrPeriod": [10, 14, 20], "trailAfterR": [0.5, 1.0, 1.5]},
        {"maxDailyTrades": [3, 5, 8], "eqTolerance": [0.05, 0.1, 0.2]},
        {"htfBars": [8, 16, 32], "htfSwingLen": [3, 5, 7]},
        {"obMitigateBody": [True, False], "liqLookback": [10, 20, 30]},
    ]

    for iteration in range(max_iterations):
        print(f"\n{'='*60}")
        print(f"  OPTIMIZATION LOOP — Iteration {iteration + 1}/{max_iterations}")
        print(f"{'='*60}")

        extra = expansion_params[iteration] if iteration < len(expansion_params) else {}

        # Phase 1: Optimize on TRAIN data only
        print(f"\n--- Phase 1: Optimization on train data ---")
        if use_bayesian:
            n_trials = 300 + iteration * 100  # More trials each iteration
            opt_result = optimize_bayesian(train_data, output_dir=output_dir,
                                           n_trials=n_trials, base_params=current_params,
                                           extra_space=extra if extra else None)
        else:
            space = SEARCH_SPACE.copy()
            space.update(extra)
            opt_result = optimize(train_data, output_dir=output_dir,
                                  search_space=space, quick=False)

        # Phase 2: Refine top results on train data
        print(f"\n--- Phase 2: Refinement on train data ---")
        refined = refine(train_data, seed_results=opt_result["all_results"],
                         top_n=1, output_dir=output_dir)

        # Phase 3: Validate on TEST data (out-of-sample)
        print(f"\n--- Phase 3: Out-of-sample validation ---")
        best_params_full = DEFAULT_PARAMS.copy()
        best_params_full.update(current_params)
        best_params_full.update(refined["best_params"])

        train_result = refined["best"]
        test_result = run_backtest(test_data, best_params_full)
        train_metrics = train_result["metrics"]
        test_metrics = test_result["metrics"]

        print(f"\n  {'':20s} {'In-Sample':>12s} {'Out-of-Sample':>14s}")
        print(f"  {'Trades':20s} {train_metrics['total_trades']:>12d} {test_metrics['total_trades']:>14d}")
        print(f"  {'Win Rate':20s} {train_metrics['win_rate']:>11.2f}% {test_metrics['win_rate']:>13.2f}%")
        print(f"  {'Net P&L':20s} ${train_metrics['net_pnl']:>10,.2f} ${test_metrics['net_pnl']:>12,.2f}")
        print(f"  {'Sharpe':20s} {train_metrics['sharpe_ratio']:>12.4f} {test_metrics['sharpe_ratio']:>14.4f}")
        print(f"  {'Sortino':20s} {train_metrics.get('sortino_ratio',0):>12.4f} {test_metrics.get('sortino_ratio',0):>14.4f}")
        print(f"  {'Calmar':20s} {train_metrics.get('calmar_ratio',0):>12.4f} {test_metrics.get('calmar_ratio',0):>14.4f}")
        print(f"  {'Profit Factor':20s} {train_metrics['profit_factor']:>12.4f} {test_metrics['profit_factor']:>14.4f}")

        # Use full-data score for overall ranking
        full_result = run_backtest(data, best_params_full)
        score = _objective(full_result["metrics"])
        metrics = full_result["metrics"]

        if score > best_overall_score:
            best_overall_score = score
            best_overall = {"best": full_result, "best_params": refined["best_params"],
                            "baseline": opt_result["baseline"]}

        # Check profitability on BOTH train AND test
        train_profitable = train_metrics["sharpe_ratio"] > 0 and train_metrics["net_pnl"] > 0
        test_profitable = test_metrics["sharpe_ratio"] > 0 and test_metrics["net_pnl"] > 0

        if train_profitable and test_profitable:
            print(f"\n  *** PROFITABLE ON BOTH IN-SAMPLE AND OUT-OF-SAMPLE ***")
            print(f"  Full-data Sharpe: {metrics['sharpe_ratio']:.4f}")
            print(f"  Full-data P&L:    ${metrics['net_pnl']:.2f}")

            # Phase 4: Monte Carlo robustness test
            print(f"\n--- Phase 4: Monte Carlo robustness test ---")
            mc = monte_carlo(full_result["trades"] if hasattr(full_result["trades"][0], 'pnl')
                             else [type('T', (), t)() for t in full_result["trades"]],
                             n_simulations=1000)
            print_monte_carlo_report(mc)

            # Save snapshot with Monte Carlo results
            _save_profitable_snapshot(output_dir, refined["best_params"],
                                      metrics, iteration + 1, mc_results=mc,
                                      oos_metrics=test_metrics)

            print(f"\n  Snapshot saved as profitable_smcV1. Continuing optimization...")
        elif train_profitable:
            print(f"\n  Profitable in-sample but NOT out-of-sample. Continuing...")
        else:
            print(f"\n  Not yet profitable. Continuing to iteration {iteration + 2}...")

    print(f"\n  Optimization complete ({max_iterations} iterations). "
          f"Best Sharpe: {best_overall['best']['metrics']['sharpe_ratio']:.4f}")
    return best_overall


if __name__ == "__main__":
    from trading.backtest.data_provider import generate_synthetic_data

    print("Generating 2.5 years of synthetic MNQ data...")
    data = generate_synthetic_data(years=2.5)
    print(f"Generated {len(data)} bars\n")

    optimize(data)
