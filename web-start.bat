@echo off
REM web-start.bat - Launch mobile web server (Windows)
REM Access from phone: http://<your-pc-ip>:8000

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [trading-ops] Installing dependencies...
python -m pip install -r scripts\requirements.txt -q
python -m pip install -r requirements-web.txt -q

if "%PORT%"=="" set PORT=8000

echo.
echo [trading-ops] Starting mobile web server on port %PORT%
echo [trading-ops] Local: http://localhost:%PORT%
echo [trading-ops] To find your LAN IP: run "ipconfig" and use the IPv4 address.
echo [trading-ops] For internet access from work, see DEPLOY.md.
echo.

python -m uvicorn web.server:app --host 0.0.0.0 --port %PORT%

if errorlevel 1 (
    echo.
    echo Server exited with an error.
    pause
)
