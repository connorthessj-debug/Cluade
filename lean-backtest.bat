@echo off
REM ── trading-ops Lean Backtester (Gate 1) ──────────────────────────────────
REM
REM Requirements:
REM   1. Docker Desktop — https://www.docker.com/products/docker-desktop/
REM   2. Python 3.9+
REM   3. A free QuantConnect account — https://www.quantconnect.com
REM
REM First-time setup (run once):
REM   lean login
REM
REM Usage:
REM   lean-backtest.bat AAPL
REM   lean-backtest.bat AAPL --strategy breakout --resolution Hour
REM   lean-backtest.bat BTCUSDT --strategy mean_reversion --push https://your-app.onrender.com
REM
REM To push results to your Render app, set these in .env:
REM   TRADING_OPS_URL=https://your-app.onrender.com
REM   TRADING_OPS_USER=trader
REM   TRADING_OPS_PASSWORD=your_password
REM ---------------------------------------------------------------------------

if "%1"=="" (
    echo Usage: lean-backtest.bat SYMBOL [--strategy sma_rsi^|breakout^|mean_reversion] [--push URL]
    exit /b 1
)

REM Load .env if present
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" set %%A=%%B
    )
)

REM Install lean CLI if missing
where lean >nul 2>&1
if errorlevel 1 (
    echo Installing lean CLI...
    pip install lean --quiet
    if errorlevel 1 (
        echo Failed to install lean CLI. Make sure Python and pip are on PATH.
        exit /b 1
    )
)

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Please start Docker Desktop.
    exit /b 1
)

REM Build push arg from .env if not provided on command line
set PUSH_ARG=
echo %* | findstr /i "\-\-push" >nul
if errorlevel 1 (
    if defined TRADING_OPS_URL (
        set PUSH_ARG=--push %TRADING_OPS_URL%
    )
)

echo.
echo Running Lean backtest for: %*
echo.
python scripts\lean_runner.py %* %PUSH_ARG%

if errorlevel 1 (
    echo.
    echo Lean backtest failed. Common causes:
    echo   - Docker Desktop not running
    echo   - Not logged in: run "lean login" first
    echo   - Lean image still downloading (first run takes a few minutes)
    exit /b 1
)

echo.
echo Done. Results pushed to %TRADING_OPS_URL%
