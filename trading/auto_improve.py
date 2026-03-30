#!/usr/bin/env python3
"""
Auto-improvement system for SMC MNQ strategy.
Performs grid search parameter optimization with guard rails.
"""

import json
import os
import itertools
from datetime import datetime

import numpy as np
import pandas as pd

from trading.backtest.backtester import run_backtest
from trading.backtest.smc_engine import DEFAULT_PARAMS
from trading.backtest.report import print_optimization_report


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


def _objective(metrics: dict) -> float:
    """
    Score a parameter set. Higher is better.
    Maximizes Sharpe ratio with constraints.
    Returns -inf for parameter sets that violate guard rails.
    """
    if metrics["total_trades"] < MIN_TRADES:
        return float("-inf")
    if metrics["max_drawdown_pct"] > MAX_DRAWDOWN_PCT:
        return float("-inf")
    if metrics["win_rate"] < MIN_WIN_RATE:
        return float("-inf")

    # Primary: Sharpe ratio
    # Secondary bonus for profit factor and win rate
    score = metrics["sharpe_ratio"]
    score += 0.1 * min(metrics["profit_factor"], 5.0)  # cap PF contribution
    score += 0.01 * metrics["win_rate"]

    return score


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
        with open(path) as f:
            existing = f.read()
    except FileNotFoundError:
        existing = "# Changelog\n"

    date_str = datetime.now().strftime("%Y-%m-%d")
    param_lines = "\n".join(f"  - `{k}`: {v}" for k, v in params.items())

    entry = f"""
## v1.1.0 — {date_str}

### Added
- Python backtesting framework with SMC engine
- Grid search parameter optimization
- Walk-forward analysis
- Performance reporting

### Optimized Parameters
{param_lines}

### Performance (Backtest)
- Sharpe: {baseline_metrics['sharpe_ratio']:.4f} → {opt_metrics['sharpe_ratio']:.4f}
- Win Rate: {baseline_metrics['win_rate']:.2f}% → {opt_metrics['win_rate']:.2f}%
- Profit Factor: {baseline_metrics['profit_factor']:.4f} → {opt_metrics['profit_factor']:.4f}
- Net P&L: ${baseline_metrics['net_pnl']:.2f} → ${opt_metrics['net_pnl']:.2f}

"""

    # Insert after the first heading line
    lines = existing.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            header_end = i + 1
            break

    new_content = "\n".join(lines[:header_end]) + "\n" + entry + "\n".join(lines[header_end:])

    with open(path, "w") as f:
        f.write(new_content)


# Fine-grained refinement steps around a seed parameter set
# Wide range + fine steps for maximum precision (~13k combos per seed)
REFINE_STEPS = {
    "swingLen":   {"step": 1,     "range": 2,    "min": 2,    "max": 15},
    "obMaxAge":   {"step": 25,    "range": 50,   "min": 25,   "max": 300},
    "atrSlMult":  {"step": 0.1,   "range": 0.3,  "min": 0.3,  "max": 4.0},
    "rrRatio":    {"step": 0.25,  "range": 0.5,  "min": 0.5,  "max": 5.0},
    "fvgMinSize": {"step": 0.125, "range": 0.25, "min": 0.01, "max": 3.0},
    "pdLookback": {"step": 5,     "range": 10,   "min": 10,   "max": 150},
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
                          max_iterations: int = 5, base_params: dict = None) -> dict:
    """
    Repeatedly optimize and refine until the strategy is profitable.

    Each iteration:
    1. Quick grid search
    2. Refine top 3 results
    3. Check if profitable (Sharpe > 0 AND net_pnl > 0)
    4. If not, widen the search space and retry

    Args:
        data: OHLCV DataFrame
        output_dir: Directory to save results
        max_iterations: Max optimization loops
        base_params: Starting parameter set (uses DEFAULT_PARAMS if None)

    Returns:
        Best result found (profitable or best-effort)
    """
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    best_overall = None
    best_overall_score = float("-inf")
    current_params = (base_params or DEFAULT_PARAMS).copy()

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

        # Build search space — full grid (1,728 combos) + expansions
        space = SEARCH_SPACE.copy()
        if iteration < len(expansion_params):
            space.update(expansion_params[iteration])

        # Phase 1: Grid search
        grid_result = optimize(data, output_dir=output_dir, search_space=space,
                               quick=False)

        # Phase 2: Refine top results
        print(f"\n--- Refinement phase ---")
        refined = refine(data, seed_results=grid_result["all_results"],
                         top_n=3, output_dir=output_dir)

        best = refined["best"]
        score = _objective(best["metrics"])
        metrics = best["metrics"]

        print(f"\n  Iteration {iteration + 1} result: "
              f"Sharpe={metrics['sharpe_ratio']:.4f}, "
              f"PnL=${metrics['net_pnl']:.2f}, "
              f"WR={metrics['win_rate']:.1f}%")

        if score > best_overall_score:
            best_overall_score = score
            best_overall = refined

        # Check profitability
        if metrics["sharpe_ratio"] > 0 and metrics["net_pnl"] > 0:
            print(f"\n  *** PROFITABLE STRATEGY FOUND ***")
            print(f"  Sharpe: {metrics['sharpe_ratio']:.4f}")
            print(f"  Net P&L: ${metrics['net_pnl']:.2f}")
            print(f"  Win Rate: {metrics['win_rate']:.2f}%")
            print(f"  Profit Factor: {metrics['profit_factor']:.4f}")
            return best_overall

    print(f"\n  Max iterations reached. Best Sharpe: "
          f"{best_overall['best']['metrics']['sharpe_ratio']:.4f}")
    return best_overall


if __name__ == "__main__":
    from trading.backtest.data_provider import generate_synthetic_data

    print("Generating 2.5 years of synthetic MNQ data...")
    data = generate_synthetic_data(years=2.5)
    print(f"Generated {len(data)} bars\n")

    optimize(data)
