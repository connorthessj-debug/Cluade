"""
Connors RSI2 Mean Reversion engine — Python implementation.
Processes OHLCV bars and generates trading signals using RSI(2) + MA trend filter.

Strategy:
  Long:  close > MA(200) AND RSI(2) < oversold threshold
  Short: close < MA(200) AND RSI(2) > overbought threshold
  Exit long:  close crosses above SMA(5) OR SL/TP/trailing
  Exit short: close crosses below SMA(5) OR SL/TP/trailing
"""

import numpy as np
from dataclasses import dataclass, field
from .smc_engine import Trade  # Reuse Trade dataclass


RSI2_DEFAULT_PARAMS = {
    # Trend Filter
    "maLen": 200,
    "maType": "SMA",       # SMA or EMA
    # RSI
    "rsiLen": 2,
    "rsiOversold": 10,
    "rsiOverbought": 90,
    # Exit
    "exitMaLen": 5,
    # Risk Management
    "atrPeriod": 14,
    "atrSlMult": 1.5,
    "rrRatio": 2.0,
    "useTrailing": True,
    "trailAfterR": 1.0,
    # Session Filter
    "sessEnabled": True,
    "sessStartHour": 9,
    "sessStartMin": 30,
    "sessEndHour": 16,
    "sessEndMin": 0,
    "maxDailyTrades": 5,
    # Simulation
    "slippage_ticks": 2,
    "tick_size": 0.25,
    "commission": 0.62,
    "point_value": 2.0,
    "spread": 0.0,
    "min_volume": 0,
    # FTMO
    "account_balance": 10000,
    "max_daily_loss_pct": 5.0,
    "max_total_dd_pct": 10.0,
}


@dataclass
class RSI2State:
    """Running state for the RSI2 engine."""
    # Indicators
    ma: float = np.nan
    rsi: float = 50.0
    exit_ma: float = np.nan
    prev_exit_ma: float = np.nan
    atr: float = 0.0

    # RSI internals
    avg_gain: float = 0.0
    avg_loss: float = 0.0

    # EMA state (for maType=EMA)
    ema: float = np.nan

    # Position tracking
    position: int = 0
    active_trade: Trade = None
    daily_trade_count: int = 0
    current_date: object = None

    # Trailing
    trail_activated: bool = False
    trail_stop: float = np.nan

    # FTMO tracking
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    peak_equity: float = 0.0
    ftmo_breached: bool = False
    daily_loss_breached: bool = False


