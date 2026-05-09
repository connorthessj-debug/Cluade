# region imports
from AlgorithmImports import *
# endregion

class BreakoutAlgorithm(QCAlgorithm):
    """
    N-bar high/low channel breakout with ATR expansion filter.
    Long on close above N-bar high when ATR > rolling ATR average.
    Short (optional) on close below N-bar low with same ATR filter.
    """

    def initialize(self):
        self.set_start_date(
            int(self.get_parameter("start_year",  "2020")),
            int(self.get_parameter("start_month", "1")),
            int(self.get_parameter("start_day",   "1")),
        )
        self.set_end_date(
            int(self.get_parameter("end_year",  "2024")),
            int(self.get_parameter("end_month", "12")),
            int(self.get_parameter("end_day",   "31")),
        )
        self.set_cash(int(self.get_parameter("capital", "10000")))

        symbol_str = self.get_parameter("symbol", "AAPL")
        resolution = self._parse_resolution(self.get_parameter("resolution", "Daily"))

        equity = self.add_equity(symbol_str, resolution)
        equity.set_data_normalization_mode(DataNormalizationMode.Adjusted)
        self._sym = equity.symbol

        lookback_n = int(self.get_parameter("lookback_n",  "20"))
        atr_period = int(self.get_parameter("atr_period",  "14"))
        self._atr_mult    = float(self.get_parameter("atr_mult", "1.0"))
        self._allow_short = self.get_parameter("allow_short", "true").lower() == "true"

        self._max_high = self.max(self._sym, lookback_n, resolution, Field.High)
        self._min_low  = self.min(self._sym, lookback_n, resolution, Field.Low)
        self._atr      = self.atr(self._sym, atr_period, MovingAverageType.Exponential, resolution)
        self._atr_avg  = self.sma(self._atr, atr_period)

        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin
        )
        self.settings.free_portfolio_value_percentage = 0.05

    def on_data(self, data: Slice):
        if not (self._max_high.is_ready and self._min_low.is_ready
                and self._atr.is_ready and self._atr_avg.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return

        bar   = data.bars[self._sym]
        close = bar.close
        atr_filter = self._atr.current.value > self._atr_mult * self._atr_avg.current.value

        if close > self._max_high.current.value and atr_filter:
            if not self.portfolio[self._sym].is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif close < self._min_low.current.value and atr_filter and self._allow_short:
            if not self.portfolio[self._sym].is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif (self.portfolio[self._sym].is_long and close < self._min_low.current.value):
            self.liquidate(self._sym)
        elif (self.portfolio[self._sym].is_short and close > self._max_high.current.value):
            self.liquidate(self._sym)

    @staticmethod
    def _parse_resolution(s: str) -> Resolution:
        return {
            "Tick": Resolution.Tick, "Second": Resolution.Second,
            "Minute": Resolution.Minute, "Hour": Resolution.Hour,
        }.get(s, Resolution.Daily)
