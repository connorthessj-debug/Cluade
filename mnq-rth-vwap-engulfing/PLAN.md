# MNQ RTH VWAP Engulfing — Plan Review & Implementation Plan

## Context

The user pasted a detailed spec for an automated MNQ 1-minute RTH VWAP engulfing
strategy, to be built twice for cross-platform parity:

1. TradingView **Pine Script v6** strategy
2. MetaTrader 5 **MQL5** Expert Advisor

Branch `claude/mnq-rth-vwap-engulfing-724p2` is already checked out. The
repository is otherwise unrelated (Le Besian Balls site, a Python schedule
generator) — this is a green-field add. The user asked two direct questions:

- *Is this the best plan?*
- *Are you using the "superpowers" tool kit?*

**Superpowers answer:** No. No such plugin is loaded in this session. Available
skills here are: `update-config`, `keybindings-help`, `simplify`,
`fewer-permission-prompts`, `loop`, `claude-api`, `session-start-hook`, `init`,
`review`, `security-review`. If the user expected a specific plugin pack, it
needs to be installed/enabled before I can use it.

## Assessment of the user's spec

**Good bones.** Single pattern, RTH-anchored VWAP, multi-TF confluence, fixed
ATR exits, closed-bar logic, daily locks, and the parity-first / baseline-first
research sequencing are all correct discipline. The anti-repaint pattern
(`lookahead_on` + `[1]` offset for `request.security`) and conservative tick
rounding are right.

**But it is not yet the *best* plan.** Ten concrete weaknesses:

1. **Filter stack is thin-stream.** VWAP-side + VWAP-slope + EMA9>EMA21 +
   HTF-trend + HTF-slope + close-location + body + range cap, over a 115-minute
   entry window, will starve the backtest. Low N → false confidence.
2. **Redundant day-locks.** `-3R daily loss` and `3 consecutive losses` both
   fire on the same event (three full stops). Keep one, or space them.
3. **BE-at-1.5R on a 2R target is usually destructive.** Most trades tag 1.5R
   en route to 2R then pull back; BE is hit, trade exits flat. If BE stays,
   default to **1.0R**, not 1.5R.
4. **Swing-trail is under-specified.** "Trail behind confirmed 1-minute
   structure" will diverge badly between Pine and MT5 without a concrete pivot
   rule (e.g. `pivotlow(low, 3, 3) - 1 tick`).
5. **ATR gates [3.0, 30.0] are magic numbers.** They need empirical grounding
   for MNQ, ideally expressed as rolling percentile rather than absolute points.
6. **Perfect cross-platform parity is unrealistic.** Pine `volume` on futures
   ≠ MT5 `real_volume`/`tick_volume` from a retail broker feed. Expect
   VWAP drift; document it rather than chase it.
7. **No statistical pass/fail gate.** "Test baseline first" with no minimum
   trade count or profit-factor threshold will guarantee overfitting.
8. **Pyramiding conflation.** In Pine, `pyramiding=1` allows one same-direction
   add-on — *not* the intended "one position at a time." Use
   `pyramiding=1` **and** an explicit `strategy.position_size == 0` guard.
9. **No default commission/slippage.** MNQ realistic defaults: ~$1.24
   round-trip commission, 2-tick slippage. Ship these, don't leave blank.
10. **No flatten-at-session-end.** 11:30 ET entry cutoff doesn't close open
    trades; path-dependent exits can run into afternoon chop. Add optional
    hard-flatten at 15:55 ET (default on).

## Recommended implementation (applies the 10 refinements)

### Files to create (new)

- `mnq-rth-vwap-engulfing/MNQ_RTH_VWAP_Engulfing.pine`
- `mnq-rth-vwap-engulfing/MNQ_RTH_VWAP_Engulfing.mq5`
- `mnq-rth-vwap-engulfing/README.md`

No edits to existing files.

### Pine v6 strategy — key construction points

- `strategy(..., pyramiding=1, calc_on_every_tick=false,
  process_orders_on_close=false)`; commission default
  `strategy.commission.cash_per_contract = 1.24`, slippage default `2`.
- Manual RTH VWAP: reset on first bar where `time(timeframe.period,
  "0930-1600:1234567", "America/New_York")` is non-na after being na;
  accumulate `TP*volume` and `volume`.
