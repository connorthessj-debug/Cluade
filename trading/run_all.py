#!/usr/bin/env python3
"""
Batch runner — runs optimization across all instrument × style combinations.

Usage:
    python trading/run_all.py                        # All instruments, all styles
    python trading/run_all.py --style scalping       # All instruments, scalping only
    python trading/run_all.py --instrument gold      # Gold only, all styles
    python trading/run_all.py --loop                 # Loop until profitable for each
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.backtest.data_provider import fetch_yahoo_2yr
from trading.backtest.backtester import run_backtest
from trading.backtest.instruments import INSTRUMENTS, STYLE_DEFAULTS, get_params
from trading.auto_improve import optimize, refine, loop_until_profitable, QUICK_SEARCH_SPACE


def run_single(instrument: str, style: str, do_loop: bool = False,
               quick: bool = False) -> dict:
    """Run optimization for a single instrument/style combo."""
    inst_info = INSTRUMENTS[instrument]
    symbol = inst_info["symbol"]

    print(f"\n{'#'*70}")
    print(f"  {inst_info['name']} — {style}")
    print(f"  Ticker: {symbol}")
    print(f"{'#'*70}")

    # Fetch data
    print(f"\nFetching 2-year {symbol} data...")
    try:
        data = fetch_yahoo_2yr(symbol)
        print(f"  Got {len(data)} bars")
    except Exception as e:
        print(f"  ERROR fetching data: {e}")
        return {"instrument": instrument, "style": style, "error": str(e)}

    # Get params
    params = get_params(instrument, style)

    # Output dir
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, "strategies", style, instrument)
    os.makedirs(out_dir, exist_ok=True)

    # Run
    if do_loop:
        result = loop_until_profitable(data, output_dir=out_dir,
                                       base_params=params)
    else:
        # Quick optimize + refine
        grid_result = optimize(data, output_dir=out_dir,
                               search_space=QUICK_SEARCH_SPACE, quick=quick)
        result = refine(data, seed_results=grid_result["all_results"],
                        top_n=3, output_dir=out_dir)

    # Save results summary
    best_metrics = result["best"]["metrics"]
    summary = {
        "instrument": instrument,
        "instrument_name": inst_info["name"],
        "style": style,
        "symbol": symbol,
        "optimized_at": datetime.now().isoformat(),
        "metrics": best_metrics,
        "params": result.get("best_params", {}),
        "profitable": best_metrics["net_pnl"] > 0 and best_metrics["sharpe_ratio"] > 0,
    }

    results_path = os.path.join(out_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Results saved to: {results_path}")

    return summary


def print_summary_table(results: list):
    """Print a summary table of all results."""
    print(f"\n{'='*90}")
    print(f"  SUMMARY — All Instruments × Styles")
    print(f"{'='*90}")
    print(f"\n  {'Instrument':<12s} {'Style':<12s} {'Trades':>7s} {'Win%':>6s} "
          f"{'PF':>6s} {'Sharpe':>8s} {'Net PnL':>12s} {'Status':>10s}")
    print(f"  {'-'*75}")

    for r in results:
        if "error" in r:
            print(f"  {r['instrument']:<12s} {r['style']:<12s} {'ERROR':>55s}")
            continue

        m = r["metrics"]
        status = "PROFIT" if r["profitable"] else "LOSS"
        print(f"  {r['instrument']:<12s} {r['style']:<12s} {m['total_trades']:>7d} "
              f"{m['win_rate']:>5.1f}% {m['profit_factor']:>6.2f} "
              f"{m['sharpe_ratio']:>8.4f} ${m['net_pnl']:>11,.2f} "
              f"{'  ✓' if r['profitable'] else '  ✗':>10s}")

    profitable = sum(1 for r in results if r.get("profitable"))
    print(f"\n  Profitable: {profitable}/{len(results)}")
    print(f"{'='*90}")


def main():
    parser = argparse.ArgumentParser(description="Batch Optimizer — All Instruments")
    parser.add_argument("--instrument", type=str, default=None,
                        choices=list(INSTRUMENTS.keys()),
                        help="Single instrument (default: all)")
    parser.add_argument("--style", type=str, default=None,
                        choices=list(STYLE_DEFAULTS.keys()),
                        help="Single style (default: all)")
    parser.add_argument("--loop", action="store_true",
                        help="Loop until profitable for each combo")
    parser.add_argument("--quick", action="store_true",
                        help="Use quick search space")

    args = parser.parse_args()

    instruments = [args.instrument] if args.instrument else list(INSTRUMENTS.keys())
    styles = [args.style] if args.style else list(STYLE_DEFAULTS.keys())

    total = len(instruments) * len(styles)
    print(f"Running {total} instrument × style combinations...")
    print(f"  Instruments: {', '.join(instruments)}")
    print(f"  Styles: {', '.join(styles)}")
    print(f"  Mode: {'loop until profitable' if args.loop else 'optimize + refine'}")

    results = []
    for inst in instruments:
        for style in styles:
            try:
                result = run_single(inst, style, do_loop=args.loop,
                                    quick=args.quick)
                results.append(result)
            except Exception as e:
                print(f"\n  ERROR on {inst}/{style}: {e}")
                results.append({
                    "instrument": inst, "style": style, "error": str(e)
                })

    print_summary_table(results)

    # Save master summary
    base_dir = os.path.dirname(os.path.abspath(__file__))
    summary_path = os.path.join(base_dir, "strategies", "summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nMaster summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
