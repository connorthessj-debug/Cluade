"""Tests for risk management system."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Minimal RiskManager implementation for testing (since core/risk_manager.py
# does not exist yet). Tests exercise the risk management *logic* that will
# govern the bots.
# ---------------------------------------------------------------------------

class RiskManager:
    """Risk manager with position sizing, drawdown kill switch, and
    correlation checks.

    This is a self-contained implementation used for unit testing the risk
    management logic. The production version in core/ will share the same
    interface.
    """

    def __init__(
        self,
        max_risk_pct: float = 1.0,
        max_positions: int = 5,
        max_drawdown_pct: float = 5.0,
        kill_switch_enabled: bool = True,
        correlation_pairs: dict = None,
    ):
        self.max_risk_pct = max_risk_pct
        self.max_positions = max_positions
        self.max_drawdown_pct = max_drawdown_pct
        self.kill_switch_enabled = kill_switch_enabled
        self.correlation_pairs = correlation_pairs or {
            "EUR_USD": ["GBP_USD"],
            "GBP_USD": ["EUR_USD"],
        }

        self.account_balance = 10000.0
        self.peak_balance = 10000.0
        self.open_positions: list = []
        self.kill_switch_triggered = False

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        risk_pct: float = None,
    ) -> float:
        """Calculate position size based on risk percentage.

        Uses the formula:
            position_size = (account_balance * risk_pct) / |entry - stop_loss|

        Args:
            entry_price: Planned entry price.
            stop_loss: Stop loss price.
            risk_pct: Risk as a fraction (default: self.max_risk_pct / 100).

        Returns:
            Position size in units.
        """
        if risk_pct is None:
            risk_pct = self.max_risk_pct / 100.0

        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return 0.0

        risk_amount = self.account_balance * risk_pct
        return risk_amount / risk_per_unit

    def check_max_positions(self) -> bool:
        """Return True if a new position can be opened."""
        return len(self.open_positions) < self.max_positions

    def check_drawdown(self) -> bool:
        """Check if the max drawdown threshold has been breached.

        Returns True if trading should continue, False if the kill switch
        should be triggered.
        """
        if not self.kill_switch_enabled:
            return True

        if self.account_balance > self.peak_balance:
            self.peak_balance = self.account_balance

        drawdown_pct = ((self.peak_balance - self.account_balance) /
                        self.peak_balance) * 100.0

        if drawdown_pct >= self.max_drawdown_pct:
            self.kill_switch_triggered = True
            return False
        return True

    def check_correlation(self, symbol: str) -> bool:
        """Check if opening a position on symbol would violate correlation rules.

        Returns True if the trade is allowed, False if a correlated position
        already exists.
        """
        correlated = self.correlation_pairs.get(symbol, [])
        for pos in self.open_positions:
            if pos.get("symbol") in correlated:
                return False
        return True

    async def check_trade(
        self,
        bot_name: str,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> bool:
        """Full pre-trade approval check.

        Verifies:
            1. Kill switch is not triggered
            2. Max positions not reached
            3. No correlation violation
            4. Drawdown is within limits
        """
        if self.kill_switch_triggered:
            return False

        if not self.check_max_positions():
            return False

        if not self.check_correlation(symbol):
            return False

        if not self.check_drawdown():
            return False

        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPositionSizing(unittest.TestCase):
    """Test position size calculation."""

    def setUp(self):
        self.rm = RiskManager(max_risk_pct=1.0)
        self.rm.account_balance = 10000.0

    def test_basic_position_size(self):
        """Position size should be risk_amount / risk_per_unit."""
        # Risk 1% of 10000 = 100. Entry=1.1000, SL=1.0950 -> risk=0.005
        # Size = 100 / 0.005 = 20000 units
        size = self.rm.calculate_position_size(
            entry_price=1.1000,
            stop_loss=1.0950,
        )
        self.assertAlmostEqual(size, 20000.0, places=0)

    def test_custom_risk_percentage(self):
        """Custom risk_pct should override default."""
        size = self.rm.calculate_position_size(
            entry_price=1.1000,
            stop_loss=1.0950,
            risk_pct=0.005,  # 0.5%
        )
        # Risk = 10000 * 0.005 = 50. Size = 50 / 0.005 = 10000
        self.assertAlmostEqual(size, 10000.0, places=0)

    def test_zero_risk_distance(self):
        """Zero distance between entry and SL should return 0."""
        size = self.rm.calculate_position_size(
            entry_price=100.0,
            stop_loss=100.0,
        )
        self.assertEqual(size, 0.0)

    def test_larger_stop_larger_size_reduction(self):
        """A wider stop loss should result in a smaller position size."""
        tight = self.rm.calculate_position_size(1.1000, 1.0990)  # 10 pip
        wide = self.rm.calculate_position_size(1.1000, 1.0950)   # 50 pip
        self.assertGreater(tight, wide)

    def test_larger_balance_larger_position(self):
        """A larger account balance should produce a larger position."""
        small = self.rm.calculate_position_size(1.1000, 1.0950)
        self.rm.account_balance = 50000.0
        large = self.rm.calculate_position_size(1.1000, 1.0950)
        self.assertGreater(large, small)


class TestMaxPositions(unittest.TestCase):
    """Test max position limit enforcement."""

    def setUp(self):
        self.rm = RiskManager(max_positions=3)

    def test_under_limit(self):
        """Should allow trades when under the position limit."""
        self.rm.open_positions = [
            {"symbol": "EUR_USD"},
        ]
        self.assertTrue(self.rm.check_max_positions())

    def test_at_limit(self):
        """Should reject trades when at the position limit."""
        self.rm.open_positions = [
            {"symbol": "EUR_USD"},
            {"symbol": "GBP_USD"},
            {"symbol": "USD_JPY"},
        ]
        self.assertFalse(self.rm.check_max_positions())

    def test_empty_positions(self):
        """Should allow trades when no positions are open."""
        self.rm.open_positions = []
        self.assertTrue(self.rm.check_max_positions())


class TestDrawdownKillSwitch(unittest.TestCase):
    """Test max drawdown kill switch."""

    def setUp(self):
        self.rm = RiskManager(max_drawdown_pct=5.0, kill_switch_enabled=True)
        self.rm.account_balance = 10000.0
        self.rm.peak_balance = 10000.0

    def test_no_drawdown(self):
        """No drawdown should allow trading."""
        self.assertTrue(self.rm.check_drawdown())
        self.assertFalse(self.rm.kill_switch_triggered)

    def test_small_drawdown_ok(self):
        """Small drawdown should still allow trading."""
        self.rm.account_balance = 9700.0  # 3% drawdown
        self.assertTrue(self.rm.check_drawdown())
        self.assertFalse(self.rm.kill_switch_triggered)

    def test_max_drawdown_triggers_kill_switch(self):
        """Drawdown exceeding threshold should trigger kill switch."""
        self.rm.account_balance = 9400.0  # 6% drawdown
        self.assertFalse(self.rm.check_drawdown())
        self.assertTrue(self.rm.kill_switch_triggered)

    def test_exact_threshold(self):
        """Drawdown exactly at threshold should trigger kill switch."""
        self.rm.account_balance = 9500.0  # exactly 5%
        self.assertFalse(self.rm.check_drawdown())
        self.assertTrue(self.rm.kill_switch_triggered)

    def test_kill_switch_disabled(self):
        """When disabled, drawdown should not trigger the kill switch."""
        self.rm.kill_switch_enabled = False
        self.rm.account_balance = 9000.0  # 10% drawdown
        self.assertTrue(self.rm.check_drawdown())
        self.assertFalse(self.rm.kill_switch_triggered)

    def test_peak_balance_updates(self):
        """Peak balance should increase when balance grows."""
        self.rm.account_balance = 12000.0
        self.rm.check_drawdown()
        self.assertEqual(self.rm.peak_balance, 12000.0)


class TestCorrelation(unittest.TestCase):
    """Test correlation check."""

    def setUp(self):
        self.rm = RiskManager(
            correlation_pairs={
                "EUR_USD": ["GBP_USD"],
                "GBP_USD": ["EUR_USD"],
                "USD_JPY": [],
            },
        )

    def test_no_correlation_conflict(self):
        """Non-correlated pairs should be allowed."""
        self.rm.open_positions = [{"symbol": "USD_JPY"}]
        self.assertTrue(self.rm.check_correlation("EUR_USD"))

    def test_correlation_conflict(self):
        """Correlated pairs should be blocked."""
        self.rm.open_positions = [{"symbol": "EUR_USD"}]
        self.assertFalse(self.rm.check_correlation("GBP_USD"))

    def test_no_open_positions(self):
        """No open positions means no correlation conflict."""
        self.rm.open_positions = []
        self.assertTrue(self.rm.check_correlation("EUR_USD"))

    def test_unknown_symbol_allowed(self):
        """Symbols not in the correlation map should be allowed."""
        self.rm.open_positions = [{"symbol": "EUR_USD"}]
        self.assertTrue(self.rm.check_correlation("XAU_USD"))


class TestTradeApproval(unittest.TestCase):
    """Test the full trade approval flow."""

    def setUp(self):
        self.rm = RiskManager(
            max_positions=3,
            max_drawdown_pct=5.0,
            kill_switch_enabled=True,
        )
        self.rm.account_balance = 10000.0
        self.rm.peak_balance = 10000.0
        self.loop = asyncio.new_event_loop()

    def tearDown(self):
        self.loop.close()

    def test_approved_trade(self):
        """A valid trade should be approved."""
        result = self.loop.run_until_complete(
            self.rm.check_trade("scalper", "USD_JPY", "buy", 1000, 150.0)
        )
        self.assertTrue(result)

    def test_rejected_kill_switch(self):
        """Trade should be rejected when kill switch is triggered."""
        self.rm.kill_switch_triggered = True
        result = self.loop.run_until_complete(
            self.rm.check_trade("scalper", "EUR_USD", "buy", 1000, 1.1)
        )
        self.assertFalse(result)

    def test_rejected_max_positions(self):
        """Trade should be rejected when max positions reached."""
        self.rm.open_positions = [
            {"symbol": "EUR_USD"},
            {"symbol": "USD_JPY"},
            {"symbol": "XAU_USD"},
        ]
        result = self.loop.run_until_complete(
            self.rm.check_trade("scalper", "GBP_USD", "buy", 1000, 1.25)
        )
        self.assertFalse(result)

    def test_rejected_correlation(self):
        """Trade should be rejected for correlated pairs."""
        self.rm.open_positions = [{"symbol": "EUR_USD"}]
        result = self.loop.run_until_complete(
            self.rm.check_trade("scalper", "GBP_USD", "buy", 1000, 1.25)
        )
        self.assertFalse(result)

    def test_rejected_drawdown(self):
        """Trade should be rejected when drawdown exceeds limit."""
        self.rm.account_balance = 9400.0  # 6% drawdown
        result = self.loop.run_until_complete(
            self.rm.check_trade("scalper", "EUR_USD", "buy", 1000, 1.1)
        )
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
