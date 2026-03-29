#!/bin/bash
# Simple credential setup - writes to arb/.env
ENV_FILE="$(dirname "$0")/.env"

echo "Coinbase API Credential Setup"
echo "=============================="
echo ""
read -p "Paste your API Key Name: " API_KEY
echo ""
echo "Paste your API Secret (the entire key including BEGIN/END lines)."
echo "When done, press Enter then Ctrl+D:"
API_SECRET=$(cat)

cat > "$ENV_FILE" << ENVEOF
COINBASE_API_KEY=${API_KEY}
COINBASE_API_SECRET=${API_SECRET}
ENVEOF

chmod 600 "$ENV_FILE"
echo ""
echo "Saved to $ENV_FILE"
