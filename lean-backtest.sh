#!/usr/bin/env bash
# ── trading-ops Lean Backtester (Gate 1) ──────────────────────────────────
#
# Requirements:
#   1. Docker Desktop (Mac/Linux) — https://www.docker.com/products/docker-desktop/
#   2. Python 3.9+
#   3. A free QuantConnect account — https://www.quantconnect.com
#
# First-time setup (run once):
#   lean login
#
# Usage:
#   ./lean-backtest.sh AAPL
#   ./lean-backtest.sh AAPL --strategy breakout --resolution Hour
#   ./lean-backtest.sh BTCUSDT --strategy mean_reversion --push https://your-app.onrender.com
# ---------------------------------------------------------------------------
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: ./lean-backtest.sh SYMBOL [--strategy sma_rsi|breakout|mean_reversion] [--push URL]"
    exit 1
fi

# load .env if present
if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# install lean CLI if missing
if ! command -v lean &>/dev/null; then
    echo "Installing lean CLI..."
    pip install lean --quiet
fi

# check Docker
if ! docker info &>/dev/null; then
    echo "Docker is not running. Please start Docker Desktop."
    exit 1
fi

# build push arg from .env if not already in args
PUSH_ARG=""
if [[ "$*" != *"--push"* ]] && [[ -n "${TRADING_OPS_URL:-}" ]]; then
    PUSH_ARG="--push ${TRADING_OPS_URL}"
fi

echo ""
echo "Running Lean backtest for: $*"
echo ""
python3 scripts/lean_runner.py "$@" $PUSH_ARG

echo ""
echo "Done. Results pushed to ${TRADING_OPS_URL:-<no URL set>}"
