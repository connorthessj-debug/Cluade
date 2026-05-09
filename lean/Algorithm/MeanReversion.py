# region imports
from AlgorithmImports import *
# endregion

class MeanReversionAlgorithm(QCAlgorithm):
    """
    Bollinger Band extremes + RSI confirmation.
    Long when price below lower band AND RSI oversold.
    Short (optional) when price above upper band AND RSI overbought.
    Exit on mean reversion back to middle band.
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

        bb_period       = int(self.get_parameter("bb_period", "20"))
        bb_std          = float(self.get_parameter("bb_std",  "2.0"))
        rsi_period      = int(self.get_parameter("rsi_period", "14"))
        self._rsi_oversold   = float(self.get_parameter("rsi_oversold",   "30.0"))
        self._rsi_overbought = float(self.get_parameter("rsi_overbought", "70.0"))
        self._allow_short    = self.get_parameter("allow_short", "true").lower() == "true"

        self._bb  = self.bb(self._sym, bb_period, bb_std,
                            MovingAverageType.Simple, resolution)
        self._rsi = self.rsi(self._sym, rsi_period,
                             MovingAverageType.Exponential, resolution)

        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin
        )
        self.settings.free_portfolio_value_percentage = 0.05

    def on_data(self, data: Slice):
        if not (self._bb.is_ready and self._rsi.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return

        close        = data.bars[self._sym].close
        upper        = self._bb.upper_band.current.value
        lower        = self._bb.lower_band.current.value
        middle       = self._bb.middle_band.current.value
        rsi_val      = self._rsi.current.value
        is_long      = self.portfolio[self._sym].is_long
        is_short     = self.portfolio[self._sym].is_short

        if close < lower and rsi_val < self._rsi_oversold:
            if not is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif close > upper and rsi_val > self._rsi_overbought and self._allow_short:
            if not is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif is_long  and close >= middle:
            self.liquidate(self._sym)
        elif is_short and close <= middle:
            self.liquidate(self._sym)

    @staticmethod
    def _parse_resolution(s: str) -> Resolution:
        return {
            "Tick": Resolution.Tick, "Second": Resolution.Second,
            "Minute": Resolution.Minute, "Hour": Resolution.Hour,
        }.get(s, Resolution.Daily)
