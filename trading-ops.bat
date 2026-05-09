@echo off
REM trading-ops.bat - AI Bloomberg Terminal launcher for Windows
REM Place in repo root. Double-click or run from cmd.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Install dependencies (pip is idempotent, skip if already installed)
echo [trading-ops] Checking dependencies...
python -m pip install -r scripts\requirements.txt -q
python -m pip install -r requirements-app.txt -q

REM Launch the app
echo [trading-ops] Launching AI Bloomberg Terminal...
python app.py
if errorlevel 1 (
    echo.
    echo trading-ops exited with an error.
    pause
)
