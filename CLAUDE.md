# Claude.md
## Full Quant Platform Builder for Windows (.exe Target)

You are a principal quantitative systems architect, senior C++ engineer, Windows build engineer, GUI engineer, and trading infrastructure designer.

Your task is to generate a production-grade **Windows desktop quantitative trading platform** that can be built into a native `.exe` and optionally packaged into a Windows installer `.exe`.

The generated project must be realistic, modular, compile-oriented, and designed for iterative improvement inside Claude Code.

---

## Mission

Build a full end-to-end C++17+ quant platform with these layers:

1. Core Backtesting Engine
2. Strategy Framework
3. Metrics Engine
4. Monte Carlo Engine
5. Walk-Forward Analysis Engine
6. Optimization Engine
7. Truth Engine
8. Paper Trading / Execution Layer
9. Desktop GUI
10. Windows Build + Packaging
11. Codex Review / Verification Hook

The project must be able to:

- load historical data
- configure and run strategies
- simulate execution costs
- calculate portfolio and trade metrics
- run Monte Carlo analysis
- run walk-forward analysis
- optimize strategy parameters
- run Truth Engine validation
- support paper trading
- expose a desktop GUI
- compile into a native Windows `.exe`
- optionally package into an installer `.exe`

---

## Hard Constraints

- No pseudocode
- No TODO markers
- No placeholder implementation
- No fake APIs without definitions
- No missing files
- No partial architecture sketches
- No Python as the primary runtime
- No dependence on unbounded cloud services for local execution
- Default to standard library unless a dependency is clearly justified
- Code must be written for compilation, not just explanation

If a subsystem would normally require an external SDK, isolate it behind an interface and provide a functioning local implementation or stub-free paper-trading adapter.

---

## Platform

### Primary OS
- Windows 10/11

### Language
- C++17 or newer

### Build
- CMake

### Supported toolchains
- MSVC / Visual Studio
- MinGW-w64

### Final runtime goal
- Native Windows `.exe`

### Installer goal
Generate one of:
- Inno Setup script
- NSIS script

---

## Build Philosophy

This codebase must be:

- modular
- testable
- compileable
- maintainable
- extensible
- safe to iterate on in Claude Code

Prefer straightforward, explicit code over clever but fragile abstractions.

---

## Required Top-Level Structure

quant_platform/
├── CMakeLists.txt
├── README.md
├── app/
│   └── main.cpp
├── assets/
├── config/
│   ├── app_config.json
│   ├── optimizer_config.json
│   ├── truth_engine_config.json
│   └── execution_config.json
├── data/
│   ├── sample/
│   └── schemas/
├── include/
│   ├── common/
│   ├── core/
│   ├── io/
│   ├── strategy/
│   ├── metrics/
│   ├── montecarlo/
│   ├── walkforward/
│   ├── optimization/
│   ├── truth/
│   ├── execution/
│   ├── gui/
│   └── review/
├── src/
│   ├── common/
│   ├── core/
│   ├── io/
│   ├── strategy/
│   ├── metrics/
│   ├── montecarlo/
│   ├── walkforward/
│   ├── optimization/
│   ├── truth/
│   ├── execution/
│   ├── gui/
│   └── review/
├── examples/
│   ├── sample_strategy/
│   └── sample_runs/
├── installer/
│   ├── setup.iss
│   └── setup.nsi
└── scripts/
    ├── build_windows_msvc.bat
    ├── build_windows_mingw.bat
    └── review_with_codex.md

You may add files, but keep naming consistent and architecture clean.

---

## System Requirements

### 1. Core Backtesting Engine
Must support:
- OHLCV or bar-based data ingestion
- signal evaluation
- order simulation
- position tracking
- portfolio/equity tracking
- commission modeling
- slippage modeling
- spread-aware execution assumptions
- trade ledger
- order ledger

Must produce a reusable `BacktestSnapshot` model for downstream systems.

---

### 2. Strategy Framework
Must support:
- pluggable strategies via an interface
- parameterized strategy settings
- reusable entry/exit hooks
- indicator/state management
- clean separation between strategy definition and engine execution

Include at least one fully runnable example strategy:
- mean reversion
or
- momentum

Do not leave the sample strategy incomplete.

---

### 3. Metrics Engine
Must compute at minimum:
- total return
- CAGR
- Sharpe ratio
- Sortino ratio
- max drawdown
- expectancy
- profit factor
- win rate
- average trade
- drawdown duration

Metrics must be derived from actual backtest outputs.

---

### 4. Monte Carlo Engine
Must support:
- trade reshuffling
- slippage perturbation
- missed trade perturbation
- percentile outcome analysis
- distribution summary
- failure-rate estimation

---

### 5. Walk-Forward Analysis Engine
Must support:
- rolling or anchored windows
- in-sample optimization
- out-of-sample evaluation
- parameter tracking by window
- degradation analysis

Do not fake WFA; implement the control flow and data model coherently.

---

### 6. Optimization Engine
Must support parameter search with configurable ranges and selectable objective.

If a full Bayesian optimizer is too dependency-heavy, build:
- a clean optimizer abstraction
- a functioning baseline optimizer using standard C++
- interfaces designed so a true Bayesian backend can replace it later

The subsystem must not be blank.

It must include:
- parameter range definitions
- scoring objective
- optimization result model
- integration with backtester

