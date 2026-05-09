"""
lean_runner.py — Gate 1: Run Lean backtests locally and push results to the cloud app.

Usage:
    python3 scripts/lean_runner.py AAPL --strategy sma_rsi --resolution Daily
    python3 scripts/lean_runner.py BTCUSDT --strategy breakout --resolution Hour
    python3 scripts/lean_runner.py AAPL --strategy mean_reversion --push https://your-app.onrender.com

Requirements:
    - pip install lean
    - Docker Desktop running
    - lean login (run once with your free QC account)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent
LEAN_DIR    = REPO_ROOT / "lean"
ALGO_DIR    = LEAN_DIR / "Algorithm"

STRATEGY_MAP = {
    "sma_rsi":        "SmaRsi",
    "breakout":       "Breakout",
    "mean_reversion": "MeanReversion",
}

RESOLUTION_MAP = {
    "1d": "Daily", "daily": "Daily",
    "1h": "Hour",  "hour":  "Hour",
    "1m": "Minute","minute":"Minute",
    "tick": "Tick",
    "second": "Second",
}


# ── parameter builders ────────────────────────────────────────────────────────

def _date_params(lookback_years: int = 4) -> dict:
    end   = datetime.utcnow()
    start = end - timedelta(days=lookback_years * 365)
    return {
        "start_year":  str(start.year),
        "start_month": str(start.month),
        "start_day":   str(start.day),
        "end_year":    str(end.year),
        "end_month":   str(end.month),
        "end_day":     str(end.day),
    }


def build_params(
    symbol: str,
    strategy: str,
    resolution: str = "Daily",
    allow_short: bool = True,
    capital: int = 10_000,
    lookback_years: int = 4,
    overrides: dict | None = None,
) -> dict:
    base = {
        "symbol":      symbol,
        "resolution":  resolution,
        "capital":     str(capital),
        "allow_short": "true" if allow_short else "false",
        **_date_params(lookback_years),
    }
    # strategy-specific defaults
    if strategy == "sma_rsi":
        base.update({"fast_ma":"20","slow_ma":"50","rsi_period":"14",
                     "rsi_buy":"35.0","rsi_sell":"65.0"})
    elif strategy == "breakout":
        base.update({"lookback_n":"20","atr_period":"14","atr_mult":"1.0"})
    elif strategy == "mean_reversion":
        base.update({"bb_period":"20","bb_std":"2.0","rsi_period":"14",
                     "rsi_oversold":"30.0","rsi_overbought":"70.0"})

    if overrides:
        base.update({k: str(v) for k, v in overrides.items()})
    return base


# ── lean.json writer ──────────────────────────────────────────────────────────

def write_lean_json(params: dict) -> None:
    lean_json = LEAN_DIR / "lean.json"
    cfg = json.loads(lean_json.read_text()) if lean_json.exists() else {}
    cfg["parameters"] = params
    lean_json.write_text(json.dumps(cfg, indent=4))


# ── result parser ─────────────────────────────────────────────────────────────

def _find_results_json(backtests_dir: Path, algo_name: str) -> Path | None:
    """Find the most recent results.json in lean/backtests/{algo_name}/"""
    target = backtests_dir / algo_name
    if not target.exists():
        # try case-insensitive search
        for d in backtests_dir.iterdir():
            if d.name.lower() == algo_name.lower():
                target = d
                break
        else:
            return None

    # most recent timestamped subfolder
    runs = sorted([d for d in target.iterdir() if d.is_dir()], reverse=True)
    for run in runs:
        candidate = run / "results.json"
        if candidate.exists():
            return candidate
    return None


def parse_lean_results(results_path: Path, symbol: str, strategy: str,
                       resolution: str, params: dict) -> dict:
    raw = json.loads(results_path.read_text())
    stats = raw.get("Statistics", {})
    charts = raw.get("Charts", {})

    # equity curve
    equity_series = (charts.get("Strategy Equity", {})
                           .get("Series", {})
                           .get("Equity", {})
                           .get("Values", []))
    equity_curve = [{"t": p["x"], "v": p["y"]} for p in equity_series]

    # drawdown series
    dd_series = (charts.get("Drawdown", {})
                       .get("Series", {})
                       .get("Drawdown", {})
                       .get("Values", []))

    def _pct(key: str, default: float = 0.0) -> float:
        v = stats.get(key, default)
        try:
            s = str(v).strip().replace("%", "")
            return float(s) / 100 if "%" in str(v) else float(s)
        except (ValueError, TypeError):
            return default

    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(stats.get(key, default))
        except (ValueError, TypeError):
            return default

    # map QC stat names → our verdict schema
    verdict_data = {
        "source":          "lean_local",
        "symbol":          symbol,
        "strategy":        strategy,
        "resolution":      resolution,
        "run_at":          datetime.utcnow().isoformat(),
        "params":          params,
        # core metrics
        "total_return_pct":  round(_pct("Net Profit") * 100, 2),
        "cagr_pct":          round(_pct("Compounding Annual Return") * 100, 2),
        "sharpe_ratio":      round(_f("Sharpe Ratio"), 3),
        "sortino_ratio":     round(_f("Sortino Ratio"), 3),
        "max_drawdown_pct":  round(_pct("Drawdown") * -100, 2),
        "win_rate_pct":      round(_pct("Win Rate") * 100, 1),
        "profit_factor":     round(_f("Profit-Loss Ratio"), 3),
        "n_trades":          int(_f("Total Trades")),
        "avg_trade_pct":     round(_pct("Average Win") * 100, 3),
        # institutional
        "alpha":             round(_f("Alpha"), 4),
        "beta":              round(_f("Beta"), 4),
        "information_ratio": round(_f("Information Ratio"), 3),
        "probabilistic_sharpe": round(_f("Probabilistic Sharpe Ratio", 0), 3),
        "total_fees":        round(_f("Total Fees"), 2),
        "capacity":          stats.get("Estimated Strategy Capacity", "—"),
        # series
        "equity_curve":      equity_curve,
        "drawdown_series":   [{"t": p["x"], "v": p["y"]} for p in dd_series],
    }

    # rolling stats
    rolling = raw.get("RollingStatistics", [])
    verdict_data["rolling_stats"] = rolling

    return verdict_data


# ── lean subprocess runner ────────────────────────────────────────────────────

def run_lean_backtest(algo_name: str, lean_dir: Path) -> tuple[bool, str]:
    """
    Run `lean backtest {algo_name}` in lean_dir.
    Returns (success, stderr_output).
    """
    cmd = ["lean", "backtest", algo_name, "--output", str(lean_dir / "backtests")]
    print(f"[lean_runner] Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        cwd=str(lean_dir),
        capture_output=False,   # stream output live
        text=True,
    )
    return result.returncode == 0, ""


# ── push results to cloud app ─────────────────────────────────────────────────

def push_to_server(data: dict, base_url: str, username: str, password: str) -> bool:
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/lean-result",
            json=data,
            auth=HTTPBasicAuth(username, password),
            timeout=30,
        )
        resp.raise_for_status()
        print(f"[lean_runner] Pushed to {base_url}: {resp.json()}", flush=True)
        return True
    except Exception as e:
        print(f"[lean_runner] Push failed: {e}", file=sys.stderr)
        return False


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run Lean backtest and push results")
    parser.add_argument("symbol",               help="Ticker symbol (e.g. AAPL, BTCUSDT)")
    parser.add_argument("--strategy",  default="sma_rsi",
                        choices=["sma_rsi","breakout","mean_reversion"])
    parser.add_argument("--resolution", default="Daily",
                        help="Resolution: Daily|Hour|Minute|Second|Tick")
    parser.add_argument("--years",  type=int, default=4,    help="Lookback years")
    parser.add_argument("--capital",type=int, default=10000, help="Starting capital")
    parser.add_argument("--no-short", action="store_true",   help="Long-only mode")
    parser.add_argument("--push",   default="",              help="Base URL of Render app to push results")
    parser.add_argument("--user",   default=os.environ.get("TRADING_OPS_USER","trader"))
    parser.add_argument("--password", default=os.environ.get("TRADING_OPS_PASSWORD",""))
    args = parser.parse_args()

    # normalize resolution
    resolution = RESOLUTION_MAP.get(args.resolution.lower(), args.resolution)

    algo_name = STRATEGY_MAP.get(args.strategy)
    if not algo_name:
        print(f"Unknown strategy: {args.strategy}", file=sys.stderr)
        sys.exit(1)

    # check lean CLI installed
    if not shutil.which("lean"):
        print("lean CLI not found. Installing...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "lean", "--quiet"], check=True)

    # build + write params
    params = build_params(
        symbol=args.symbol.upper(),
        strategy=args.strategy,
        resolution=resolution,
        allow_short=not args.no_short,
        capital=args.capital,
        lookback_years=args.years,
    )
    write_lean_json(params)
    print(f"[lean_runner] Params written: {params}", flush=True)

    # run lean backtest
    success, _ = run_lean_backtest(algo_name, LEAN_DIR)
    if not success:
        print("[lean_runner] Lean backtest failed — check Docker is running and "
              "you're logged in with `lean login`.", file=sys.stderr)
        sys.exit(1)

    # find results
    results_path = _find_results_json(LEAN_DIR / "backtests", algo_name)
    if not results_path:
        print(f"[lean_runner] results.json not found in {LEAN_DIR}/backtests/{algo_name}/",
              file=sys.stderr)
        sys.exit(1)

    print(f"[lean_runner] Results: {results_path}", flush=True)
    verdict = parse_lean_results(results_path, args.symbol.upper(),
                                  args.strategy, resolution, params)

    # print to stdout
    print(json.dumps(verdict, indent=2, default=str))

    # push to server if requested
    if args.push:
        push_to_server(verdict, args.push, args.user, args.password)


if __name__ == "__main__":
    main()
