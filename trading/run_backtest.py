#!/usr/bin/env python3
"""
CLI entry point for SMC backtesting and optimization.

Usage:
    python trading/run_backtest.py                                    # Basic backtest with defaults
    python trading/run_backtest.py --optimize                         # Grid search optimization
    python trading/run_backtest.py --refine                           # Refine around current best
    python trading/run_backtest.py --loop                             # Loop until profitable
    python trading/run_backtest.py --walk-forward                     # Walk-forward analysis
    python trading/run_backtest.py --instrument gold --style scalping # Gold scalping
    python trading/run_backtest.py --params optimized.json            # Custom params
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.backtest.data_provider import (
    generate_synthetic_data, load_csv_data, fetch_yahoo_2yr,
    fetch_yahoo_long, load_csv_provider,
)
from trading.backtest.backtester import run_backtest, walk_forward
from trading.backtest.report import (
    print_backtest_report,
    print_walk_forward_report,
)
from trading.backtest.smc_engine import DEFAULT_PARAMS
from trading.backtest.instruments import INSTRUMENTS, STYLE_DEFAULTS, get_params


def load_params(filepath: str, base: dict = None) -> dict:
    """Load parameters from a JSON file, merging with base."""
    with open(filepath) as f:
        custom = json.load(f)
    custom.pop("_metadata", None)
    return {**(base or DEFAULT_PARAMS), **custom}


def save_results(result: dict, filepath: str):
    """Save backtest results to JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved to: {filepath}")


def load_data(args, instrument_key: str = None):
    """Load data based on CLI arguments."""
    if args.csv:
        data = load_csv_provider(args.csv)
        print(f"Loaded {len(data)} bars from {args.csv}")
    elif args.long_history:
        symbol = INSTRUMENTS[instrument_key]["symbol"] if instrument_key else "NQ=F"
        years = args.history_years
        print(f"Fetching {years}-year daily {symbol} data from Yahoo Finance...")
        data = fetch_yahoo_long(symbol, years=years)
        print(f"Fetched {len(data)} daily bars ({data['timestamp'].iloc[0].date()} to {data['timestamp'].iloc[-1].date()})")
    elif instrument_key and instrument_key in INSTRUMENTS:
        symbol = INSTRUMENTS[instrument_key]["symbol"]
        print(f"Fetching 2-year {symbol} data from Yahoo Finance...")
        data = fetch_yahoo_2yr(symbol)
        print(f"Fetched {len(data)} bars ({data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]})")
    else:
        data = generate_synthetic_data(years=args.years, seed=args.seed)
        print(f"Generated {len(data)} bars of synthetic data "
              f"({data['timestamp'].iloc[0].date()} to {data['timestamp'].iloc[-1].date()})")
    return data