- HTF filter: `request.security(sym, "5", expr[1], lookahead=barmerge.lookahead_on)`.
  Never reference `barstate.isconfirmed` inside `request.security`.
- Engulfing: closed-bar only, strict body/range/close-location gates per spec.
- Entries: `strategy.entry` with `when = condition and strategy.position_size == 0
  and cooldownOK and not dayLock`.
- Exits: `strategy.exit` with `stop = floorTick/ceilTick(...)`, `limit = ...`.
- Optional BE default `1.0R`; optional pivot-trail via
  `ta.pivotlow/pivothigh(low/high, 3, 3)`.
- Day-lock: single gate `dailyR <= -3R`. Consec-loss retained as optional input
  (default off).
- Flatten hook: if `time > 15:55 ET`, `strategy.close_all()`.
- Webhook JSON via `alert_message =` on each `strategy.entry`/`strategy.exit`.
- Visuals: plot VWAP, M1 EMAs, stepped HTF EMAs, session shading, active SL/TP
  lines, status table (bias / trades today / consec losses / atr / lock state).

### MT5 EA — key construction points

- `#include <Trade/Trade.mqh>`, `CTrade`, `trade.SetExpertMagicNumber(magic)`,
  `trade.SetTypeFillingBySymbol(_Symbol)`,
  `trade.SetDeviationInPoints(inputDeviation)`.
- Indicator handles in `OnInit`: `iATR(_Symbol, PERIOD_M1, 14)`, `iMA` × 4.
- New-bar detection via stored `datetime lastBarTime`; evaluate signal on the
  previous closed bar (`shift=1`).
- VWAP: manual from `CopyRates(_Symbol, PERIOD_M1, 0, maxBars, rates)`; prefer
  `rates[i].real_volume` > 0 else `tick_volume`.
- Session: inputs for `BrokerUTCOffsetWinter`, `BrokerUTCOffsetSummer`, and
  `UseUSDST`; compute NY time from `TimeCurrent()`.
- Normalization helpers: `NormalizePriceDownToTick`, `NormalizePriceUpToTick`,
  `NormalizeVolumeToStep` using `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_VOLUME_MIN/MAX/STEP`.
- Day-lock ledger: `HistorySelect(todayStart, TimeCurrent())`, filter by
  `DEAL_SYMBOL == _Symbol` and `DEAL_MAGIC == magic`, sum realized R.
- Logging via `PrintFormat` with `trade.ResultRetcode()` +
  `trade.ResultRetcodeDescription()`.

### README

One file covering: rules, required TF, VWAP definition, anti-repaint method,
exits, alert setup, webhook JSON shape, daily controls, **known Pine/MT5
parity caveats (VWAP volume source, session-offset handling)**, limitations,
and the 10 refinements and why they were applied.

## Verification

1. **Pine compile.** Paste into TradingView 1-min chart → no errors. Verify
   `calc_on_every_tick` off in properties.
2. **Pine replay.** Bar Replay on a known RTH day; confirm VWAP resets at 09:30
   ET, engulfing markers fire only on closed bars, SL/TP lines track while in
   trade, flatten fires at 15:55 ET.
3. **MT5 compile.** Load `.mq5` in MetaEditor → zero errors, zero warnings
   beyond unused-parameter noise.
4. **MT5 tester.** Strategy Tester on M1 with user-supplied broker offset;
   inspect Journal for new-bar evaluation, SL/TP attach, daily reset, day-lock
   trigger.
5. **Parity check.** Run both on same date window; expect same-direction
   signals on same bars within ±1 bar; document systematic skew in README.
6. **Stats harness (user-side).** Export Pine List of Trades and MT5 tester
   report; check pass/fail criteria: **≥ 100 trades OOS, profit factor ≥ 1.25
   net of commission + 2-tick slippage, max DD ≤ 8R**. Only then proceed to BE
   or trail variants.

## User decisions (resolved)

- **Refinements:** *Apply the important fixes.* Confirmed. All 10 refinements
  above will be applied.
- **Superpowers plugin:** *Pause so user can install it.* Confirmed. After
  ExitPlanMode approval, the user will install the superpowers plugin pack,
  restart the session, and we resume implementation with those skills
  available.
