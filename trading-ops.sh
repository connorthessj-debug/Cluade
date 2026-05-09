#!/bin/bash
# trading-ops.sh - AI Bloomberg Terminal launcher (Linux/macOS)

cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+"
    exit 1
fi

echo "[trading-ops] Checking dependencies..."
python3 -m pip install -r scripts/requirements.txt -q
python3 -m pip install -r requirements-app.txt -q

echo "[trading-ops] Launching AI Bloomberg Terminal..."
python3 app.py
