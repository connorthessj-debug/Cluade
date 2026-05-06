@echo off
REM vault-sync.bat — Sync trading-ops scans to Obsidian vault
REM
REM SETUP (one time):
REM   1. Edit your .env file and add:
REM        TRADING_OPS_URL=https://your-app.onrender.com
REM        TRADING_OPS_PASSWORD=yourpassword
REM        VAULT_PROJECT_PATH=C:\Users\conno\OneDrive\ResearchOS\02_Projects
REM
REM   2. Schedule this file in Windows Task Scheduler:
REM        - Open Task Scheduler → Create Basic Task
REM        - Trigger: "When the computer starts" + repeat every 5 minutes
REM        - Action: Start a program
REM        - Program: C:\path\to\Cluade\vault-sync.bat
REM        - Start in: C:\path\to\Cluade

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    exit /b 1
)

python -m pip install requests python-dotenv -q

python scripts\sync_to_vault.py
