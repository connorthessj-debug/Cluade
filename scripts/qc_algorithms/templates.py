"""
QC Cloud algorithm code generators.

Each function returns a Python string that is uploaded to QC Cloud and
compiled/run there. Parameters are hardcoded (not get_parameter) since
these are one-shot cloud submissions.
"""

from datetime import datetime, timedelta


def _header(symbol: str, resolution: str, start: str, end: str,
            capital: int, allow_short: bool) -> str:
    return f"""\
# region imports
from AlgorithmImports import *
# endregion

SYMBOL      = "{symbol}"
RESOLUTION  = Resolution.{resolution}
START_DATE  = ({start.replace('-', ', ')})
END_DATE    = ({end.replace('-', ', ')})
CAPITAL     = {capital}
ALLOW_SHORT = {str(allow_short)}
"""


def _date_range(lookback_years: int = 4) -> tuple[str, str]:
    end   = datetime.utcnow()
    start = end - timedelta(days=lookback_years * 365)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def build_sma_rsi(
    symbol: str, resolution: str = "Daily",
    fast_ma: int = 20, slow_ma: int = 50,
    rsi_period: int = 14, rsi_buy: float = 35.0, rsi_sell: float = 65.0,
    allow_short: bool = True, capital: int = 10_000, lookback_years: int = 4,
) -> str:
    start, end = _date_range(lookback_years)
    hdr = _header(symbol, resolution, start, end, capital, allow_short)
    return hdr + f"""
class TradingOpsSmaRsi(QCAlgorithm):
    def initialize(self):
        self.set_start_date(*START_DATE)
        self.set_end_date(*END_DATE)
        self.set_cash(CAPITAL)
        eq = self.add_equity(SYMBOL, RESOLUTION)
        eq.set_data_normalization_mode(DataNormalizationMode.Adjusted)
        self._sym  = eq.symbol
        self._fast = self.sma(self._sym, {fast_ma}, RESOLUTION)
        self._slow = self.sma(self._sym, {slow_ma}, RESOLUTION)
        self._rsi  = self.rsi(self._sym, {rsi_period},
                              MovingAverageType.Exponential, RESOLUTION)
        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin)
        self.settings.free_portfolio_value_percentage = 0.05

    def on_data(self, data: Slice):
        if not (self._fast.is_ready and self._slow.is_ready and self._rsi.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return
        fast_above = self._fast.current.value > self._slow.current.value
        rsi_val    = self._rsi.current.value
        is_long    = self.portfolio[self._sym].is_long
        is_short   = self.portfolio[self._sym].is_short
        invested   = self.portfolio[self._sym].invested

        if fast_above and rsi_val < {rsi_buy}:
            if not is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif not fast_above and rsi_val > {rsi_sell} and ALLOW_SHORT:
            if not is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif not fast_above and invested:
            self.liquidate(self._sym)
"""


def build_breakout(
    symbol: str, resolution: str = "Daily",
    lookback_n: int = 20, atr_period: int = 14, atr_mult: float = 1.0,
    allow_short: bool = True, capital: int = 10_000, lookback_years: int = 4,
) -> str:
    start, end = _date_range(lookback_years)
    hdr = _header(symbol, resolution, start, end, capital, allow_short)
    return hdr + f"""
class TradingOpsBreakout(QCAlgorithm):
    def initialize(self):
        self.set_start_date(*START_DATE)
        self.set_end_date(*END_DATE)
        self.set_cash(CAPITAL)
        eq = self.add_equity(SYMBOL, RESOLUTION)
        eq.set_data_normalization_mode(DataNormalizationMode.Adjusted)
        self._sym     = eq.symbol
        self._max_h   = self.max(self._sym, {lookback_n}, RESOLUTION, Field.High)
        self._min_l   = self.min(self._sym, {lookback_n}, RESOLUTION, Field.Low)
        self._atr     = self.atr(self._sym, {atr_period},
                                 MovingAverageType.Exponential, RESOLUTION)
        self._atr_avg = self.sma(self._atr, {atr_period})
        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin)
        self.settings.free_portfolio_value_percentage = 0.05

    def on_data(self, data: Slice):
        if not (self._max_h.is_ready and self._min_l.is_ready
                and self._atr.is_ready and self._atr_avg.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return
        close      = data.bars[self._sym].close
        atr_ok     = self._atr.current.value > {atr_mult} * self._atr_avg.current.value
        is_long    = self.portfolio[self._sym].is_long
        is_short   = self.portfolio[self._sym].is_short

        if close > self._max_h.current.value and atr_ok:
            if not is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif close < self._min_l.current.value and atr_ok and ALLOW_SHORT:
            if not is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif is_long  and close < self._min_l.current.value:
            self.liquidate(self._sym)
        elif is_short and close > self._max_h.current.value:
            self.liquidate(self._sym)
"""


