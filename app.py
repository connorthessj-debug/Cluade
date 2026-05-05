#!/usr/bin/env python3
"""trading-ops — AI Bloomberg Terminal

Run with:  python3 app.py
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

try:
    from textual.app import App
except ImportError:
    print("ERROR: textual is not installed.")
    print("Install with:  pip install -r requirements-app.txt")
    sys.exit(1)

from ui.screens.main_screen import MainScreen


class TradingOpsApp(App):
    """AI Bloomberg Terminal — version-controlled trading research workspace."""

    CSS_PATH = "ui/styles.tcss"
    TITLE = "trading-ops · AI Bloomberg Terminal"
    SUB_TITLE = "scan, regime, audit"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


def main() -> None:
    if not os.environ.get("FRED_API_KEY"):
        print("[trading-ops] WARNING: FRED_API_KEY not set. Macro panel will show data gaps.")
        print("[trading-ops] Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        print("[trading-ops] Then create a .env file (copy .env.example) with FRED_API_KEY=...")
        print()
    TradingOpsApp().run()


if __name__ == "__main__":
    main()
