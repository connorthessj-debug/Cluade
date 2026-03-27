"""Tests for arbitrage bot components."""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bots.arbitrage.fee_calculator import FeeCalculator
from bots.arbitrage.spread_monitor import SpreadMonitor
from bots.arbitrage.execution import ArbitrageExecutor


# ---------------------------------------------------------------------------
# Fee calculation tests
# ---------------------------------------------------------------------------

class TestFeeCalculator(unittest.TestCase):
    """Test fee calculation for different exchanges."""

    def setUp(self):
        self.calc = FeeCalculator()

    def test_binance_taker_fee(self):
        """Binance taker fee should be 0.1%."""
        fee = self.calc.calculate_fees("binance", "taker", amount=1000, price=1.0)
        # 1000 * 1.0 * 0.001 = 1.0
        self.assertAlmostEqual(fee, 1.0)

    def test_binance_maker_fee(self):
        """Binance maker fee should be 0.1%."""
        fee = self.calc.calculate_fees("binance", "maker", amount=1000, price=1.0)
        self.assertAlmostEqual(fee, 1.0)

    def test_coinbase_taker_fee(self):
        """Coinbase taker fee should be 0.6%."""
        fee = self.calc.calculate_fees("coinbase", "taker", amount=1000, price=1.0)
        # 1000 * 1.0 * 0.006 = 6.0
        self.assertAlmostEqual(fee, 6.0)

    def test_coinbase_maker_fee(self):
        """Coinbase maker fee should be 0.4%."""
        fee = self.calc.calculate_fees("coinbase", "maker", amount=1000, price=1.0)
        # 1000 * 1.0 * 0.004 = 4.0
        self.assertAlmostEqual(fee, 4.0)

    def test_unknown_exchange_defaults(self):
        """Unknown exchange should default to 0.1% fee."""
        fee = self.calc.calculate_fees("kraken", "taker", amount=1000, price=1.0)
        self.assertAlmostEqual(fee, 1.0)

    def test_custom_fee_schedule(self):
        """Custom fee schedule should override defaults."""
        custom = FeeCalculator(fee_schedules={
            "kraken": {"maker": 0.002, "taker": 0.003},
        })
        fee = custom.calculate_fees("kraken", "taker", amount=1000, price=1.0)
        self.assertAlmostEqual(fee, 3.0)

    def test_fee_scales_with_amount(self):
        """Fee should scale linearly with trade amount."""
        fee1 = self.calc.calculate_fees("binance", "taker", amount=1000, price=1.0)
        fee2 = self.calc.calculate_fees("binance", "taker", amount=2000, price=1.0)
        self.assertAlmostEqual(fee2, fee1 * 2)

    def test_fee_scales_with_price(self):
        """Fee should scale linearly with price."""
        fee1 = self.calc.calculate_fees("binance", "taker", amount=1000, price=1.0)
        fee2 = self.calc.calculate_fees("binance", "taker", amount=1000, price=2.0)
        self.assertAlmostEqual(fee2, fee1 * 2)

    def test_case_insensitive_exchange_name(self):
        """Exchange names should be case-insensitive."""
        fee_lower = self.calc.calculate_fees("binance", "taker", 1000, 1.0)
        fee_upper = self.calc.calculate_fees("BINANCE", "taker", 1000, 1.0)
        self.assertAlmostEqual(fee_lower, fee_upper)


# ---------------------------------------------------------------------------
# Net profit calculation tests
# ---------------------------------------------------------------------------

class TestNetProfit(unittest.TestCase):
    """Test net profit calculation after fees."""

    def setUp(self):
        self.calc = FeeCalculator()

    def test_profitable_spread(self):
        """Net profit should be positive when spread exceeds fees."""
        # Buy at 0.9990 on Binance, sell at 1.0100 on Coinbase
        # Gross = (1.0100 - 0.9990) * 1000 = 11.0
        # Buy fee = 1000 * 0.9990 * 0.001 = 0.999
        # Sell fee = 1000 * 1.0100 * 0.006 = 6.06
        # Net = 11.0 - 0.999 - 6.06 = 3.941
        net = self.calc.calculate_net_profit(
            buy_exchange="binance",
            sell_exchange="coinbase",
            buy_price=0.9990,
            sell_price=1.0100,
            amount=1000,
        )
        self.assertGreater(net, 0)
        self.assertAlmostEqual(net, 3.941, places=2)

    def test_unprofitable_spread(self):
        """Net profit should be negative when fees exceed spread."""
        net = self.calc.calculate_net_profit(
            buy_exchange="coinbase",
            sell_exchange="coinbase",
            buy_price=1.0000,
            sell_price=1.0005,
            amount=1000,
        )
        self.assertLess(net, 0)

    def test_zero_spread(self):
        """Same buy and sell price should yield a negative net (fees only)."""
        net = self.calc.calculate_net_profit(
            buy_exchange="binance",
            sell_exchange="coinbase",
            buy_price=1.0000,
            sell_price=1.0000,
            amount=1000,
        )
        self.assertLess(net, 0)

    def test_net_profit_symmetry(self):
        """Reversing buy/sell exchanges should change the net profit
        (because fee rates differ between exchanges)."""
        net_a = self.calc.calculate_net_profit(
            "binance", "coinbase", 1.0000, 1.0100, 1000)
        net_b = self.calc.calculate_net_profit(
            "coinbase", "binance", 1.0000, 1.0100, 1000)
        # Different fee structures mean different nets
        self.assertNotAlmostEqual(net_a, net_b, places=2)


