"""
backtest_engine.py — Institutional-grade signal-based backtester.

Accepts OHLCV data + a signal Series (values: +1 long, -1 short, 0 flat),
simulates trades with intrabar OHLC stop/TP triggering, slippage, spread,
and risk-based position sizing. Returns a full institutional metric suite.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


# ---------------------------------------------------------------------------
# Parameters & Result
# ---------------------------------------------------------------------------

@dataclass
class BacktestParams:
    stop_loss_pct: float = 0.05        # 5% stop below entry
    take_profit_pct: float = 0.10      # 10% target above entry
    capital: float = 10_000.0
    commission_pct: float = 0.001      # 0.1% per trade (one-way)
    allow_short: bool = True
    slippage_pct: float = 0.0005       # 0.05% per fill (half-spread slippage)
    spread_pct: float = 0.0002         # 0.02% bid-ask spread cost on entry
    position_sizing: str = "fixed"     # "fixed" | "risk_pct"
    risk_pct_per_trade: float = 0.02   # fraction of equity risked (risk_pct mode)
    annualization: int = 252           # bars/year — set by wfa_optimizer per interval


@dataclass
class BacktestResult:
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    n_trades: int = 0
    avg_trade_pct: float = 0.0
    calmar_ratio: float = 0.0
    # Institutional metrics
    ulcer_index: float = 0.0
    recovery_factor: float = 0.0
    expectancy_pct: float = 0.0
    max_consecutive_losses: int = 0
    avg_bars_in_trade: float = 0.0
    exposure_pct: float = 0.0
    r_squared: float = 0.0
    mc_sharpe_p5: float = 0.0
    mc_sharpe_p95: float = 0.0
    equity_curve: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("equity_curve")
        return d


# ---------------------------------------------------------------------------
# Pure-numpy helpers
# ---------------------------------------------------------------------------

def _ulcer_index(equity: np.ndarray) -> float:
    roll_max = np.maximum.accumulate(equity)
    dd_pct = (equity - roll_max) / (roll_max + 1e-10) * 100
    return float(np.sqrt(np.mean(dd_pct ** 2)))


def _r_squared(equity: np.ndarray) -> float:
    n = len(equity)
    if n < 4:
        return 0.0
    x = np.arange(n, dtype=float)
    xm = x.mean()
    ym = equity.mean()
    ss_tot = float(np.sum((equity - ym) ** 2))
    if ss_tot < 1e-10:
        return 1.0
    slope = float(np.sum((x - xm) * (equity - ym)) / np.sum((x - xm) ** 2))
    y_hat = slope * x + (ym - slope * xm)
    ss_res = float(np.sum((equity - y_hat) ** 2))
    return max(0.0, 1.0 - ss_res / ss_tot)


def _max_consecutive_losses(trade_returns: list[float]) -> int:
    max_cl = cur = 0
    for r in trade_returns:
        if r <= 0:
            cur += 1
            max_cl = max(max_cl, cur)
        else:
            cur = 0
    return max_cl


def _monte_carlo_sharpe(
    trade_returns: list[float],
    n_sim: int = 200,
    annualization: int = 252,
) -> tuple[float, float]:
    """Bootstrap-resample trade returns → (p5_sharpe, p95_sharpe)."""
    if len(trade_returns) < 5:
        return 0.0, 0.0
    arr = np.array(trade_returns)
    rng = np.random.default_rng(42)
    sharpes: list[float] = []
    for _ in range(n_sim):
        sample = rng.choice(arr, size=len(arr), replace=True)
        sigma = sample.std()
        if sigma < 1e-10:
            continue
        sharpes.append(float(sample.mean() / sigma * np.sqrt(annualization)))
    if not sharpes:
        return 0.0, 0.0
    sharpes.sort()
    n = len(sharpes)
    return round(sharpes[int(n * 0.05)], 3), round(sharpes[int(n * 0.95)], 3)


# ---------------------------------------------------------------------------
# Core trade simulator — intrabar OHLC with slippage & risk sizing
# ---------------------------------------------------------------------------

def _compute_equity(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signals: np.ndarray,
    stop_pct: float,
    tp_pct: float,
    capital: float,
    commission: float,
    slippage_pct: float,
    spread_pct: float,
    allow_short: bool,
    position_sizing: str,
    risk_pct_per_trade: float,
) -> tuple[np.ndarray, list[dict], np.ndarray]:
    """
    Simulate trades bar-by-bar with intrabar OHLC stop/TP triggering.

    Intrabar logic (conservative / worst-case):
        - For a long: stop = entry*(1-stop_pct), tp = entry*(1+tp_pct)
          hit_stop = bar_low  <= stop_price
          hit_tp   = bar_high >= tp_price
          If both trigger in the same bar → assume stop fills first.
        - Short: mirror logic.

    Returns (equity_curve, trade_list, position_open_mask).
    """
    n = len(close)
    equity = np.full(n, capital, dtype=float)
    cash = capital
    position = 0          # +1 long, -1 short, 0 flat
    entry_price = 0.0
    entry_bar = 0
    pos_fraction = 1.0    # fraction of equity in the trade
    trades: list[dict] = []
    pos_mask = np.zeros(n, dtype=bool)

    for i in range(1, n):
        prev_sig = signals[i - 1]
        bar_high = high[i]
        bar_low  = low[i]
        bar_close = close[i]

        pos_mask[i] = position != 0

        # ── exit open position (intrabar OHLC check) ─────────────────────
        if position != 0:
            if position == 1:
                stop_price = entry_price * (1 - stop_pct)
                tp_price   = entry_price * (1 + tp_pct)
                hit_stop   = bar_low  <= stop_price
                hit_tp     = bar_high >= tp_price
            else:  # short
                stop_price = entry_price * (1 + stop_pct)
                tp_price   = entry_price * (1 - tp_pct)
                hit_stop   = bar_high >= stop_price
                hit_tp     = bar_low  <= tp_price

            signal_exit = (prev_sig == 0) or (prev_sig == -position)

            if hit_stop or hit_tp or signal_exit:
                if hit_stop and hit_tp:
                    # worst-case: stop fires first
                    exit_price = stop_price
                elif hit_stop:
                    exit_price = stop_price
                elif hit_tp:
                    exit_price = tp_price
                else:
                    exit_price = bar_close

                # apply slippage on exit (adverse)
                exit_price *= (1 - position * slippage_pct)

                trade_ret = (exit_price - entry_price) / entry_price * position
                trade_ret -= commission * 2  # entry + exit commission

                # scale trade return to equity
                equity_ret = trade_ret * pos_fraction
                cash *= (1 + equity_ret)

                trades.append({
                    "entry":       entry_price,
                    "exit":        exit_price,
                    "direction":   position,
                    "return_pct":  trade_ret * 100,
                    "bars_held":   i - entry_bar,
                })
                position = 0
                pos_mask[i] = False

        # ── enter new position ────────────────────────────────────────────
        if position == 0 and prev_sig != 0:
            if prev_sig == 1 or allow_short:
                position = int(prev_sig)
                entry_bar = i

                # entry price = open of this bar + slippage + spread
                raw_entry = bar_close  # use close as proxy for open-of-bar fill
                entry_price = raw_entry * (1 + position * (slippage_pct + spread_pct))

                # position sizing
                if position_sizing == "risk_pct":
                    pos_fraction = min(1.0, risk_pct_per_trade / (stop_pct + 1e-10))
                else:
                    pos_fraction = 1.0

                # entry commission on the fraction traded
                cash *= (1 - commission * pos_fraction)
                pos_mask[i] = True

        equity[i] = cash

    return equity, trades, pos_mask


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    params: Optional[BacktestParams] = None,
) -> BacktestResult:
    """
    ohlcv: DataFrame with Open/High/Low/Close/Volume columns, DatetimeIndex.
    signals: Series aligned to ohlcv, values +1/0/-1.
    Returns BacktestResult with full institutional metric suite.
    """
    if params is None:
        params = BacktestParams()

    high  = ohlcv["High"].values.astype(float)  if "High"  in ohlcv.columns else ohlcv["Close"].values.astype(float)
    low   = ohlcv["Low"].values.astype(float)   if "Low"   in ohlcv.columns else ohlcv["Close"].values.astype(float)
    close = ohlcv["Close"].values.astype(float)
    sig   = signals.reindex(ohlcv.index).fillna(0).values.astype(int)

    if len(close) < 10:
        return BacktestResult()

    equity, trades, pos_mask = _compute_equity(
        high, low, close, sig,
        params.stop_loss_pct, params.take_profit_pct,
        params.capital, params.commission_pct,
        params.slippage_pct, params.spread_pct,
        params.allow_short,
        params.position_sizing, params.risk_pct_per_trade,
    )

    if not trades:
        return BacktestResult(equity_curve=equity.tolist())

    ann = params.annualization

    # ── returns ───────────────────────────────────────────────────────────
    daily_ret = np.diff(equity) / (equity[:-1] + 1e-10)
    total_ret = (equity[-1] / equity[0] - 1) * 100
    n_bars = len(close)
    years  = max(n_bars / ann, 1 / ann)
    cagr   = ((equity[-1] / equity[0]) ** (1 / years) - 1) * 100

    # ── risk ──────────────────────────────────────────────────────────────
    rf = 0.05 / ann
    excess  = daily_ret - rf
    sharpe  = float(np.mean(excess) / (np.std(excess)  + 1e-10) * np.sqrt(ann))
    downside = daily_ret[daily_ret < rf]
    sortino = float(np.mean(excess) / (np.std(downside) + 1e-10) * np.sqrt(ann))

    roll_max  = np.maximum.accumulate(equity)
    drawdowns = (equity - roll_max) / (roll_max + 1e-10) * 100
    max_dd    = float(np.min(drawdowns))
    calmar    = cagr / (abs(max_dd) + 1e-10)

    # ── trade stats ───────────────────────────────────────────────────────
    rets   = [t["return_pct"] for t in trades]
    wins   = [r for r in rets if r >  0]
    losses = [r for r in rets if r <= 0]

    win_rate     = len(wins) / len(trades) * 100
    gross_win    = sum(wins)         if wins   else 0.0
    gross_loss   = abs(sum(losses))  if losses else 1e-10
    profit_factor = gross_win / gross_loss
    avg_trade    = float(np.mean(rets))

    avg_win  = float(np.mean(wins))          if wins   else 0.0
    avg_loss = float(np.mean([abs(l) for l in losses])) if losses else 0.0
    expectancy = avg_win * (win_rate / 100) - avg_loss * (1 - win_rate / 100)

    # ── institutional metrics ─────────────────────────────────────────────
    ulcer    = _ulcer_index(equity)
    recovery = abs(total_ret) / (abs(max_dd) + 1e-10)
    max_cl   = _max_consecutive_losses(rets)
    avg_bars = float(np.mean([t["bars_held"] for t in trades])) if trades else 0.0
    exposure = float(np.sum(pos_mask)) / n_bars * 100
    r2       = _r_squared(equity)
    mc_p5, mc_p95 = _monte_carlo_sharpe(rets, n_sim=200, annualization=ann)

    return BacktestResult(
        total_return_pct=round(total_ret, 2),
        cagr_pct=round(cagr, 2),
        sharpe_ratio=round(sharpe, 3),
        sortino_ratio=round(sortino, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 1),
        profit_factor=round(profit_factor, 3),
        n_trades=len(trades),
        avg_trade_pct=round(avg_trade, 3),
        calmar_ratio=round(calmar, 3),
        ulcer_index=round(ulcer, 3),
        recovery_factor=round(recovery, 3),
        expectancy_pct=round(expectancy, 4),
        max_consecutive_losses=max_cl,
        avg_bars_in_trade=round(avg_bars, 1),
        exposure_pct=round(exposure, 1),
        r_squared=round(r2, 4),
        mc_sharpe_p5=mc_p5,
        mc_sharpe_p95=mc_p95,
        equity_curve=equity.tolist(),
    )


# ---------------------------------------------------------------------------
# Signal generators
# ---------------------------------------------------------------------------

def compute_signals_from_params(
    ohlcv: pd.DataFrame,
    fast_ma: int = 20,
    slow_ma: int = 50,
    rsi_period: int = 14,
    rsi_buy: float = 35.0,
    rsi_sell: float = 65.0,
    use_volume: bool = True,
    **_kwargs,
) -> pd.Series:
    """SMA crossover + RSI + volume confirmation."""
    close  = ohlcv["Close"].astype(float)
    volume = ohlcv.get("Volume", pd.Series(1, index=ohlcv.index)).astype(float)

    sma_fast = close.rolling(fast_ma, min_periods=fast_ma).mean()
    sma_slow = close.rolling(slow_ma, min_periods=slow_ma).mean()
    trend = np.where(sma_fast > sma_slow, 1, -1)

    delta    = close.diff()
    avg_gain = delta.clip(lower=0).ewm(span=rsi_period, adjust=False).mean()
    avg_loss = (-delta).clip(lower=0).ewm(span=rsi_period, adjust=False).mean()
    rsi      = 100 - 100 / (1 + avg_gain / (avg_loss + 1e-10))
    rsi_bull = (rsi < rsi_buy).astype(int)
    rsi_bear = (rsi > rsi_sell).astype(int)

    vol_ma      = volume.rolling(20, min_periods=5).mean()
    vol_confirm = (volume > vol_ma).astype(int) if use_volume else pd.Series(1, index=ohlcv.index)

    raw = np.where(
        (trend == 1) & (rsi_bull == 1) & (vol_confirm == 1), 1,
        np.where((trend == -1) & (rsi_bear == 1) & (vol_confirm == 1), -1, 0)
    )
    return pd.Series(raw, index=ohlcv.index, dtype=int)


def compute_breakout_signals(
    ohlcv: pd.DataFrame,
    lookback_n: int = 20,
    atr_period: int = 14,
    atr_mult: float = 1.0,
    **_kwargs,
) -> pd.Series:
    """N-bar high/low channel breakout with ATR expansion filter."""
    high  = ohlcv["High"].astype(float)
    low   = ohlcv["Low"].astype(float)
    close = ohlcv["Close"].astype(float)

    rolling_high = high.shift(1).rolling(lookback_n).max()
    rolling_low  = low.shift(1).rolling(lookback_n).min()

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr     = tr.ewm(span=atr_period, adjust=False).mean()
    atr_avg = atr.rolling(atr_period).mean().shift(1)

    atr_filter    = atr > atr_mult * atr_avg
    breakout_up   = (close > rolling_high) & atr_filter
    breakout_down = (close < rolling_low)  & atr_filter

    raw = np.where(breakout_up, 1, np.where(breakout_down, -1, 0))
    return pd.Series(raw, index=ohlcv.index, dtype=int)


def compute_mean_reversion_signals(
    ohlcv: pd.DataFrame,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    **_kwargs,
) -> pd.Series:
    """Bollinger Band extremes + RSI confirmation for mean reversion."""
    close = ohlcv["Close"].astype(float)

    sma   = close.rolling(bb_period, min_periods=bb_period).mean()
    std   = close.rolling(bb_period, min_periods=bb_period).std()
    upper = sma + bb_std * std
    lower = sma - bb_std * std

    delta    = close.diff()
    avg_gain = delta.clip(lower=0).ewm(span=rsi_period, adjust=False).mean()
    avg_loss = (-delta).clip(lower=0).ewm(span=rsi_period, adjust=False).mean()
    rsi      = 100 - 100 / (1 + avg_gain / (avg_loss + 1e-10))

    long_signal  = (close < lower) & (rsi < rsi_oversold)
    short_signal = (close > upper) & (rsi > rsi_overbought)

    raw = np.where(long_signal, 1, np.where(short_signal, -1, 0))
    return pd.Series(raw, index=ohlcv.index, dtype=int)


# ---------------------------------------------------------------------------
# Strategy router
# ---------------------------------------------------------------------------

STRATEGY_COMPUTE_FN = {
    "sma_rsi":        compute_signals_from_params,
    "breakout":       compute_breakout_signals,
    "mean_reversion": compute_mean_reversion_signals,
}


def get_signal_fn(strategy: str):
    return STRATEGY_COMPUTE_FN.get(strategy, compute_signals_from_params)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import yfinance as yf

    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    df  = yf.download(sym, period="2y", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        print(json.dumps({"error": f"No data for {sym}"}))
        sys.exit(1)
    sig    = compute_signals_from_params(df)
    result = run_backtest(df, sig)
    out    = result.to_dict()
    out["symbol"] = sym
    print(json.dumps(out, indent=2))
