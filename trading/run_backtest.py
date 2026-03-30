#!/usr/bin/env python3
"""
CLI entry point for SMC MNQ backtesting and optimization.

Usage:
    python trading/run_backtest.py                          # Basic backtest with defaults
    python trading/run_backtest.py --optimize               # Grid search optimization
    python trading/run_backtest.py --walk-forward            # Walk-forward analysis
    python trading/run_backtest.py --params optimized.json   # Backtest with custom params
    python trading/run_backtest.py --years 3.0               # Override data length
"""

import argparse
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.backtest.data_provider import generate_synthetic_data, load_csv_data
from trading.backtest.backtester import run_backtest, walk_forward
from trading.backtest.report import (
    print_backtest_report,
    print_walk_forward_report,
    print_optimization_report,
)
from trading.backtest.smc_engine import DEFAULT_PARAMS


def load_params(filepath: str) -> dict:
    """Load parameters from a JSON file, merging with defaults."""
    with open(filepath) as f:
        custom = json.load(f)
    params = {**DEFAULT_PARAMS, **custom}
    return params


def save_results(result: dict, filepath: str):
    """Save backtest results to JSON."""
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="SMC MNQ Backtesting System")
    parser.add_argument("--optimize", action="store_true",
                        help="Run parameter optimization (grid search)")
    parser.add_argument("--walk-forward", action="store_true",
                        help="Run walk-forward analysis")
    parser.add_argument("--params", type=str, default=None,
                        help="Path to custom parameters JSON file")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to CSV data file (uses synthetic data if not provided)")
    parser.add_argument("--years", type=float, default=2.5,
                        help="Years of synthetic data to generate (default: 2.5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for synthetic data (default: 42)")
    parser.add_argument("--folds", type=int, default=5,
                        help="Number of walk-forward folds (default: 5)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")
    parser.add_argument("--quick", action="store_true",
                        help="Use reduced search space for faster optimization")

    args = parser.parse_args()

    # Load data
    print("Loading data...")
    if args.csv:
        data = load_csv_data(args.csv)
        print(f"Loaded {len(data)} bars from {args.csv}")
    else:
        data = generate_synthetic_data(years=args.years, seed=args.seed)
        print(f"Generated {len(data)} bars of synthetic MNQ data "
              f"({data['timestamp'].iloc[0].date()} to {data['timestamp'].iloc[-1].date()})")

    # Load params
    params = DEFAULT_PARAMS.copy()
    if args.params:
        params = load_params(args.params)
        print(f"Loaded custom parameters from {args.params}")

    if args.optimize:
        # Run auto-improvement
        from trading.auto_improve import optimize
        optimize(data, output_dir=os.path.dirname(os.path.abspath(__file__)),
                 quick=args.quick)

    elif args.walk_forward:
        print(f"\nRunning walk-forward analysis ({args.folds} folds)...")
        wf_result = walk_forward(data, params, n_folds=args.folds)
        print_walk_forward_report(wf_result)

        if args.output:
            save_results(wf_result, args.output)

    else:
        # Standard backtest
        print("\nRunning backtest...")
        result = run_backtest(data, params)
        print_backtest_report(result)

        if args.output:
            save_results(result, args.output)


if __name__ == "__main__":
    main()
