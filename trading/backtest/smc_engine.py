"""
SMC (Smart Money Concepts) engine — Python implementation matching the PineScript strategy.
Processes OHLCV bars and generates trading signals with full SMC analysis.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


# Default parameters matching PineScript strategy inputs
DEFAULT_PARAMS = {
    # Market Structure
    "swingLen": 5,
    "structureLen": 50,
    # Order Blocks
    "obMaxAge": 100,
    "obMitigateBody": True,
    "obMaxCount": 10,
    # Fair Value Gaps
    "fvgEnabled": True,
    "fvgMinSize": 0.5,
    "fvgMaxAge": 50,
    # Liquidity
    "liqEnabled": True,
    "eqTolerance": 0.1,
    "liqLookback": 20,
    # Premium / Discount
    "pdLookback": 50,
    # Higher Timeframe
    "htfBars": 16,  # 4H = 16 x 15min bars
    "htfSwingLen": 5,
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
    "maxDailyTrades": 3,
    # Simulation
    "slippage_ticks": 2,
    "tick_size": 0.25,
    "commission": 0.62,
    "point_value": 2.0,
}


@dataclass
class OrderBlock:
    top: float
    bot: float
    bar_idx: int
    direction: int  # 1=bullish, -1=bearish
    active: bool = True


@dataclass
class FairValueGap:
    top: float
    bot: float
    bar_idx: int
    direction: int  # 1=bullish, -1=bearish
    active: bool = True


@dataclass
class Trade:
    entry_bar: int
    entry_price: float
    direction: int  # 1=long, -1=short
    stop_loss: float
    take_profit: float
    sl_distance: float
    exit_bar: int = -1
    exit_price: float = 0.0
    pnl: float = 0.0
    r_multiple: float = 0.0
    exit_reason: str = ""


@dataclass
class SMCState:
    """Running state for the SMC engine."""
    # Swing points
    last_swing_high: float = np.nan
    last_swing_low: float = np.nan
    prev_swing_high: float = np.nan
    prev_swing_low: float = np.nan
    last_sw_high_bar: int = -1
    last_sw_low_bar: int = -1

    # Trend
    trend: int = 0  # 1=bullish, -1=bearish, 0=neutral

    # Structure breaks (per bar)
    bos_up: bool = False
    bos_dn: bool = False
    choch_up: bool = False
    choch_dn: bool = False

    # Order Blocks
    order_blocks: list = field(default_factory=list)

    # Fair Value Gaps
    fvgs: list = field(default_factory=list)

    # Liquidity sweeps (per bar)
    bull_sweep: bool = False
    bear_sweep: bool = False

    # HTF
    htf_trend: int = 0
    htf_last_sw_high: float = np.nan
    htf_last_sw_low: float = np.nan

    # ATR
    atr: float = 0.0

    # Position tracking
    position: int = 0  # 1=long, -1=short, 0=flat
    active_trade: Trade = None
    daily_trade_count: int = 0
    current_date: object = None

    # Trail tracking
    trail_activated: bool = False
    trail_stop: float = np.nan


class SMCEngine:
    """Processes OHLCV data bar-by-bar applying SMC logic."""

    def __init__(self, params: dict = None):
        self.p = {**DEFAULT_PARAMS, **(params or {})}
        self.state = SMCState()
        self.trades: list[Trade] = []
        self._highs = []
        self._lows = []
        self._closes = []
        self._opens = []
        self._timestamps = []
        self._bar_idx = 0

    def reset(self):
        """Reset engine state for a new run."""
        self.state = SMCState()
        self.trades = []
        self._highs = []
        self._lows = []
        self._closes = []
        self._opens = []
        self._timestamps = []
        self._bar_idx = 0

    def process_bar(self, timestamp, o: float, h: float, l: float, c: float) -> dict:
        """
        Process a single OHLCV bar. Returns signal info dict.
        """
        self._timestamps.append(timestamp)
        self._opens.append(o)
        self._highs.append(h)
        self._lows.append(l)
        self._closes.append(c)
        idx = self._bar_idx
        s = self.state

        # Reset per-bar signals
        s.bos_up = s.bos_dn = s.choch_up = s.choch_dn = False
        s.bull_sweep = s.bear_sweep = False

        # Daily trade counter reset
        bar_date = timestamp.date() if hasattr(timestamp, 'date') else None
        if bar_date and bar_date != s.current_date:
            s.daily_trade_count = 0
            s.current_date = bar_date

        # Update ATR
        self._update_atr(idx)

        # Session filter
        in_session = self._in_session(timestamp)
        can_trade = in_session and s.daily_trade_count < self.p["maxDailyTrades"]

        # Detect swing points
        self._detect_swings(idx)

        # Market structure (BOS/CHoCH)
        self._detect_structure(idx, c)

        # Order blocks
        self._detect_order_blocks(idx)
        self._mitigate_order_blocks(idx, h, l, c)

        # Fair value gaps
        self._detect_fvgs(idx)
        self._fill_fvgs(idx, h, l)

        # Liquidity sweeps
        self._detect_liquidity_sweeps(idx)

        # Premium/Discount zones
        in_premium, in_discount = self._premium_discount(idx)

        # HTF bias
        self._update_htf_bias(idx)

        # Check for exit on active position
        signal = {"action": "none", "bar": idx}
        if s.active_trade is not None:
            exit_signal = self._check_exit(idx, h, l, c)
            if exit_signal:
                signal = exit_signal

        # Entry logic (only if flat and can trade)
        if s.position == 0 and can_trade:
            entry = self._check_entry(idx, o, h, l, c, in_premium, in_discount)
            if entry:
                signal = entry

        self._bar_idx += 1
        return signal

    def _update_atr(self, idx: int):
        """Calculate ATR using exponential moving average."""
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
            # Simple average until we have enough bars
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

    def _in_session(self, timestamp) -> bool:
        if not self.p["sessEnabled"]:
            return True
        if not hasattr(timestamp, 'hour'):
            return True
        t = timestamp.hour * 60 + timestamp.minute
        start = self.p["sessStartHour"] * 60 + self.p["sessStartMin"]
        end = self.p["sessEndHour"] * 60 + self.p["sessEndMin"]
        return start <= t < end

    def _detect_swings(self, idx: int):
        """Detect pivot highs and lows."""
        swing_len = self.p["swingLen"]
        if idx < swing_len * 2:
            return

        pivot_idx = idx - swing_len

        # Check pivot high
        is_pivot_high = True
        pivot_val = self._highs[pivot_idx]
        for i in range(pivot_idx - swing_len, pivot_idx + swing_len + 1):
            if i == pivot_idx or i < 0 or i >= len(self._highs):
                continue
            if self._highs[i] > pivot_val:
                is_pivot_high = False
                break

        if is_pivot_high:
            self.state.prev_swing_high = self.state.last_swing_high
            self.state.last_swing_high = pivot_val
            self.state.last_sw_high_bar = pivot_idx

        # Check pivot low
        is_pivot_low = True
        pivot_val = self._lows[pivot_idx]
        for i in range(pivot_idx - swing_len, pivot_idx + swing_len + 1):
            if i == pivot_idx or i < 0 or i >= len(self._lows):
                continue
            if self._lows[i] < pivot_val:
                is_pivot_low = False
                break

        if is_pivot_low:
            self.state.prev_swing_low = self.state.last_swing_low
            self.state.last_swing_low = pivot_val
            self.state.last_sw_low_bar = pivot_idx

    def _detect_structure(self, idx: int, close: float):
        """Detect BOS and CHoCH."""
        s = self.state
        if np.isnan(s.last_swing_high) or np.isnan(s.last_swing_low):
            return

        # Bullish BOS: close above swing high in uptrend
        if close > s.last_swing_high and s.trend >= 0:
            s.bos_up = True
            s.trend = 1

        # Bearish BOS: close below swing low in downtrend
        if close < s.last_swing_low and s.trend <= 0:
            s.bos_dn = True
            s.trend = -1

        # Bullish CHoCH: close above swing high in DOWNTREND
        if close > s.last_swing_high and s.trend == -1:
            s.choch_up = True
            s.trend = 1

        # Bearish CHoCH: close below swing low in UPTREND
        if close < s.last_swing_low and s.trend == 1:
            s.choch_dn = True
            s.trend = -1

    def _detect_order_blocks(self, idx: int):
        """Detect order blocks on BOS/CHoCH."""
        s = self.state

        # Bullish OB: last bearish candle before bullish break
        if s.bos_up or s.choch_up:
            for i in range(1, min(11, idx + 1)):
                if self._closes[idx - i] < self._opens[idx - i]:
                    ob = OrderBlock(
                        top=self._highs[idx - i],
                        bot=self._lows[idx - i],
                        bar_idx=idx - i,
                        direction=1,
                    )
                    if len(s.order_blocks) >= self.p["obMaxCount"]:
                        s.order_blocks.pop(0)
                    s.order_blocks.append(ob)
                    break

        # Bearish OB: last bullish candle before bearish break
        if s.bos_dn or s.choch_dn:
            for i in range(1, min(11, idx + 1)):
                if self._closes[idx - i] > self._opens[idx - i]:
                    ob = OrderBlock(
                        top=self._highs[idx - i],
                        bot=self._lows[idx - i],
                        bar_idx=idx - i,
                        direction=-1,
                    )
                    if len(s.order_blocks) >= self.p["obMaxCount"]:
                        s.order_blocks.pop(0)
                    s.order_blocks.append(ob)
                    break

    def _mitigate_order_blocks(self, idx: int, h: float, l: float, c: float):
        """Mitigate order blocks when price trades through them."""
        for ob in self.state.order_blocks:
            if not ob.active:
                continue
            age = idx - ob.bar_idx
            if age > self.p["obMaxAge"]:
                ob.active = False
                continue
            if ob.direction == 1:
                if self.p["obMitigateBody"]:
                    if c < ob.bot:
                        ob.active = False
                else:
                    if l < ob.bot:
                        ob.active = False
            elif ob.direction == -1:
                if self.p["obMitigateBody"]:
                    if c > ob.top:
                        ob.active = False
                else:
                    if h > ob.top:
                        ob.active = False

    def _detect_fvgs(self, idx: int):
        """Detect fair value gaps."""
        if not self.p["fvgEnabled"] or idx < 2:
            return
        s = self.state

        # Bullish FVG: current low > 2 bars ago high
        if self._lows[idx] > self._highs[idx - 2]:
            gap = self._lows[idx] - self._highs[idx - 2]
            if gap >= self.p["fvgMinSize"]:
                fvg = FairValueGap(
                    top=self._lows[idx],
                    bot=self._highs[idx - 2],
                    bar_idx=idx - 1,
                    direction=1,
                )
                s.fvgs.append(fvg)

        # Bearish FVG: current high < 2 bars ago low
        if self._highs[idx] < self._lows[idx - 2]:
            gap = self._lows[idx - 2] - self._highs[idx]
            if gap >= self.p["fvgMinSize"]:
                fvg = FairValueGap(
                    top=self._lows[idx - 2],
                    bot=self._highs[idx],
                    bar_idx=idx - 1,
                    direction=-1,
                )
                s.fvgs.append(fvg)

    def _fill_fvgs(self, idx: int, h: float, l: float):
        """Fill or expire FVGs."""
        for fvg in self.state.fvgs:
            if not fvg.active:
                continue
            age = idx - fvg.bar_idx
            if age > self.p["fvgMaxAge"]:
                fvg.active = False
                continue
            if fvg.direction == 1 and l <= fvg.bot:
                fvg.active = False
            elif fvg.direction == -1 and h >= fvg.top:
                fvg.active = False

    def _detect_liquidity_sweeps(self, idx: int):
        """Detect liquidity sweeps on equal highs/lows."""
        if not self.p["liqEnabled"]:
            return
        s = self.state
        swing_len = self.p["swingLen"]

        if idx < swing_len * 2 + self.p["liqLookback"]:
            return

        # Check for pivot at current confirmation point
        pivot_idx = idx - swing_len

        # Check for equal highs and sweep
        pivot_high = self._highs[pivot_idx]
        is_ph = all(
            self._highs[j] <= pivot_high
            for j in range(pivot_idx - swing_len, pivot_idx + swing_len + 1)
            if j != pivot_idx and 0 <= j < len(self._highs)
        )

        if is_ph:
            for i in range(1, self.p["liqLookback"] + 1):
                check_idx = pivot_idx - swing_len - i
                if check_idx < 0:
                    break
                prev_high = self._highs[check_idx]
                tol = prev_high * self.p["eqTolerance"] / 100
                if abs(pivot_high - prev_high) <= tol:
                    eq_level = max(pivot_high, prev_high)
                    if self._highs[idx] > eq_level and self._closes[idx] < eq_level:
                        s.bear_sweep = True
                    break

        # Check for equal lows and sweep
        pivot_low = self._lows[pivot_idx]
        is_pl = all(
            self._lows[j] >= pivot_low
            for j in range(pivot_idx - swing_len, pivot_idx + swing_len + 1)
            if j != pivot_idx and 0 <= j < len(self._lows)
        )

        if is_pl:
            for i in range(1, self.p["liqLookback"] + 1):
                check_idx = pivot_idx - swing_len - i
                if check_idx < 0:
                    break
                prev_low = self._lows[check_idx]
                tol = prev_low * self.p["eqTolerance"] / 100
                if abs(pivot_low - prev_low) <= tol:
                    eq_level = min(pivot_low, prev_low)
                    if self._lows[idx] < eq_level and self._closes[idx] > eq_level:
                        s.bull_sweep = True
                    break

    def _premium_discount(self, idx: int) -> tuple:
        """Calculate premium/discount zones."""
        lookback = min(self.p["pdLookback"], idx + 1)
        if lookback < 2:
            return False, False

        range_high = max(self._highs[idx - lookback + 1:idx + 1])
        range_low = min(self._lows[idx - lookback + 1:idx + 1])
        eq = (range_high + range_low) / 2

        return self._closes[idx] > eq, self._closes[idx] < eq

    def _update_htf_bias(self, idx: int):
        """Simulate HTF bias using resampled bars."""
        htf_bars = self.p["htfBars"]
        htf_swing = self.p["htfSwingLen"]
        s = self.state

        if idx < htf_bars * (htf_swing * 2 + 1):
            return

        # Resample to HTF bars
        htf_highs = []
        htf_lows = []
        htf_closes = []

        num_htf = min(htf_swing * 2 + 1, (idx + 1) // htf_bars)
        for i in range(num_htf):
            end = idx - i * htf_bars
            start = max(0, end - htf_bars + 1)
            htf_highs.append(max(self._highs[start:end + 1]))
            htf_lows.append(min(self._lows[start:end + 1]))
            htf_closes.append(self._closes[end])

        htf_highs.reverse()
        htf_lows.reverse()
        htf_closes.reverse()

        if len(htf_highs) < htf_swing * 2 + 1:
            return

        # Check for HTF swing high/low at the middle point
        mid = htf_swing
        is_htf_sh = all(htf_highs[j] <= htf_highs[mid] for j in range(len(htf_highs)) if j != mid)
        is_htf_sl = all(htf_lows[j] >= htf_lows[mid] for j in range(len(htf_lows)) if j != mid)

        if is_htf_sh:
            s.htf_last_sw_high = htf_highs[mid]
        if is_htf_sl:
            s.htf_last_sw_low = htf_lows[mid]

        if not np.isnan(s.htf_last_sw_high) and not np.isnan(s.htf_last_sw_low):
            if htf_closes[-1] > s.htf_last_sw_high:
                s.htf_trend = 1
            if htf_closes[-1] < s.htf_last_sw_low:
                s.htf_trend = -1

    def _check_entry(self, idx: int, o: float, h: float, l: float, c: float,
                     in_premium: bool, in_discount: bool) -> dict | None:
        """Check entry conditions matching PineScript logic."""
        s = self.state
        p = self.p

        # Price in active bullish OB or FVG
        in_bull_ob = False
        ob_bot = 0.0
        for ob in s.order_blocks:
            if ob.active and ob.direction == 1 and l <= ob.top and c >= ob.bot:
                in_bull_ob = True
                ob_bot = ob.bot
                break

        in_bull_fvg = False
        fvg_bot = 0.0
        if p["fvgEnabled"]:
            for fvg in s.fvgs:
                if fvg.active and fvg.direction == 1 and l <= fvg.top and c >= fvg.bot:
                    in_bull_fvg = True
                    fvg_bot = fvg.bot
                    break

        in_bear_ob = False
        ob_top = 0.0
        for ob in s.order_blocks:
            if ob.active and ob.direction == -1 and h >= ob.bot and c <= ob.top:
                in_bear_ob = True
                ob_top = ob.top
                break

        in_bear_fvg = False
        fvg_top = 0.0
        if p["fvgEnabled"]:
            for fvg in s.fvgs:
                if fvg.active and fvg.direction == -1 and h >= fvg.bot and c <= fvg.top:
                    in_bear_fvg = True
                    fvg_top = fvg.top
                    break

        # Long conditions
        long_cond = (
            s.htf_trend >= 1 and        # 1. HTF bullish
            s.trend == 1 and             # 2. Structure bullish
            in_discount and              # 3. Price in discount
            (in_bull_ob or in_bull_fvg)  # 4. At OB or FVG
        )

        # Short conditions
        short_cond = (
            s.htf_trend <= -1 and        # 1. HTF bearish
            s.trend == -1 and            # 2. Structure bearish
            in_premium and               # 3. Price in premium
            (in_bear_ob or in_bear_fvg)  # 4. At OB or FVG
        )

        if long_cond:
            ref_bot = ob_bot if in_bull_ob else fvg_bot
            sl_dist = max(c - ref_bot, s.atr * p["atrSlMult"])
            sl = c - sl_dist
            tp = c + sl_dist * p["rrRatio"]

            # Apply slippage
            entry_price = c + p["slippage_ticks"] * p["tick_size"]

            trade = Trade(
                entry_bar=idx,
                entry_price=entry_price,
                direction=1,
                stop_loss=sl,
                take_profit=tp,
                sl_distance=sl_dist,
            )
            s.active_trade = trade
            s.position = 1
            s.daily_trade_count += 1
            s.trail_activated = False
            s.trail_stop = np.nan

            return {"action": "long_entry", "bar": idx, "price": entry_price,
                    "sl": sl, "tp": tp}

        if short_cond:
            ref_top = ob_top if in_bear_ob else fvg_top
            sl_dist = max(ref_top - c, s.atr * p["atrSlMult"])
            sl = c + sl_dist
            tp = c - sl_dist * p["rrRatio"]

            entry_price = c - p["slippage_ticks"] * p["tick_size"]

            trade = Trade(
                entry_bar=idx,
                entry_price=entry_price,
                direction=-1,
                stop_loss=sl,
                take_profit=tp,
                sl_distance=sl_dist,
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
        """Check exit conditions for active position."""
        s = self.state
        p = self.p
        trade = s.active_trade

        exit_price = None
        exit_reason = ""

        if trade.direction == 1:  # Long
            # Check stop loss
            if l <= trade.stop_loss:
                exit_price = trade.stop_loss - p["slippage_ticks"] * p["tick_size"]
                exit_reason = "stop_loss"
            # Check take profit
            elif h >= trade.take_profit:
                exit_price = trade.take_profit - p["slippage_ticks"] * p["tick_size"]
                exit_reason = "take_profit"
            # Trailing stop
            elif p["useTrailing"] and trade.sl_distance > 0:
                r_achieved = (h - trade.entry_price) / trade.sl_distance
                if r_achieved >= p["trailAfterR"]:
                    s.trail_activated = True
                if s.trail_activated:
                    new_trail = h - trade.sl_distance
                    if np.isnan(s.trail_stop) or new_trail > s.trail_stop:
                        s.trail_stop = new_trail
                    if l <= s.trail_stop:
                        exit_price = s.trail_stop - p["slippage_ticks"] * p["tick_size"]
                        exit_reason = "trailing_stop"

        elif trade.direction == -1:  # Short
            if h >= trade.stop_loss:
                exit_price = trade.stop_loss + p["slippage_ticks"] * p["tick_size"]
                exit_reason = "stop_loss"
            elif l <= trade.take_profit:
                exit_price = trade.take_profit + p["slippage_ticks"] * p["tick_size"]
                exit_reason = "take_profit"
            elif p["useTrailing"] and trade.sl_distance > 0:
                r_achieved = (trade.entry_price - l) / trade.sl_distance
                if r_achieved >= p["trailAfterR"]:
                    s.trail_activated = True
                if s.trail_activated:
                    new_trail = l + trade.sl_distance
                    if np.isnan(s.trail_stop) or new_trail < s.trail_stop:
                        s.trail_stop = new_trail
                    if h >= s.trail_stop:
                        exit_price = s.trail_stop + p["slippage_ticks"] * p["tick_size"]
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

            return {"action": f"{exit_reason}_exit", "bar": idx,
                    "price": exit_price, "pnl": pnl, "r_multiple": r_mult}

        return None
