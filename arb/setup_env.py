#!/usr/bin/env python3
"""
Interactive setup for Coinbase API credentials.
Writes to arb/.env (gitignored). Credentials stay local only.
"""

import getpass
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

print("=" * 50)
print("  Coinbase API Credential Setup")
print("=" * 50)
print()
print("Your credentials will be saved to:")
print(f"  {ENV_PATH}")
print("This file is gitignored and never committed.")
print()

api_key = input("Paste your API Key Name (organizations/...): ").strip()
print()
api_secret = getpass.getpass("Paste your API Secret (hidden input): ").strip()

# Handle multiline secrets (EC private keys)
if "BEGIN" in api_secret:
    # Already got it in one line with \n
    pass
elif not api_secret:
    print("\nNo secret entered. Aborting.")
    exit(1)

with open(ENV_PATH, "w") as f:
    f.write(f"COINBASE_API_KEY={api_key}\n")
    f.write(f"COINBASE_API_SECRET={api_secret}\n")

# Lock file permissions (owner read/write only)
ENV_PATH.chmod(0o600)

print()
print(f"Saved to {ENV_PATH} (permissions: 600)")
print("You can now run: python backtest/fetch_data.py --days 30")
