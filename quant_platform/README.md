# Quant Platform

A production-grade C++17 quantitative trading platform for Windows. Includes backtesting, strategy framework, metrics, Monte Carlo simulation, walk-forward analysis, parameter optimization, truth validation, paper trading, and a native Win32 desktop GUI.

## Build Requirements

- CMake 3.16+
- C++17 compiler (MSVC 2019+ or MinGW-w64 8+)
- Windows 10/11

## Quick Build (MSVC)

```batch
cd scripts
build_windows_msvc.bat
```

## Quick Build (MinGW)

```batch
cd scripts
build_windows_mingw.bat
```

## Manual Build

```batch
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

## Usage

### GUI Mode (default on Windows)
```batch
quant_platform.exe
```

### Console Mode
```batch
quant_platform.exe --console
```

## Project Structure

```
quant_platform/
  app/          - Application entry point
  include/      - All header files by subsystem
  src/          - All source files by subsystem
  config/       - JSON configuration files
  data/         - Sample data and schemas
  scripts/      - Build scripts and review guide
  installer/    - Inno Setup and NSIS scripts
  examples/     - Sample strategies and run outputs
```

## Subsystems

1. **Core** - Backtesting engine, order simulator, position tracker
2. **Strategy** - Pluggable strategy interface, momentum and mean reversion strategies
3. **Metrics** - Sharpe, Sortino, CAGR, drawdown, profit factor, win rate, expectancy
4. **Monte Carlo** - Trade reshuffling, slippage perturbation, missed trade simulation
5. **Walk-Forward** - Rolling/anchored window optimization and out-of-sample testing
6. **Optimization** - Grid and random search with pluggable objective functions
7. **Truth Engine** - Strategy stress testing and validation (fragility, overfitting, regime dependence)
8. **Execution** - Paper trading with order/position/risk management
9. **GUI** - Native Win32 desktop interface

## Configuration

All settings are in `config/` as JSON files:
- `app_config.json` - Main application settings
- `optimizer_config.json` - Optimization parameters
- `truth_engine_config.json` - Truth engine thresholds
- `execution_config.json` - Paper trading settings

## Dependencies

- [nlohmann/json](https://github.com/nlohmann/json) - JSON parsing (vendored, single-header)
- Win32 API (Windows SDK, included with MSVC/MinGW)
