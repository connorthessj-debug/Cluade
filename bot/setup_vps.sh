#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SMC Dual-Agent Trading Bot — VPS Setup Script (Hostinger VPS)
#
# This script installs everything needed to run the bot 24/7:
# 1. System packages
# 2. Wine (for MT5 on Linux)
# 3. MetaTrader 5
# 4. Python environment
# 5. Systemd service for 24/7 operation
#
# Usage: sudo bash setup_vps.sh
# ��══════════════════════════════════════════════════════════════

set -euo pipefail

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
HOME_DIR="/home/$USER_NAME"

echo "═══════════════════════════════════════════════"
echo " SMC Trading Bot — VPS Setup"
echo "═══════════════════════════════════════════════"
echo " Bot directory: $BOT_DIR"
echo " User: $USER_NAME"
echo ""

# ── Step 1: System packages ───────────────────────────────────
echo "[1/5] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    wget curl gnupg2 software-properties-common \
    xvfb x11-utils \
    cabextract

# ── Step 2: Install Wine (for MT5) ────────────────────────────
echo "[2/5] Installing Wine..."
dpkg --add-architecture i386

# Add Wine repository
if ! command -v wine &> /dev/null; then
    wget -qO - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
    add-apt-repository -y 'deb https://dl.winehq.org/wine-builds/ubuntu/ jammy main'
    apt-get update -qq
    apt-get install -y -qq --install-recommends winehq-stable || \
        apt-get install -y -qq wine wine64 wine32
fi

echo "   Wine version: $(wine --version 2>/dev/null || echo 'installed')"

# ── Step 3: Download & Install MT5 ────────────────────────────
echo "[3/5] Setting up MetaTrader 5..."
MT5_DIR="$HOME_DIR/.wine/drive_c/Program Files/MetaTrader 5"

if [ ! -d "$MT5_DIR" ]; then
    echo "   Downloading MT5 installer..."
    MT5_INSTALLER="/tmp/mt5setup.exe"
    wget -q "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" \
        -O "$MT5_INSTALLER" || true

    if [ -f "$MT5_INSTALLER" ]; then
        echo "   Installing MT5 via Wine (this may take a few minutes)..."
        echo "   NOTE: You may need to complete MT5 setup manually."
        export WINEPREFIX="$HOME_DIR/.wine"
        export DISPLAY=:99

        # Start virtual display
        Xvfb :99 -screen 0 1024x768x16 &
        XVFB_PID=$!
        sleep 2

        # Run installer silently
        sudo -u "$USER_NAME" wine "$MT5_INSTALLER" /auto &
        sleep 30
        kill $XVFB_PID 2>/dev/null || true

        echo "   MT5 installation initiated."
        echo "   You may need to run MT5 manually first to complete setup:"
        echo "     DISPLAY=:99 wine \"$MT5_DIR/terminal64.exe\""
    else
        echo "   WARNING: Could not download MT5 installer."
        echo "   Please install MT5 manually."
    fi
else
    echo "   MT5 already installed at: $MT5_DIR"
fi

# ── Step 4: Python environment ─────────────────────────────────
echo "[4/5] Setting up Python environment..."
VENV_DIR="$BOT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$USER_NAME" python3 -m venv "$VENV_DIR"
fi

sudo -u "$USER_NAME" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$USER_NAME" "$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q

echo "   Python packages installed."

# Create logs directory
mkdir -p "$BOT_DIR/logs"
chown "$USER_NAME:$USER_NAME" "$BOT_DIR/logs"

# ── Step 5: Systemd service ─────���─────────────────────────────
echo "[5/5] Installing systemd service..."

cat > /etc/systemd/system/smc-trading-bot.service << SERVICEEOF
[Unit]
Description=SMC Dual-Agent Trading Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$BOT_DIR
Environment=DISPLAY=:99
Environment=WINEPREFIX=$HOME_DIR/.wine
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1024x768x16 -ac
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Safety limits
LimitNOFILE=65536
MemoryMax=2G

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable smc-trading-bot

echo ""
echo "═════��═════════════════════════════════════════"
echo " Setup complete!"
echo "══════════��════════════════════════════════════"
echo ""
echo " BEFORE STARTING:"
echo " 1. Edit bot/config.py with your MT5 credentials:"
echo "    - MT5_LOGIN, MT5_PASSWORD, MT5_SERVER"
echo "    - Set ACCOUNT_BALANCE to your actual balance"
echo ""
echo " 2. Update MT5_PATH in config.py:"
echo "    MT5_PATH = '$MT5_DIR/terminal64.exe'"
echo ""
echo " 3. Start MT5 manually first to login and save credentials:"
echo "    Xvfb :99 -screen 0 1024x768x16 &"
echo "    DISPLAY=:99 wine '$MT5_DIR/terminal64.exe'"
echo ""
echo " 4. Start the bot:"
echo "    sudo systemctl start smc-trading-bot"
echo ""
echo " 5. Check status:"
echo "    sudo systemctl status smc-trading-bot"
echo "    journalctl -u smc-trading-bot -f"
echo ""
echo " 6. View trade logs:"
echo "    tail -f $BOT_DIR/logs/smc_bot.log"
echo "    tail -f $BOT_DIR/logs/trades.log"
echo ""
