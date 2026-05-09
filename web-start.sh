#!/bin/bash
# web-start.sh - Launch the mobile web server (Linux/macOS)
# Access from phone: http://<your-pc-ip>:8000

cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+"
    exit 1
fi

echo "[trading-ops] Installing dependencies..."
python3 -m pip install -r scripts/requirements.txt -q
python3 -m pip install -r requirements-web.txt -q

PORT="${PORT:-8000}"
echo ""
echo "[trading-ops] Starting mobile web server on port $PORT"
echo "[trading-ops] Local:   http://localhost:$PORT"
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$LAN_IP" ] && LAN_IP=$(ipconfig getifaddr en0 2>/dev/null)
[ -n "$LAN_IP" ] && echo "[trading-ops] LAN:     http://$LAN_IP:$PORT"
echo ""
echo "[trading-ops] For internet access from work, see DEPLOY.md (Render/Fly/Cloudflare Tunnel)."
echo ""

python3 -m uvicorn web.server:app --host 0.0.0.0 --port "$PORT"