def build_mean_reversion(
    symbol: str, resolution: str = "Daily",
    bb_period: int = 20, bb_std: float = 2.0,
    rsi_period: int = 14, rsi_oversold: float = 30.0, rsi_overbought: float = 70.0,
    allow_short: bool = True, capital: int = 10_000, lookback_years: int = 4,
) -> str:
    start, end = _date_range(lookback_years)
    hdr = _header(symbol, resolution, start, end, capital, allow_short)
    return hdr + f"""
class TradingOpsMeanReversion(QCAlgorithm):
    def initialize(self):
        self.set_start_date(*START_DATE)
        self.set_end_date(*END_DATE)
        self.set_cash(CAPITAL)
        eq = self.add_equity(SYMBOL, RESOLUTION)
        eq.set_data_normalization_mode(DataNormalizationMode.Adjusted)
        self._sym = eq.symbol
        self._bb  = self.bb(self._sym, {bb_period}, {bb_std},
                            MovingAverageType.Simple, RESOLUTION)
        self._rsi = self.rsi(self._sym, {rsi_period},
                             MovingAverageType.Exponential, RESOLUTION)
        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin)
        self.settings.free_portfolio_value_percentage = 0.05

    def on_data(self, data: Slice):
        if not (self._bb.is_ready and self._rsi.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return
        close    = data.bars[self._sym].close
        upper    = self._bb.upper_band.current.value
        lower    = self._bb.lower_band.current.value
        middle   = self._bb.middle_band.current.value
        rsi_val  = self._rsi.current.value
        is_long  = self.portfolio[self._sym].is_long
        is_short = self.portfolio[self._sym].is_short

        if close < lower and rsi_val < {rsi_oversold}:
            if not is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif close > upper and rsi_val > {rsi_overbought} and ALLOW_SHORT:
            if not is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif is_long  and close >= middle:
            self.liquidate(self._sym)
        elif is_short and close <= middle:
            self.liquidate(self._sym)
"""


BUILDERS = {
    "sma_rsi":        build_sma_rsi,
    "breakout":       build_breakout,
    "mean_reversion": build_mean_reversion,
}

QC_RESOLUTION_MAP = {
    "1d": "Daily", "daily": "Daily",
    "1h": "Hour",  "hour":  "Hour",
    "1m": "Minute","minute": "Minute",
    "second": "Second",
    "tick":   "Tick",
}


def build_algorithm_code(
    symbol: str,
    strategy: str,
    resolution: str = "Daily",
    allow_short: bool = True,
    capital: int = 10_000,
    lookback_years: int = 4,
    params: dict | None = None,
) -> str:
    """
    Generate Python algorithm code for QC Cloud submission.
    params: optional dict of strategy-specific overrides (fast_ma, lookback_n, etc.)
    """
    res = QC_RESOLUTION_MAP.get(resolution.lower(), resolution)
    p   = params or {}
    builder = BUILDERS.get(strategy, build_sma_rsi)

    kwargs = dict(
        symbol=symbol,
        resolution=res,
        allow_short=allow_short,
        capital=capital,
        lookback_years=lookback_years,
    )

    if strategy == "sma_rsi":
        kwargs.update({
            "fast_ma":    int(p.get("fast_ma", 20)),
            "slow_ma":    int(p.get("slow_ma", 50)),
            "rsi_period": int(p.get("rsi_period", 14)),
            "rsi_buy":    float(p.get("rsi_buy", 35.0)),
            "rsi_sell":   float(p.get("rsi_sell", 65.0)),
        })
    elif strategy == "breakout":
        kwargs.update({
            "lookback_n": int(p.get("lookback_n", 20)),
            "atr_period": int(p.get("atr_period", 14)),
            "atr_mult":   float(p.get("atr_mult", 1.0)),
        })
    elif strategy == "mean_reversion":
        kwargs.update({
            "bb_period":      int(p.get("bb_period", 20)),
            "bb_std":         float(p.get("bb_std", 2.0)),
            "rsi_period":     int(p.get("rsi_period", 14)),
            "rsi_oversold":   float(p.get("rsi_oversold", 30.0)),
            "rsi_overbought": float(p.get("rsi_overbought", 70.0)),
        })

    return builder(**kwargs)
