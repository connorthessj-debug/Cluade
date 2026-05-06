#!/bin/bash
# vault-sync.sh — Sync trading-ops scans to Obsidian vault (macOS/Linux)
#
# Schedule with crontab -e:
#   */5 * * * * /path/to/Cluade/vault-sync.sh >> /tmp/vault-sync.log 2>&1

cd "$(dirname "$0")"
python3 -m pip install requests python-dotenv -q 2>/dev/null
python3 scripts/sync_to_vault.py
