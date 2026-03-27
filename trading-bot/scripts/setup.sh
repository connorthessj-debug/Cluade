#!/bin/bash
# =============================================================================
# Trading Bot - One-Line Server Setup Script
# Usage: curl -sSL <raw_url> | bash
# Or:    bash setup.sh
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }

# -------------------------------------------------------------------
# 1. System dependencies
# -------------------------------------------------------------------
log "Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv nodejs npm git sqlite3 > /dev/null 2>&1
log "System packages installed."

# -------------------------------------------------------------------
# 2. Clone repo (or pull if already cloned)
# -------------------------------------------------------------------
INSTALL_DIR="$HOME/trading-bot-system"

if [ -d "$INSTALL_DIR" ]; then
    warn "Directory $INSTALL_DIR already exists. Pulling latest..."
    cd "$INSTALL_DIR"
    git pull origin claude/trading-bot-dashboard-zKuw9 || true
else
    log "Cloning repository..."
    git clone -b claude/trading-bot-dashboard-zKuw9 https://github.com/connorthessj-debug/Cluade.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

BOTDIR="$INSTALL_DIR/trading-bot"
cd "$BOTDIR"

# -------------------------------------------------------------------
# 3. Python virtual environment + dependencies
# -------------------------------------------------------------------
log "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
log "Python dependencies installed."

# -------------------------------------------------------------------
# 4. Node.js dashboard dependencies
# -------------------------------------------------------------------
log "Installing dashboard dependencies..."
cd "$BOTDIR/dashboard"
npm install --silent 2>/dev/null
cd "$BOTDIR"
log "Dashboard dependencies installed."

# -------------------------------------------------------------------
# 5. Create data directories
# -------------------------------------------------------------------
mkdir -p "$BOTDIR/data/logs"

# -------------------------------------------------------------------
# 6. Interactive API key setup
# -------------------------------------------------------------------
ENV_FILE="$BOTDIR/.env"

if [ -f "$ENV_FILE" ]; then
    warn ".env file already exists. Skipping key setup."
    warn "Edit it manually with: nano $ENV_FILE"
else
    log "Setting up API keys..."
    echo ""
    echo "========================================="
    echo "  API Key Configuration"
    echo "========================================="
    echo ""
    echo "Leave blank to skip any exchange."
    echo ""

    read -p "OANDA Account ID: " OANDA_ACCOUNT_ID
    read -p "OANDA API Key: " OANDA_API_KEY
    read -p "OANDA Environment (practice/live) [practice]: " OANDA_ENV
    OANDA_ENV=${OANDA_ENV:-practice}

    echo ""
    read -p "Binance API Key: " BINANCE_API_KEY
    read -p "Binance Secret Key: " BINANCE_SECRET

    echo ""
    read -p "Coinbase API Key (optional): " COINBASE_API_KEY
    read -p "Coinbase Secret (optional): " COINBASE_SECRET

    cat > "$ENV_FILE" << ENVEOF
# OANDA (Scalper + Swing bots)
OANDA_ACCOUNT_ID=${OANDA_ACCOUNT_ID}
OANDA_API_KEY=${OANDA_API_KEY}
OANDA_ENVIRONMENT=${OANDA_ENV}

# Binance (Arbitrage bot)
BINANCE_API_KEY=${BINANCE_API_KEY}
BINANCE_SECRET=${BINANCE_SECRET}

# Coinbase (Arbitrage bot - optional)
COINBASE_API_KEY=${COINBASE_API_KEY}
COINBASE_SECRET=${COINBASE_SECRET}
ENVEOF

    chmod 600 "$ENV_FILE"
    log "API keys saved to .env (permissions locked to owner only)."
fi

# -------------------------------------------------------------------
# 7. Create systemd service for 24/7 operation
# -------------------------------------------------------------------
log "Creating systemd service..."

SERVICE_FILE="/etc/systemd/system/trading-bot.service"
sudo tee "$SERVICE_FILE" > /dev/null << SVCEOF
[Unit]
Description=Multi-Agent Trading Bot System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BOTDIR
ExecStart=$BOTDIR/venv/bin/python scripts/run_all.py
Restart=always
RestartSec=10
Environment=PATH=$BOTDIR/venv/bin:/usr/local/bin:/usr/bin:/bin
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable trading-bot
log "Systemd service created and enabled (starts on boot)."

# -------------------------------------------------------------------
# 8. Create helper commands
# -------------------------------------------------------------------
HELPER="$HOME/.local/bin/tbot"
mkdir -p "$HOME/.local/bin"

cat > "$HELPER" << 'HELPEREOF'
#!/bin/bash
BOTDIR="$HOME/trading-bot-system/trading-bot"

case "$1" in
    start)
        sudo systemctl start trading-bot
        echo "Trading bot started."
        ;;
    stop)
        sudo systemctl stop trading-bot
        echo "Trading bot stopped."
        ;;
    restart)
        sudo systemctl restart trading-bot
        echo "Trading bot restarted."
        ;;
    status)
        sudo systemctl status trading-bot --no-pager
        ;;
    logs)
        journalctl -u trading-bot -f --no-pager
        ;;
    keys)
        nano "$BOTDIR/.env"
        echo "Restart with: tbot restart"
        ;;
    dashboard)
        IP=$(curl -s ifconfig.me)
        echo "Dashboard: http://$IP:8080"
        ;;
    backtest)
        shift
        cd "$BOTDIR" && source venv/bin/activate
        python scripts/backtest.py "$@"
        ;;
    test)
        cd "$BOTDIR" && source venv/bin/activate
        python -m pytest tests/ -v
        ;;
    *)
        echo "Usage: tbot {start|stop|restart|status|logs|keys|dashboard|backtest|test}"
        echo ""
        echo "  start     - Start the trading bot system"
        echo "  stop      - Stop all bots"
        echo "  restart   - Restart all bots"
        echo "  status    - Show service status"
        echo "  logs      - Stream live logs"
        echo "  keys      - Edit API keys"
        echo "  dashboard - Show dashboard URL"
        echo "  backtest  - Run backtester"
        echo "  test      - Run unit tests"
        ;;
esac
HELPEREOF

chmod +x "$HELPER"

# Add to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi

# -------------------------------------------------------------------
# 9. Open firewall for dashboard
# -------------------------------------------------------------------
if command -v ufw &> /dev/null; then
    sudo ufw allow 8080/tcp > /dev/null 2>&1 || true
    log "Firewall opened on port 8080."
fi

# -------------------------------------------------------------------
# 10. Done
# -------------------------------------------------------------------
echo ""
echo "========================================="
echo -e "${GREEN}  Setup Complete!${NC}"
echo "========================================="
echo ""
IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
echo "Quick commands (type these in Termius):"
echo ""
echo "  tbot start      Start the bots"
echo "  tbot stop       Stop everything"
echo "  tbot status     Check if running"
echo "  tbot logs       Watch live logs"
echo "  tbot keys       Edit API keys"
echo "  tbot dashboard  Get dashboard URL"
echo ""
echo -e "Dashboard: ${GREEN}http://$IP:8080${NC}"
echo ""
if [ -z "$OANDA_ACCOUNT_ID" ] && [ ! -f "$ENV_FILE" ]; then
    warn "No API keys configured. Run 'tbot keys' to add them."
fi
echo "To start now: tbot start"
echo ""