# ---------------------------------------------------------------------------
# Minimum profitable spread tests
# ---------------------------------------------------------------------------

class TestMinProfitableSpread(unittest.TestCase):
    """Test minimum profitable spread calculation."""

    def setUp(self):
        self.calc = FeeCalculator()

    def test_binance_to_coinbase(self):
        """Min spread Binance->Coinbase = 0.001 + 0.006 = 0.007."""
        spread = self.calc.get_min_profitable_spread("binance", "coinbase")
        self.assertAlmostEqual(spread, 0.007, places=4)

    def test_coinbase_to_binance(self):
        """Min spread Coinbase->Binance = 0.006 + 0.001 = 0.007."""
        spread = self.calc.get_min_profitable_spread("coinbase", "binance")
        self.assertAlmostEqual(spread, 0.007, places=4)

    def test_same_exchange(self):
        """Min spread on same exchange = 2 * taker_rate."""
        spread = self.calc.get_min_profitable_spread("binance", "binance")
        self.assertAlmostEqual(spread, 0.002, places=4)

    def test_spread_is_positive(self):
        """Min profitable spread should always be positive."""
        spread = self.calc.get_min_profitable_spread("binance", "coinbase")
        self.assertGreater(spread, 0)


# ---------------------------------------------------------------------------
# Spread monitoring logic tests
# ---------------------------------------------------------------------------

class TestSpreadMonitoring(unittest.TestCase):
    """Test spread monitoring and opportunity detection."""

    def test_get_best_opportunity_empty(self):
        """No data should return None."""
        monitor = SpreadMonitor(
            exchange_manager=None,
            pairs=["USDC/USDT"],
        )
        self.assertIsNone(monitor.get_best_opportunity())

    def test_get_best_opportunity_selects_highest_net(self):
        """Best opportunity should be the one with highest net profit."""
        monitor = SpreadMonitor(
            exchange_manager=None,
            pairs=["USDC/USDT"],
        )
        # Manually set last_spreads to simulate fetched data
        monitor._last_spreads = [
            {
                "pair": "USDC/USDT",
                "buy_exchange": "binance",
                "sell_exchange": "coinbase",
                "buy_price": 0.9990,
                "sell_price": 1.0100,
                "spread": 0.011,
                "spread_pct": 1.1,
                "timestamp": 1000,
            },
            {
                "pair": "USDT/USD",
                "buy_exchange": "coinbase",
                "sell_exchange": "binance",
                "buy_price": 0.9980,
                "sell_price": 1.0200,
                "spread": 0.022,
                "spread_pct": 2.2,
                "timestamp": 1000,
            },
        ]
        best = monitor.get_best_opportunity()
        self.assertIsNotNone(best)
        # The second spread is wider, should yield higher net profit
        self.assertEqual(best["pair"], "USDT/USD")
        self.assertIn("net_profit_per_unit", best)
        self.assertGreater(best["net_profit_per_unit"], 0)


# ---------------------------------------------------------------------------
# Execution result tracking tests
# ---------------------------------------------------------------------------

class TestExecutionResult(unittest.TestCase):
    """Test execution result handling."""

    def test_extract_fill_price_dict(self):
        """Fill price should be extracted from standard dict keys."""
        executor = ArbitrageExecutor(
            exchange_manager=None,
            fee_calculator=FeeCalculator(),
        )
        result = {"average": 1.005, "amount": 1000}
        fill = executor._extract_fill_price(result, fallback=1.0)
        self.assertAlmostEqual(fill, 1.005)

    def test_extract_fill_price_fallback(self):
        """Should fall back to default when no fill price is found."""
        executor = ArbitrageExecutor(
            exchange_manager=None,
            fee_calculator=FeeCalculator(),
        )
        result = {"status": "filled"}
        fill = executor._extract_fill_price(result, fallback=1.0)
        self.assertAlmostEqual(fill, 1.0)

    def test_extract_fill_price_alt_keys(self):
        """Should extract from alternative key names."""
        executor = ArbitrageExecutor(
            exchange_manager=None,
            fee_calculator=FeeCalculator(),
        )
        for key in ("avg_price", "price", "fill_price"):
            result = {key: 1.0123}
            fill = executor._extract_fill_price(result, fallback=0.0)
            self.assertAlmostEqual(fill, 1.0123,
                                   msg=f"Failed for key '{key}'")

    def test_extract_fill_price_none_value(self):
        """None values should be skipped, trying other keys."""
        executor = ArbitrageExecutor(
            exchange_manager=None,
            fee_calculator=FeeCalculator(),
        )
        result = {"average": None, "price": 1.05}
        fill = executor._extract_fill_price(result, fallback=0.0)
        self.assertAlmostEqual(fill, 1.05)


if __name__ == '__main__':
    unittest.main()
