#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SMC Dual-Agent Trading Bot — VPS Setup Script (Hostinger VPS)
#
# Pure Python setup — connects to OANDA REST API directly.
# No Wine, no MT5 terminal needed.
#
# Usage: sudo bash setup_vps.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$USER}"

echo "═══════════════════════════════════════════════"
echo " SMC Trading Bot — VPS Setup"
echo "═══════════════════════════════════════════════"
echo " Bot directory: $BOT_DIR"
echo " User: $USER_NAME"
echo ""

# ── Step 1: System packages ───────────────────────────────────
echo "[1/3] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv

# ── Step 2: Python environment ────────────────────────────────
echo "[2/3] Setting up Python environment..."
VENV_DIR="$BOT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$USER_NAME" python3 -m venv "$VENV_DIR" || python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q

echo "   Python packages installed."

# Create logs directory
mkdir -p "$BOT_DIR/logs"
chown -R "$USER_NAME:$USER_NAME" "$BOT_DIR/logs" 2>/dev/null || true

# ── Step 3: Systemd service ───────────────────────────────────
echo "[3/3] Installing systemd service..."

cat > /etc/systemd/system/smc-trading-bot.service << SERVICEEOF
[Unit]
Description=SMC Dual-Agent Trading Bot (OANDA)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$BOT_DIR
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Safety limits
LimitNOFILE=65536
MemoryMax=1G

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable smc-trading-bot

echo ""
echo "═══════════════════════════════════════════════"
echo " Setup complete!"
echo "═══════════════════════════════════════════════"
echo ""
echo " BEFORE STARTING:"
echo ""
echo " 1. Get your OANDA API credentials:"
echo "    - Sign up at https://www.oanda.com (Practice account)"
echo "    - My Services → Manage API Access → Generate token"
echo "    - Note your Account ID from the account page"
echo ""
echo " 2. Edit config.py with your credentials:"
echo "    nano $BOT_DIR/config.py"
echo ""
echo "    OANDA_API_KEY = \"your-api-token-here\""
echo "    OANDA_ACCOUNT_ID = \"101-001-12345678-001\""
echo ""
echo " 3. Start the bot:"
echo "    sudo systemctl start smc-trading-bot"
echo ""
echo " 4. Check status:"
echo "    sudo systemctl status smc-trading-bot"
echo "    journalctl -u smc-trading-bot -f"
echo ""
echo " 5. View trade logs:"
echo "    tail -f $BOT_DIR/logs/smc_bot.log"
echo "    tail -f $BOT_DIR/logs/trades.log"
echo ""