- **Added context:** *"This will be put into an optimizer and backtested
  thoroughly."* This materially changes a few implementation choices (next
  section).

## Optimizer / backtest adaptations (additions to the plan)

Because the code is going through an optimizer (Pine sweeps + MT5 genetic +
walk-forward) and a thorough backtest, the implementation must be
**reproducible, leakage-proof, and sweep-friendly**. Concrete choices:

1. **Every tunable is an `input`** with explicit `minval`, `maxval`, `step`.
   This includes all lengths, multipliers, thresholds, session times,
   cooldown, daily locks, commission, slippage, and filter toggles. MT5
   inputs marked `input` (not `sinput`) so they appear in the optimizer.
2. **Filter-toggle mask.** Each non-trigger filter (VWAP slope, HTF slope,
   VWAP-distance gate, ATR min, ATR max, close-location) is an independent
   boolean input. This lets the optimizer **disable filters** and reveals
   which actually add edge vs. which are decoration. Without this, you
   curve-fit thresholds on filters that don't contribute.
3. **No look-ahead.** Zero use of `lookahead_on` except in the documented
   `request.security(..., expr[1], lookahead=barmerge.lookahead_on)` pattern.
   `calc_on_every_tick = false`, `process_orders_on_close = false`. In MT5:
   all signal logic fires **once on new-bar detection** using bar shift 1.
4. **Deterministic state.** No random numbers, no wall-clock-dependent
   branching. Daily counters reset by session-boundary detection, not by
   local time on the host. In MT5, ledger built by `HistorySelect` scoped to
   `DEAL_SYMBOL == _Symbol && DEAL_MAGIC == magic`.
5. **Clean R accounting.** On entry, store each trade's initial risk in
   points in an array keyed by entry order id (Pine) /
   `POSITION_IDENTIFIER` (MT5). On close, compute realized R =
   realized_$ / (risk_pts × point_value × contracts). This makes Pine's
   List of Trades and MT5's tester report directly comparable.
6. **Walk-forward hooks.** Expose `inSampleStart`, `inSampleEnd`,
   `oosStart`, `oosEnd` inputs in both implementations; logic skips entries
   outside the active window. Lets you run walk-forward without re-coding.
7. **Commission & slippage must be nonzero defaults.** Pine:
   `strategy.commission.cash_per_contract = 1.24`, `slippage = 2`. MT5:
   optimizer defaults `commission_per_lot_rt = 1.24`, `slippage_ticks = 2`.
   Flagged in README: "running with zero costs invalidates the optimization."
8. **Minimum trade-count guard in the strategy itself.** Optional input
   `min_trades_for_validity = 100`; when active, the strategy writes a
   warning label/Print when the sample size from the test window is below
   that. Prevents accidental overfit on a 20-trade window.
9. **No floating-point drift across runs.** All threshold comparisons use
   explicit epsilons where needed; no dependency on NaN-ordering quirks.
10. **Export hooks.** Pine: ensure `strategy.closedtrades.*` accessors are
    populated (they are by default); MT5: write a CSV-style line on each
    closed deal when `!MQL_TESTER` or when
    `InpExportTradesInTester = true`, so a reproducible trade log is
    always available for offline stats analysis.

*(Items on MT5 tester friendliness and Pine sweep friendliness were
dropped per user direction — optimization is being run on a separate
external engine, so those adaptations are unnecessary.)*

These do not change the trading logic, only the surface area and
determinism. They are cheap to add and expensive to retrofit.

## Plan status

**Approved by user**, with the following modifications folded in:

- R/R stays as specified (**1×ATR stop, 2×ATR target** — unchanged).
- Optimizer-adaptation items about MT5 tester friendliness and Pine
  sweep friendliness are **removed** — the user is running a separate
  external optimization/backtest engine, so those adaptations are
  unnecessary.

## Next actions (after ExitPlanMode approval)

1. User installs superpowers plugin pack (popular GitHub toolkit),
   restarts the Claude Code session.
2. Resume on branch `claude/mnq-rth-vwap-engulfing-724p2`.
3. Create the three files listed above.
4. Compile-check Pine (paste into TradingView) and MT5 (MetaEditor).
5. Commit and push.
