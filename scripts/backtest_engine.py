"""
backtest_engine.py — Vectorized signal-based backtester.

Accepts OHLCV data + a signal Series (values: +1 long, -1 short, 0 flat),
simulates trades with stop-loss / take-profit, and returns performance metrics.

All computation is NumPy/pandas vectorized — no per-bar Python loops.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class BacktestParams:
    stop_loss_pct: float = 0.05       # 5 % stop below entry
    take_profit_pct: float = 0.10     # 10 % target above entry
    capital: float = 10_000.0
    commission_pct: float = 0.001     # 0.1 % per trade (one-way)
    allow_short: bool = True


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
    equity_curve: list = field(default_factory=list)  # list[float] for JSON serialisation

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("equity_curve")  # strip before caching — re-attach if needed
        return d


def _compute_equity(
    close: np.ndarray,
    signals: np.ndarray,
    stop_pct: float,
    tp_pct: float,
    capital: float,
    commission: float,
    allow_short: bool,
) -> tuple[np.ndarray, list[dict]]:
    """Simulate trades bar-by-bar (signals are OPEN-of-next-bar entry).
    Returns (equity_curve, trade_list).
    """
    n = len(close)
    equity = np.full(n, capital, dtype=float)
    cash = capital
    position = 0          # +1 long, -1 short, 0 flat
    entry_price = 0.0
    trades = []

    for i in range(1, n):
        prev_sig = signals[i - 1]
        price = close[i]

        # ── exit open position ────────────────────────────────────────────
        if position != 0:
            pnl_pct = (price - entry_price) / entry_price * position
            hit_stop = pnl_pct <= -stop_pct
            hit_tp   = pnl_pct >=  tp_pct

            if hit_stop or hit_tp or (prev_sig == 0) or (prev_sig == -position):
                exit_price = price
                trade_ret = (exit_price - entry_price) / entry_price * position
                trade_ret -= commission * 2
                cash *= (1 + trade_ret)
                trades.append({"entry": entry_price, "exit": exit_price,
                               "direction": position, "return_pct": trade_ret * 100})
                position = 0

        # ── enter new position ────────────────────────────────────────────
        if position == 0 and prev_sig != 0:
            if prev_sig == 1 or allow_short:
                position = int(prev_sig)
                entry_price = price
                cash -= commission * cash  # entry commission

        equity[i] = cash

    return equity, trades


def run_backtest(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    params: Optional[BacktestParams] = None,
) -> BacktestResult:
    """
    ohlcv: DataFrame with at least a 'Close' column, DatetimeIndex.
    signals: Series aligned to ohlcv, values +1/0/-1.
    Returns BacktestResult with all metrics filled.
    """
    if params is None:
        params = BacktestParams()

    close = ohlcv["Close"].values.astype(float)
    sig = signals.reindex(ohlcv.index).fillna(0).values.astype(int)

    if len(close) < 10:
        return BacktestResult()

    equity, trades = _compute_equity(
        close, sig,
        params.stop_loss_pct, params.take_profit_pct,
        params.capital, params.commission_pct, params.allow_short,
    )

    if not trades:
        return BacktestResult(equity_curve=equity.tolist())

    # ── returns ───────────────────────────────────────────────────────────
    daily_ret = np.diff(equity) / equity[:-1]
    total_ret = (equity[-1] / equity[0] - 1) * 100
    n_days = len(close)
    years = max(n_days / 252, 1 / 252)
    cagr = ((equity[-1] / equity[0]) ** (1 / years) - 1) * 100

    # ── risk ──────────────────────────────────────────────────────────────
    rf = 0.05 / 252  # risk-free daily
    excess = daily_ret - rf
    sharpe = float(np.mean(excess) / (np.std(excess) + 1e-10) * np.sqrt(252))
    downside = daily_ret[daily_ret < 0]
    sortino = float(np.mean(excess) / (np.std(downside) + 1e-10) * np.sqrt(252))

    roll_max = np.maximum.accumulate(equity)
    drawdowns = (equity - roll_max) / (roll_max + 1e-10) * 100
    max_dd = float(np.min(drawdowns))

    calmar = cagr / (abs(max_dd) + 1e-10)

    # ── trade stats ───────────────────────────────────────────────────────
    rets = [t["return_pct"] for t in trades]
    wins  = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    win_rate = len(wins) / len(trades) * 100
    gross_win  = sum(wins) or 0.0
    gross_loss = abs(sum(losses)) or 1e-10
    profit_factor = gross_win / gross_loss
    avg_trade = float(np.mean(rets))

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
        equity_curve=equity.tolist(),
    )


def compute_signals_from_params(
    ohlcv: pd.DataFrame,
    fast_ma: int = 20,
    slow_ma: int = 50,
    rsi_period: int = 14,
    rsi_buy: float = 35.0,
    rsi_sell: float = 65.0,
    use_volume: bool = True,
) -> pd.Series:
    """
    Pure price/volume signal generator — fast vectorized.
    Returns pd.Series of +1 (long), -1 (short), 0 (flat).
    """
    close = ohlcv["Close"].astype(float)
    volume = ohlcv.get("Volume", pd.Series(1, index=ohlcv.index)).astype(float)

    # SMA crossover
    sma_fast = close.rolling(fast_ma, min_periods=fast_ma).mean()
    sma_slow = close.rolling(slow_ma, min_periods=slow_ma).mean()
    trend = np.where(sma_fast > sma_slow, 1, -1)

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(span=rsi_period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - 100 / (1 + rs)

    rsi_bull = (rsi < rsi_buy).astype(int)
    rsi_bear = (rsi > rsi_sell).astype(int)

    # Volume confirmation (optional)
    vol_ma = volume.rolling(20, min_periods=5).mean()
    vol_confirm = (volume > vol_ma).astype(int) if use_volume else pd.Series(1, index=ohlcv.index)

    # Composite: trend + RSI agreement
    raw = np.where(
        (trend == 1) & (rsi_bull == 1) & (vol_confirm == 1), 1,
        np.where((trend == -1) & (rsi_bear == 1) & (vol_confirm == 1), -1, 0)
    )

    return pd.Series(raw, index=ohlcv.index, dtype=int)


if __name__ == "__main__":
    import sys, yfinance as yf
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    df = yf.download(sym, period="2y", progress=False)
    if df.empty:
        print(json.dumps({"error": f"No data for {sym}"}))
        sys.exit(1)
    sig = compute_signals_from_params(df)
    result = run_backtest(df, sig)
    out = result.to_dict()
    out["symbol"] = sym
    print(json.dumps(out, indent=2))