def get_output_dir(instrument: str, style: str) -> str:
    """Get output directory for a given instrument/style combo."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "strategies", style, instrument)


def main():
    parser = argparse.ArgumentParser(description="SMC Backtesting System")
    parser.add_argument("--optimize", action="store_true",
                        help="Run parameter optimization (grid search)")
    parser.add_argument("--refine", action="store_true",
                        help="Refine around current best parameters")
    parser.add_argument("--loop", action="store_true",
                        help="Loop optimize+refine until profitable")
    parser.add_argument("--walk-forward", action="store_true",
                        help="Run walk-forward analysis")
    parser.add_argument("--strategy", type=str, default="smc",
                        choices=["smc", "rsi2"],
                        help="Strategy engine (default: smc)")
    parser.add_argument("--instrument", type=str, default=None,
                        choices=list(INSTRUMENTS.keys()),
                        help="Instrument to trade")
    parser.add_argument("--style", type=str, default="smc_swing",
                        choices=list(STYLE_DEFAULTS.keys()),
                        help="Trading style (default: smc_swing)")
    parser.add_argument("--params", type=str, default=None,
                        help="Path to custom parameters JSON file")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to CSV data file")
    parser.add_argument("--years", type=float, default=2.5,
                        help="Years of synthetic data (default: 2.5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--folds", type=int, default=5,
                        help="Walk-forward folds (default: 5)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")
    parser.add_argument("--quick", action="store_true",
                        help="Use reduced search space for faster optimization")
    parser.add_argument("--bayesian", action="store_true", default=True,
                        help="Use Bayesian (Optuna) optimization (default)")
    parser.add_argument("--grid", action="store_true",
                        help="Use grid search instead of Bayesian optimization")
    parser.add_argument("--objective", type=str, default="composite",
                        choices=["sharpe", "sortino", "calmar", "composite"],
                        help="Objective function (default: composite)")
    parser.add_argument("--monte-carlo", action="store_true",
                        help="Run Monte Carlo simulation after backtest")
    parser.add_argument("--mc-sims", type=int, default=1000,
                        help="Number of Monte Carlo simulations (default: 1000)")
    parser.add_argument("--dashboard", action="store_true",
                        help="Launch web dashboard")
    parser.add_argument("--long-history", action="store_true",
                        help="Use 20-year daily data from Yahoo Finance")
    parser.add_argument("--history-years", type=int, default=20,
                        help="Years of daily history with --long-history (default: 20)")

    args = parser.parse_args()

    # Dashboard mode
    if args.dashboard:
        from trading.dashboard import run_dashboard
        run_dashboard()
        return

    # Set objective function
    from trading.auto_improve import set_objective
    set_objective(args.objective)
    print(f"Objective: {args.objective}")

    # Load data
    print("Loading data...")
    data = load_data(args, args.instrument)

    # Determine engine type and style
    engine_type = args.strategy
    style = args.style
    if engine_type == "rsi2":
        style = "rsi2"

    # Build params
    if args.params:
        base = get_params(args.instrument or "mnq", style)
        params = load_params(args.params, base)
        print(f"Loaded custom parameters from {args.params}")
    elif args.instrument:
        params = get_params(args.instrument, style)
        print(f"Using {style} params for {args.instrument}")
    else:
        if engine_type == "rsi2":
            from trading.backtest.rsi2_engine import RSI2_DEFAULT_PARAMS
            params = RSI2_DEFAULT_PARAMS.copy()
        else:
            params = DEFAULT_PARAMS.copy()

    # Determine output directory
    inst_key = args.instrument or "mnq"
    out_dir = get_output_dir(inst_key, style)
    os.makedirs(out_dir, exist_ok=True)

    use_bayesian = not args.grid

    if args.loop:
        from trading.auto_improve import loop_until_profitable
        result = loop_until_profitable(data, output_dir=out_dir,
                                       base_params=params,
                                       use_bayesian=use_bayesian,
                                       engine_type=engine_type)
        if args.output:
            save_results(result, args.output)

    elif args.optimize:
        if use_bayesian and not args.quick:
            from trading.auto_improve import optimize_bayesian
            result = optimize_bayesian(data, output_dir=out_dir,
                                       base_params=params,
                                       engine_type=engine_type)
        else:
            from trading.auto_improve import optimize
            result = optimize(data, output_dir=out_dir, quick=args.quick)

        if args.refine:
            from trading.auto_improve import refine
            refine(data, seed_results=result["all_results"],
                   top_n=3, output_dir=out_dir)

    elif args.refine:
        from trading.auto_improve import refine
        opt_path = os.path.join(out_dir, "optimized_params.json")
        seed = None
        if os.path.exists(opt_path):
            seed = load_params(opt_path, params)
            print(f"Refining around params from {opt_path}")
        refine(data, seed_params=seed or params, output_dir=out_dir)

    elif args.walk_forward:
        print(f"\nRunning walk-forward analysis ({args.folds} folds)...")
        wf_result = walk_forward(data, params, n_folds=args.folds)
        print_walk_forward_report(wf_result)
        if args.output:
            save_results(wf_result, args.output)

    else:
        print("\nRunning backtest...")
        result = run_backtest(data, params, engine_type=engine_type)
        print_backtest_report(result)

        if args.monte_carlo:
            from trading.backtest.backtester import monte_carlo
            from trading.backtest.report import print_monte_carlo_report
            print("\nRunning Monte Carlo simulation...")
            mc = monte_carlo(result["trades"] if result["trades"] and hasattr(result["trades"][0], 'pnl')
                             else [type('T', (), t)() for t in result.get("trades", [])],
                             n_simulations=args.mc_sims)
            print_monte_carlo_report(mc)

        if args.output:
            save_results(result, args.output)


if __name__ == "__main__":
    main()