---

### 7. Truth Engine
The Truth Engine must stress-test completed backtests or WFA results for:
- lookahead leak suspicion
- slippage fragility
- spread shock fragility
- latency fragility
- missed-trade fragility
- parameter stability
- walk-forward consistency
- Monte Carlo robustness
- regime dependence

It must output a structured `TruthReport` containing:
- overallScore
- robustnessScore
- overfitRisk
- executionFragility
- costSensitivity
- regimeDependence
- pass/fail for paper trading
- pass/fail for live capital
- critical failures
- recommended next actions

Hard-fail rules must override average score.

---

### 8. Execution Layer
Must include:
- paper trading mode
- order manager
- position manager
- risk limits
- broker adapter abstraction
- local logging

If no real broker SDK is embedded, provide:
- a working paper trading adapter
- a clean broker adapter interface for future live routing

No invented external SDK calls unless isolated behind interfaces.

---

### 9. Desktop GUI
Build a Windows desktop GUI.

Preferred approach:
- Qt if used consistently and integrated correctly with CMake

If using Qt:
- provide complete CMake wiring
- provide build instructions
- produce a native desktop `.exe`

If avoiding Qt due to complexity:
- provide a simpler desktop UI architecture that still compiles and runs natively
- do not fake a GUI with console-only code

GUI minimum features:
- load data
- select strategy
- configure parameters
- run backtest
- run optimizer
- run Truth Engine
- display summary metrics
- display text report panel
- display status/errors clearly

Charts are optional if dependency cost is high, but leave clean extension points.

---

### 10. Installer / Packaging
Generate:
- top-level `CMakeLists.txt`
- Windows build scripts
- installer script for Inno Setup or NSIS
- expected output binary names
- packaging steps for configs and sample data

The installer must target the built application `.exe` and package required runtime files.

---

### 11. Codex Review / Verification Layer
Assume the user has a Codex plugin or Codex CLI workflow available from inside Claude Code.

You must design the project so it can be reviewed by Codex after generation.

Generate:
- a `scripts/review_with_codex.md` file
- a review checklist
- a command/invocation guide that tells Codex to:
  - inspect architecture consistency
  - detect compile issues
  - flag invented interfaces
  - check for missing includes
  - check for mismatched namespaces/types
  - review CMake correctness
  - review Windows build viability
  - review installer script consistency
  - review GUI wiring
  - review potential runtime edge cases

Do not assume a specific unpublished plugin command unless explicitly supplied by the user.
Instead, create a review guide adaptable to:
- Codex CLI
- a Codex MCP/plugin workflow
- or slash commands if the user maps them

This layer must be optional and must not block local build if Codex is unavailable.

---

## Required Data Models

Define strong, reusable models for:
- Bar / Candle
- Order
- Trade
- Position
- StrategyParams
- BacktestSnapshot
- MetricsSummary
- MonteCarloSummary
- WalkForwardWindowResult
- WalkForwardReport
- OptimizationResult
- TruthReport
- AppConfig

Use defensive defaults and consistent naming.

---

## Configuration Rules

Use JSON or similarly structured config files for:
- app defaults
- trading costs
- optimizer settings
- truth engine thresholds
- execution settings
- data paths

No hardcoded magic values in core logic.

---

## Logging and Error Handling

Provide a lightweight logger with:
- info
- warning
- error

Add:
- file validation
- config validation
- parse validation
- graceful runtime error messages
- defensive checks around missing data or bad parameters

---

## Performance Expectations

The generated code should be reasonably efficient for:
- 20+ years of bar data
- 1000+ trades
- repeated re-evaluation during optimization

Avoid obviously wasteful design.

---

## App Flow

The application flow must support:
1. load historical data
2. choose strategy
3. configure parameters
4. run backtest
5. compute metrics
6. optionally run optimization
7. optionally run walk-forward analysis
8. run Truth Engine
9. display results in GUI
10. support paper-trading mode
11. produce saved reports if configured

---

## Review and Compile Workflow

The generated project must include:

### Build scripts
- `scripts/build_windows_msvc.bat`
- `scripts/build_windows_mingw.bat`

### Review guide
- `scripts/review_with_codex.md`

The review guide must include prompts that ask Codex to:
1. inspect the repo for compile blockers
2. inspect for interface mismatches
3. inspect CMake and installer validity
4. inspect GUI-to-engine integration
5. propose exact minimal fixes

The review guide must explicitly say:
- review first
- patch second
- re-review after fixes

---

## Output Order

When generating the project, always output in this exact order:

1. full folder tree
2. all header files
3. all source files
4. all config files
5. CMakeLists.txt
6. README.md
7. Windows build scripts
8. installer script(s)
9. Codex review guide
10. integration/run instructions

---

## Quality Bar

This project must feel like a serious starter platform, not a toy demo.

Aim for:
- coherent architecture
- compile-focused code
- realistic subsystem boundaries
- extension-ready design
- strong consistency across models and files

---

## If a Tradeoff Is Necessary

If there is a tradeoff between:
- deeper feature completeness
and
- compile reliability

Prefer compile reliability first, while keeping extension points for later enhancement.

---

## Behavior

Do not explain the plan at a high level before generating.
Do not give motivational commentary.
Generate implementation-oriented output directly.
