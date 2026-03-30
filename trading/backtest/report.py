"""
Performance reporting — formatted console output for backtest results.
"""


def print_backtest_report(result: dict):
    """Print a formatted backtest performance report."""
    m = result["metrics"]
    trades = result.get("trades", [])

    print("=" * 60)
    print("  SMC MNQ BACKTEST REPORT")
    print("=" * 60)

    print(f"\n{'TRADE SUMMARY':^60}")
    print("-" * 60)
    print(f"  Total Trades:      {m['total_trades']}")
    print(f"  Wins / Losses:     {m['wins']} / {m['losses']}")
    print(f"  Win Rate:          {m['win_rate']:.2f}%")
    print(f"  Long / Short:      {m['long_trades']} / {m['short_trades']}")

    print(f"\n{'P&L':^60}")
    print("-" * 60)
    print(f"  Net P&L:           ${m['net_pnl']:>10,.2f}")
    print(f"  Gross Profit:      ${m.get('gross_profit', 0):>10,.2f}")
    print(f"  Gross Loss:        ${m.get('gross_loss', 0):>10,.2f}")
    print(f"  Profit Factor:     {m['profit_factor']:.4f}")

    print(f"\n{'RISK':^60}")
    print("-" * 60)
    print(f"  Max Drawdown:      ${m['max_drawdown']:>10,.2f}")
    print(f"  Max Drawdown %:    {m['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe Ratio:      {m['sharpe_ratio']:.4f}")

    print(f"\n{'AVERAGES':^60}")
    print("-" * 60)
    print(f"  Avg R-Multiple:    {m['avg_r_multiple']:.4f}")
    print(f"  Avg Winner:        ${m['avg_win']:>10,.2f}")
    print(f"  Avg Loser:         ${m['avg_loss']:>10,.2f}")

    # Exit reason breakdown
    if trades:
        reasons = {}
        for t in trades:
            r = t.get("exit_reason", "unknown")
            reasons[r] = reasons.get(r, 0) + 1

        print(f"\n{'EXIT REASONS':^60}")
        print("-" * 60)
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {reason:<20s} {count:>5d}  ({count / len(trades) * 100:.1f}%)")

    print("\n" + "=" * 60)


def print_walk_forward_report(wf_result: dict):
    """Print walk-forward analysis report."""
    folds = wf_result["folds"]
    agg = wf_result["aggregate_oos"]

    print("=" * 70)
    print("  WALK-FORWARD ANALYSIS")
    print("=" * 70)

    for f in folds:
        ins = f["in_sample"]
        oos = f["out_of_sample"]

        print(f"\n  Fold {f['fold']}:")
        print(f"    Train: {f['train_period']} ({f['train_bars']} bars)")
        print(f"    Test:  {f['test_period']} ({f['test_bars']} bars)")
        print(f"    {'':15s} {'In-Sample':>12s} {'Out-of-Sample':>14s}")
        print(f"    {'Trades':15s} {ins['total_trades']:>12d} {oos['total_trades']:>14d}")
        print(f"    {'Win Rate':15s} {ins['win_rate']:>11.2f}% {oos['win_rate']:>13.2f}%")
        print(f"    {'Net P&L':15s} ${ins['net_pnl']:>10,.2f} ${oos['net_pnl']:>12,.2f}")
        print(f"    {'Sharpe':15s} {ins['sharpe_ratio']:>12.4f} {oos['sharpe_ratio']:>14.4f}")
        print(f"    {'Profit Factor':15s} {ins['profit_factor']:>12.4f} {oos['profit_factor']:>14.4f}")

    if agg:
        print(f"\n{'AGGREGATE OUT-OF-SAMPLE':^70}")
        print("-" * 70)
        print(f"  Total OOS Trades:   {agg['total_oos_trades']}")
        print(f"  Total OOS P&L:      ${agg['total_oos_pnl']:,.2f}")
        print(f"  Avg OOS Win Rate:   {agg['avg_oos_win_rate']:.2f}%")
        print(f"  Avg OOS Sharpe:     {agg['avg_oos_sharpe']:.4f}")

    print("\n" + "=" * 70)


def print_optimization_report(baseline: dict, optimized: dict, best_params: dict):
    """Print before/after comparison for parameter optimization."""
    bm = baseline["metrics"]
    om = optimized["metrics"]

    print("=" * 70)
    print("  PARAMETER OPTIMIZATION REPORT")
    print("=" * 70)

    print(f"\n  {'Metric':20s} {'Baseline':>12s} {'Optimized':>12s} {'Change':>12s}")
    print("  " + "-" * 56)

    metrics_to_compare = [
        ("Total Trades", "total_trades", "d"),
        ("Win Rate %", "win_rate", ".2f"),
        ("Net P&L", "net_pnl", ",.2f"),
        ("Profit Factor", "profit_factor", ".4f"),
        ("Sharpe Ratio", "sharpe_ratio", ".4f"),
        ("Max DD %", "max_drawdown_pct", ".2f"),
        ("Avg R-Multiple", "avg_r_multiple", ".4f"),
    ]

    for label, key, fmt in metrics_to_compare:
        bv = bm[key]
        ov = om[key]
        diff = ov - bv
        sign = "+" if diff > 0 else ""
        prefix = "$" if "pnl" in key.lower() else ""
        print(f"  {label:20s} {prefix}{bv:>12{fmt}} {prefix}{ov:>12{fmt}} {sign}{diff:>11{fmt}}")

    print(f"\n  Optimized Parameters:")
    print("  " + "-" * 56)
    for k, v in best_params.items():
        print(f"    {k:20s} = {v}")

    print("\n" + "=" * 70)