class RSI2Engine:
    """Processes OHLCV data bar-by-bar applying RSI2 mean reversion logic."""

    def __init__(self, params: dict = None):
        self.p = {**RSI2_DEFAULT_PARAMS, **(params or {})}
        self.state = RSI2State()
        self.state.peak_equity = self.p["account_balance"]
        self.trades: list[Trade] = []
        self._opens = []
        self._highs = []
        self._lows = []
        self._closes = []
        self._volumes = []
        self._timestamps = []
        self._bar_idx = 0
        self.skipped_trades = 0

    def _fill_cost(self) -> float:
        """Total per-side fill cost: half spread + slippage."""
        return self.p["spread"] / 2 + self.p["slippage_ticks"] * self.p["tick_size"]

    def reset(self):
        self.state = RSI2State()
        self.state.peak_equity = self.p["account_balance"]
        self.trades = []
        self._opens = []
        self._highs = []
        self._lows = []
        self._closes = []
        self._volumes = []
        self._timestamps = []
        self._bar_idx = 0
        self.skipped_trades = 0

    def process_bar(self, timestamp, o: float, h: float, l: float, c: float,
                    volume: float = 0.0) -> dict:
        self._timestamps.append(timestamp)
        self._opens.append(o)
        self._highs.append(h)
        self._lows.append(l)
        self._closes.append(c)
        self._volumes.append(volume)
        idx = self._bar_idx
        s = self.state

        # Daily reset
        bar_date = timestamp.date() if hasattr(timestamp, 'date') else None
        if bar_date and bar_date != s.current_date:
            s.daily_trade_count = 0
            s.daily_pnl = 0.0
            s.daily_loss_breached = False
            s.current_date = bar_date

        # FTMO total drawdown check
        if s.ftmo_breached:
            self._bar_idx += 1
            return {"action": "none", "bar": idx, "reason": "ftmo_breached"}

        # Update indicators
        self._update_atr(idx)
        self._update_ma(idx)
        self._update_rsi(idx)
        self._update_exit_ma(idx)

        # Session filter
        in_session = self._in_session(timestamp)
        can_trade = (in_session
                     and s.daily_trade_count < self.p["maxDailyTrades"]
                     and not s.daily_loss_breached)

        # Check exit on active position
        signal = {"action": "none", "bar": idx}
        if s.active_trade is not None:
            exit_signal = self._check_exit(idx, h, l, c)
            if exit_signal:
                signal = exit_signal

        # Entry logic
        if s.position == 0 and can_trade and idx >= self.p["maLen"]:
            entry = self._check_entry(idx, o, h, l, c)
            if entry:
                signal = entry

        self._bar_idx += 1
        return signal

    def _update_atr(self, idx: int):
        if idx < 1:
            self.state.atr = self._highs[idx] - self._lows[idx]
            return
        tr = max(
            self._highs[idx] - self._lows[idx],
            abs(self._highs[idx] - self._closes[idx - 1]),
            abs(self._lows[idx] - self._closes[idx - 1]),
        )
        period = self.p["atrPeriod"]
        if idx < period:
            trs = []
            for i in range(max(0, idx - period + 1), idx + 1):
                if i == 0:
                    trs.append(self._highs[i] - self._lows[i])
                else:
                    trs.append(max(
                        self._highs[i] - self._lows[i],
                        abs(self._highs[i] - self._closes[i - 1]),
                        abs(self._lows[i] - self._closes[i - 1]),
                    ))
            self.state.atr = np.mean(trs)
        else:
            alpha = 1.0 / period
            self.state.atr = alpha * tr + (1 - alpha) * self.state.atr

    def _update_ma(self, idx: int):
        ma_len = self.p["maLen"]
        if idx < ma_len - 1:
            self.state.ma = np.nan
            return
        if self.p["maType"] == "EMA":
            if np.isnan(self.state.ema):
                self.state.ema = np.mean(self._closes[idx - ma_len + 1:idx + 1])
            else:
                alpha = 2.0 / (ma_len + 1)
                self.state.ema = alpha * self._closes[idx] + (1 - alpha) * self.state.ema
            self.state.ma = self.state.ema
        else:
            self.state.ma = np.mean(self._closes[idx - ma_len + 1:idx + 1])

    def _update_rsi(self, idx: int):
        rsi_len = self.p["rsiLen"]
        if idx < 1:
            self.state.rsi = 50.0
            return

        change = self._closes[idx] - self._closes[idx - 1]
        gain = max(change, 0)
        loss = max(-change, 0)

        s = self.state
        if idx < rsi_len + 1:
            # Accumulate for initial average
            if idx == rsi_len:
                total_gain = 0.0
                total_loss = 0.0
                for i in range(1, rsi_len + 1):
                    diff = self._closes[i] - self._closes[i - 1]
                    total_gain += max(diff, 0)
                    total_loss += max(-diff, 0)
                s.avg_gain = total_gain / rsi_len
                s.avg_loss = total_loss / rsi_len
            else:
                s.rsi = 50.0
                return
        else:
            s.avg_gain = (s.avg_gain * (rsi_len - 1) + gain) / rsi_len
            s.avg_loss = (s.avg_loss * (rsi_len - 1) + loss) / rsi_len

        if s.avg_loss == 0:
            s.rsi = 100.0
        else:
            rs = s.avg_gain / s.avg_loss
            s.rsi = 100.0 - (100.0 / (1.0 + rs))

    def _update_exit_ma(self, idx: int):
        exit_len = self.p["exitMaLen"]
        s = self.state
        s.prev_exit_ma = s.exit_ma
        if idx < exit_len - 1:
            s.exit_ma = np.nan
            return
        s.exit_ma = np.mean(self._closes[idx - exit_len + 1:idx + 1])

    def _in_session(self, timestamp) -> bool:
        if not self.p["sessEnabled"]:
            return True
        if not hasattr(timestamp, 'hour'):
            return True
        t = timestamp.hour * 60 + timestamp.minute
        start = self.p["sessStartHour"] * 60 + self.p["sessStartMin"]
        end = self.p["sessEndHour"] * 60 + self.p["sessEndMin"]
        return start <= t < end

    def _check_entry(self, idx: int, o: float, h: float, l: float, c: float) -> dict | None:
        s = self.state
        p = self.p

        # Volume filter
        min_vol = p.get("min_volume", 0)
        if min_vol > 0 and idx < len(self._volumes) and self._volumes[idx] < min_vol:
            self.skipped_trades += 1
            return None

        if np.isnan(s.ma):
            return None

        # Long: price above MA AND RSI oversold
        if c > s.ma and s.rsi < p["rsiOversold"]:
            sl_dist = max(s.atr * p["atrSlMult"], p["tick_size"])
            sl = c - sl_dist
            tp = c + sl_dist * p["rrRatio"]
            entry_price = c + self._fill_cost()

            trade = Trade(
                entry_bar=idx, entry_price=entry_price, direction=1,
                stop_loss=sl, take_profit=tp, sl_distance=sl_dist,
            )
            s.active_trade = trade
            s.position = 1
            s.daily_trade_count += 1
            s.trail_activated = False
            s.trail_stop = np.nan
            return {"action": "long_entry", "bar": idx, "price": entry_price,
                    "sl": sl, "tp": tp}

        # Short: price below MA AND RSI overbought
        if c < s.ma and s.rsi > p["rsiOverbought"]:
            sl_dist = max(s.atr * p["atrSlMult"], p["tick_size"])
            sl = c + sl_dist
            tp = c - sl_dist * p["rrRatio"]
            entry_price = c - self._fill_cost()

            trade = Trade(
                entry_bar=idx, entry_price=entry_price, direction=-1,
                stop_loss=sl, take_profit=tp, sl_distance=sl_dist,
            )
            s.active_trade = trade
            s.position = -1
            s.daily_trade_count += 1
            s.trail_activated = False
            s.trail_stop = np.nan
            return {"action": "short_entry", "bar": idx, "price": entry_price,
                    "sl": sl, "tp": tp}

        return None

    def _check_exit(self, idx: int, h: float, l: float, c: float) -> dict | None:
        s = self.state
        p = self.p
        trade = s.active_trade
        exit_price = None
        exit_reason = ""

        if trade.direction == 1:  # Long
            # SMA crossover exit: close crosses above exit MA
            if not np.isnan(s.exit_ma) and not np.isnan(s.prev_exit_ma):
                if c > s.exit_ma and self._closes[idx - 1] <= s.prev_exit_ma:
                    exit_price = c - self._fill_cost()
                    exit_reason = "sma_crossover"

            # Stop loss
            if exit_price is None and l <= trade.stop_loss:
                exit_price = trade.stop_loss - self._fill_cost()
                exit_reason = "stop_loss"
            # Take profit
            if exit_price is None and h >= trade.take_profit:
                exit_price = trade.take_profit - self._fill_cost()
                exit_reason = "take_profit"
            # Trailing stop
            if exit_price is None and p["useTrailing"] and trade.sl_distance > 0:
                r_achieved = (h - trade.entry_price) / trade.sl_distance
                if r_achieved >= p["trailAfterR"]:
                    s.trail_activated = True
                if s.trail_activated:
                    new_trail = h - trade.sl_distance
                    if np.isnan(s.trail_stop) or new_trail > s.trail_stop:
                        s.trail_stop = new_trail
                    if l <= s.trail_stop:
                        exit_price = s.trail_stop - self._fill_cost()
                        exit_reason = "trailing_stop"

        elif trade.direction == -1:  # Short
            # SMA crossover exit: close crosses below exit MA
            if not np.isnan(s.exit_ma) and not np.isnan(s.prev_exit_ma):
                if c < s.exit_ma and self._closes[idx - 1] >= s.prev_exit_ma:
                    exit_price = c + self._fill_cost()
                    exit_reason = "sma_crossover"

            if exit_price is None and h >= trade.stop_loss:
                exit_price = trade.stop_loss + self._fill_cost()
                exit_reason = "stop_loss"
            if exit_price is None and l <= trade.take_profit:
                exit_price = trade.take_profit + self._fill_cost()
                exit_reason = "take_profit"
            if exit_price is None and p["useTrailing"] and trade.sl_distance > 0:
                r_achieved = (trade.entry_price - l) / trade.sl_distance
                if r_achieved >= p["trailAfterR"]:
                    s.trail_activated = True
                if s.trail_activated:
                    new_trail = l + trade.sl_distance
                    if np.isnan(s.trail_stop) or new_trail < s.trail_stop:
                        s.trail_stop = new_trail
                    if h >= s.trail_stop:
                        exit_price = s.trail_stop + self._fill_cost()
                        exit_reason = "trailing_stop"

        if exit_price is not None:
            pnl_points = (exit_price - trade.entry_price) * trade.direction
            pnl = pnl_points * p["point_value"] - p["commission"]
            r_mult = pnl_points / trade.sl_distance if trade.sl_distance > 0 else 0

            trade.exit_bar = idx
            trade.exit_price = exit_price
            trade.pnl = pnl
            trade.r_multiple = r_mult
            trade.exit_reason = exit_reason

            self.trades.append(trade)
            s.active_trade = None
            s.position = 0
            s.trail_activated = False
            s.trail_stop = np.nan

            # FTMO tracking
            s.daily_pnl += pnl
            s.total_pnl += pnl
            balance = p["account_balance"]

            # Check daily loss limit
            if s.daily_pnl <= -(balance * p["max_daily_loss_pct"] / 100):
                s.daily_loss_breached = True

            # Check total drawdown
            current_equity = balance + s.total_pnl
            if current_equity > s.peak_equity:
                s.peak_equity = current_equity
            drawdown = s.peak_equity - current_equity
            if drawdown >= balance * p["max_total_dd_pct"] / 100:
                s.ftmo_breached = True

            return {"action": f"{exit_reason}_exit", "bar": idx,
                    "price": exit_price, "pnl": pnl, "r_multiple": r_mult}

        return None
