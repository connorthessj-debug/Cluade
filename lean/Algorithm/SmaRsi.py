# region imports
from AlgorithmImports import *
# endregion

class SmaRsiAlgorithm(QCAlgorithm):
    """
    SMA crossover + RSI confirmation strategy.
    Long when fast SMA > slow SMA AND RSI oversold.
    Short (optional) when fast SMA < slow SMA AND RSI overbought.
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

        fast_ma    = int(self.get_parameter("fast_ma",    "20"))
        slow_ma    = int(self.get_parameter("slow_ma",    "50"))
        rsi_period = int(self.get_parameter("rsi_period", "14"))
        self._rsi_buy    = float(self.get_parameter("rsi_buy",  "35.0"))
        self._rsi_sell   = float(self.get_parameter("rsi_sell", "65.0"))
        self._allow_short = self.get_parameter("allow_short", "true").lower() == "true"

        self._fast = self.sma(self._sym, fast_ma,    resolution)
        self._slow = self.sma(self._sym, slow_ma,    resolution)
        self._rsi  = self.rsi(self._sym, rsi_period,
                              MovingAverageType.Exponential, resolution)

        self.set_brokerage_model(
            BrokerageModel.InteractiveBrokersBrokerage, AccountType.Margin
        )
        self.settings.free_portfolio_value_percentage = 0.05  # 5% cash buffer

    def on_data(self, data: Slice):
        if not (self._fast.is_ready and self._slow.is_ready and self._rsi.is_ready):
            return
        if not data.bars.contains_key(self._sym):
            return

        fast_val = self._fast.current.value
        slow_val = self._slow.current.value
        rsi_val  = self._rsi.current.value
        invested = self.portfolio[self._sym].invested

        if fast_val > slow_val and rsi_val < self._rsi_buy:
            if not self.portfolio[self._sym].is_long:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, 1)
        elif fast_val < slow_val and rsi_val > self._rsi_sell and self._allow_short:
            if not self.portfolio[self._sym].is_short:
                self.liquidate(self._sym)
                self.set_holdings(self._sym, -1)
        elif fast_val < slow_val and invested:
            self.liquidate(self._sym)

    @staticmethod
    def _parse_resolution(s: str) -> Resolution:
        return {
            "Tick": Resolution.Tick, "Second": Resolution.Second,
            "Minute": Resolution.Minute, "Hour": Resolution.Hour,
        }.get(s, Resolution.Daily)
