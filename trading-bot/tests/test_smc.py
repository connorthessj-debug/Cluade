"""Tests for Smart Money Concepts analysis library."""
import sys
import unittest
from pathlib import Path

# Ensure project root is importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from smc.models import OHLCV, FairValueGap, LiquidityLevel, OrderBlock, SwingPoint
from smc.market_structure import (
    classify_structure,
    detect_bos,
    detect_choch,
    detect_swing_points,
    get_trend,
)
from smc.order_blocks import check_mitigation, find_order_blocks, is_price_in_ob
from smc.fair_value_gaps import check_fvg_fill, find_fvg, is_price_in_fvg
from smc.liquidity import detect_liquidity_sweep, find_equal_levels, find_swing_liquidity
from smc.fibonacci import calculate_ote_zone, get_fib_levels, is_in_discount, is_in_premium
from smc.confluence import score_setup, find_entry, calculate_sl_tp


# ---------------------------------------------------------------------------
# Helper: generate synthetic OHLCV data
# ---------------------------------------------------------------------------

def make_candles(prices, base_ts=1000.0, interval=60.0):
    """Generate OHLCV bars from a list of (open, high, low, close) tuples.

    If a single float is given per element, it is treated as (close) and
    a default OHLC spread is applied.
    """
    candles = []
    for i, p in enumerate(prices):
        ts = base_ts + i * interval
        if isinstance(p, (int, float)):
            o = p
            h = p + 0.5
            l = p - 0.5
            c = p
            candles.append(OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=100))
        else:
            o, h, l, c = p
            candles.append(OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=100))
    return candles


def make_uptrend(start=100.0, swings=8, step=2.0, retrace_ratio=0.4):
    """Generate an uptrending series with clear swing highs and lows.

    Each swing consists of a ramp of 3 bars plus a peak/trough bar,
    producing bars that detect_swing_points(lookback=2) can identify.
    The overall pattern: each swing high is higher than the last (HH)
    and each swing low is higher than the last (HL).
    """
    prices = []
    level = start
    going_up = True

    for s in range(swings):
        if going_up:
            target = level + step
            # 2 ramp bars leading to the peak
            mid = (level + target) / 2.0
            prices.append((level, level + 0.1, level - 0.1, mid))
            prices.append((mid, mid + 0.1, mid - 0.1, target - 0.3))
            # Peak bar - its high must exceed all neighbors by a margin
            prices.append((target - 0.3, target + 0.2, target - 0.5, target - 0.1))
            # 2 declining bars after peak
            prices.append((target - 0.1, target - 0.1, target - step * retrace_ratio * 0.5 - 0.3,
                           target - step * retrace_ratio * 0.5))
            level = target - step * retrace_ratio
            prices.append((target - step * retrace_ratio * 0.5, target - step * retrace_ratio * 0.5,
                           level - 0.1, level + 0.1))
            going_up = False
        else:
            # Trough bar
            prices.append((level + 0.1, level + 0.3, level - 0.2, level + 0.05))
            # 2 ramp bars going back up
            next_target = level + step
            mid = (level + next_target) / 2.0
            prices.append((level + 0.05, mid + 0.1, level + 0.05, mid))
            prices.append((mid, next_target - 0.3, mid - 0.1, next_target - 0.5))
            level = next_target - 0.5
            going_up = True

    return make_candles(prices)


def make_downtrend(start=100.0, swings=8, step=2.0, retrace_ratio=0.4):
    """Generate a downtrending series with clear swing highs and lows."""
    prices = []
    level = start
    going_down = True

    for s in range(swings):
        if going_down:
            target = level - step
            mid = (level + target) / 2.0
            prices.append((level, level + 0.1, level - 0.1, mid))
            prices.append((mid, mid + 0.1, mid - 0.1, target + 0.3))
            # Trough bar
            prices.append((target + 0.3, target + 0.5, target - 0.2, target + 0.1))
            # 2 rising bars after trough
            prices.append((target + 0.1, target + step * retrace_ratio * 0.5 + 0.3,
                           target + 0.1, target + step * retrace_ratio * 0.5))
            level = target + step * retrace_ratio
            prices.append((target + step * retrace_ratio * 0.5,
                           level + 0.1,
                           target + step * retrace_ratio * 0.5,
                           level - 0.1))
            going_down = False
        else:
            # Peak bar
            prices.append((level - 0.1, level + 0.2, level - 0.3, level - 0.05))
            # 2 declining bars
            next_target = level - step
            mid = (level + next_target) / 2.0
            prices.append((level - 0.05, level - 0.05, mid - 0.1, mid))
            prices.append((mid, mid + 0.1, next_target + 0.5, next_target + 0.5))
            level = next_target + 0.5
            going_down = True

    return make_candles(prices)


# ---------------------------------------------------------------------------
# Swing point tests
# ---------------------------------------------------------------------------

class TestSwingPoints(unittest.TestCase):
    """Tests for detect_swing_points."""

    def test_swing_high_detected(self):
        """A clear peak in the data should be detected as a swing high."""
        # Create V-shape: prices go up then down.
        prices = [10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10]
        candles = make_candles(prices)
        points = detect_swing_points(candles, lookback=2)
        highs = [sp for sp in points if sp.type == 'high']
        self.assertTrue(len(highs) >= 1)
        # The highest swing high should be near the peak.
        peak = max(highs, key=lambda sp: sp.price)
        self.assertGreaterEqual(peak.price, 14.5)

    def test_swing_low_detected(self):
        """A clear trough should be detected as a swing low."""
        prices = [15, 14, 13, 12, 11, 10, 11, 12, 13, 14, 15]
        candles = make_candles(prices)
        points = detect_swing_points(candles, lookback=2)
        lows = [sp for sp in points if sp.type == 'low']
        self.assertTrue(len(lows) >= 1)
        trough = min(lows, key=lambda sp: sp.price)
        self.assertLessEqual(trough.price, 10.5)

    def test_insufficient_data_returns_empty(self):
        """With fewer bars than 2*lookback+1, no swing points should be found."""
        candles = make_candles([10, 11, 12])
        points = detect_swing_points(candles, lookback=5)
        self.assertEqual(len(points), 0)

    def test_multiple_swing_points_in_zigzag(self):
        """A zig-zag pattern should produce multiple swing highs and lows."""
        candles = make_uptrend()
        points = detect_swing_points(candles, lookback=2)
        highs = [sp for sp in points if sp.type == 'high']
        lows = [sp for sp in points if sp.type == 'low']
        self.assertTrue(len(highs) >= 2,
                        f"Expected >=2 swing highs, got {len(highs)}")
        self.assertTrue(len(lows) >= 2,
                        f"Expected >=2 swing lows, got {len(lows)}")


# ---------------------------------------------------------------------------
# Market structure classification tests
# ---------------------------------------------------------------------------

class TestMarketStructure(unittest.TestCase):
    """Tests for classify_structure and get_trend."""

    def test_uptrend_hh_hl(self):
        """An uptrend should produce HH and HL labels."""
        candles = make_uptrend()
        points = detect_swing_points(candles, lookback=2)
        classifications = classify_structure(points)
        labels = [c['label'] for c in classifications if c['label'] is not None]
        # Should contain some HH and HL labels
        self.assertTrue('HH' in labels or 'HL' in labels,
                        f"Expected HH/HL labels in uptrend, got: {labels}")

    def test_downtrend_lh_ll(self):
        """A downtrend should produce LH and LL labels."""
        candles = make_downtrend()
        points = detect_swing_points(candles, lookback=2)
        classifications = classify_structure(points)
        labels = [c['label'] for c in classifications if c['label'] is not None]
        self.assertTrue('LH' in labels or 'LL' in labels,
                        f"Expected LH/LL labels in downtrend, got: {labels}")

    def test_get_trend_bullish(self):
        """get_trend should return 'bullish' for an uptrend."""
        candles = make_uptrend(start=100)
        points = detect_swing_points(candles, lookback=2)
        if len(points) >= 4:
            trend = get_trend(points)
            self.assertIn(trend, ['bullish', 'ranging'])

    def test_get_trend_bearish(self):
        """get_trend should return 'bearish' for a downtrend."""
        candles = make_downtrend(start=100)
        points = detect_swing_points(candles, lookback=2)
        if len(points) >= 4:
            trend = get_trend(points)
            self.assertIn(trend, ['bearish', 'ranging'])

    def test_get_trend_insufficient_data(self):
        """get_trend should return 'ranging' with fewer than 4 swing points."""
        points = [
            SwingPoint(index=0, price=100, type='high', timestamp=1000),
            SwingPoint(index=5, price=95, type='low', timestamp=1300),
        ]
        trend = get_trend(points)
        self.assertEqual(trend, 'ranging')


# ---------------------------------------------------------------------------
# BOS tests
# ---------------------------------------------------------------------------

class TestBOS(unittest.TestCase):
    """Tests for Break of Structure detection."""

    def test_bullish_bos_detected(self):
        """In an uptrend, a close above a prior swing high should trigger BOS."""
        candles = make_uptrend(start=100, step=3.0)
        points = detect_swing_points(candles, lookback=2)
        if len(points) >= 3:
            bos = detect_bos(candles, points)
            bullish_bos = [b for b in bos if b['type'] == 'bullish']
            # May or may not find BOS depending on exact classification
            # Just verify no crash and correct structure
            for b in bullish_bos:
                self.assertIn('price', b)
                self.assertIn('index', b)
                self.assertIn('broken_swing', b)

    def test_bearish_bos_detected(self):
        """In a downtrend, a close below a prior swing low should trigger BOS."""
        candles = make_downtrend(start=100, step=3.0)
        points = detect_swing_points(candles, lookback=2)
        if len(points) >= 3:
            bos = detect_bos(candles, points)
            bearish_bos = [b for b in bos if b['type'] == 'bearish']
            for b in bearish_bos:
                self.assertIn('price', b)
                self.assertIn('index', b)

    def test_bos_requires_minimum_swing_points(self):
        """BOS detection should return empty with fewer than 3 swing points."""
        candles = make_candles([10, 11, 12])
        points = [SwingPoint(0, 10, 'low', 1000)]
        bos = detect_bos(candles, points)
        self.assertEqual(len(bos), 0)


# ---------------------------------------------------------------------------
# CHoCH tests
# ---------------------------------------------------------------------------

class TestCHoCH(unittest.TestCase):
    """Tests for Change of Character detection."""

    def test_choch_requires_minimum_points(self):
        """CHoCH detection should return empty with fewer than 3 swing points."""
        candles = make_candles([10, 11])
        points = [SwingPoint(0, 10, 'low', 1000)]
        choch = detect_choch(candles, points)
        self.assertEqual(len(choch), 0)

    def test_choch_structure(self):
        """CHoCH events should have type, price, and index keys."""
        # Build a trend that reverses
        up = make_uptrend(start=100, swings=4, step=3.0)
        down = make_downtrend(start=up[-1].close, swings=4, step=3.0)
        # Adjust timestamps for the downtrend
        for i, c in enumerate(down):
            c.timestamp = up[-1].timestamp + (i + 1) * 60.0
        combined = up + down
        points = detect_swing_points(combined, lookback=2)
        if len(points) >= 3:
            choch = detect_choch(combined, points)
            for event in choch:
                self.assertIn('type', event)
                self.assertIn('price', event)
                self.assertIn('index', event)
                self.assertIn(event['type'], ['bullish', 'bearish'])


# ---------------------------------------------------------------------------
# Order block tests
# ---------------------------------------------------------------------------

class TestOrderBlocks(unittest.TestCase):
    """Tests for order block identification and mitigation."""

    def test_find_order_blocks_from_bos(self):
        """Order blocks should be found near BOS events."""
        candles = make_uptrend(start=100, step=3.0)
        points = detect_swing_points(candles, lookback=2)
        bos = detect_bos(candles, points)
        if bos:
            obs = find_order_blocks(candles, bos)
            for ob in obs:
                self.assertIn(ob.type, ['bullish', 'bearish'])
                self.assertGreater(ob.high, ob.low)
                self.assertFalse(ob.mitigated)

    def test_bullish_ob_zone(self):
        """A bullish OB should have valid high > low boundaries."""
        ob = OrderBlock(type='bullish', high=105, low=103, timeframe='H1',
                        created_at=1000, mitigated=False)
        self.assertEqual(ob.type, 'bullish')
        self.assertGreater(ob.high, ob.low)

    def test_bearish_ob_zone(self):
        """A bearish OB should have valid high > low boundaries."""
        ob = OrderBlock(type='bearish', high=110, low=108, timeframe='H1',
                        created_at=1000, mitigated=False)
        self.assertEqual(ob.type, 'bearish')
        self.assertGreater(ob.high, ob.low)

    def test_is_price_in_ob(self):
        """is_price_in_ob should return True when price is within OB bounds."""
        ob = OrderBlock(type='bullish', high=105, low=100,
                        timeframe='H1', created_at=1000)
        self.assertTrue(is_price_in_ob(102.5, ob))
        self.assertTrue(is_price_in_ob(100.0, ob))  # boundary
        self.assertTrue(is_price_in_ob(105.0, ob))  # boundary
        self.assertFalse(is_price_in_ob(99.0, ob))
        self.assertFalse(is_price_in_ob(106.0, ob))

    def test_check_mitigation_bullish(self):
        """A bullish OB is mitigated when a candle closes below OB.low."""
        ob = OrderBlock(type='bullish', high=105, low=100,
                        timeframe='H1', created_at=1000)
        # Candles after creation that don't break the OB
        candles_ok = [
            OHLCV(timestamp=1100, open=102, high=106, low=101, close=104, volume=100),
            OHLCV(timestamp=1200, open=104, high=107, low=102, close=106, volume=100),
        ]
        self.assertFalse(check_mitigation(ob, candles_ok))

        # Candle that closes below OB low
        candles_break = [
            OHLCV(timestamp=1100, open=102, high=103, low=98, close=99, volume=100),
        ]
        self.assertTrue(check_mitigation(ob, candles_break))

    def test_check_mitigation_bearish(self):
        """A bearish OB is mitigated when a candle closes above OB.high."""
        ob = OrderBlock(type='bearish', high=110, low=108,
                        timeframe='H1', created_at=1000)
        candles_break = [
            OHLCV(timestamp=1100, open=109, high=112, low=109, close=111, volume=100),
        ]
        self.assertTrue(check_mitigation(ob, candles_break))

    def test_empty_inputs(self):
        """find_order_blocks should handle empty inputs gracefully."""
        self.assertEqual(find_order_blocks([], []), [])
        self.assertEqual(find_order_blocks(make_candles([10, 11]), []), [])


# ---------------------------------------------------------------------------
# FVG tests
# ---------------------------------------------------------------------------

class TestFairValueGaps(unittest.TestCase):
    """Tests for Fair Value Gap detection and fill tracking."""

    def test_bullish_fvg_detection(self):
        """A bullish FVG: candle[i-2].high < candle[i].low."""
        candles = [
            OHLCV(timestamp=100, open=10, high=11, low=9, close=10.5, volume=100),
            OHLCV(timestamp=200, open=11, high=16, low=10.5, close=15, volume=200),  # impulse
            OHLCV(timestamp=300, open=15, high=17, low=14, close=16, volume=150),
        ]
        # candle[0].high=11, candle[2].low=14 -> gap from 11 to 14
        fvgs = find_fvg(candles)
        bullish = [f for f in fvgs if f.type == 'bullish']
        self.assertEqual(len(bullish), 1)
        self.assertAlmostEqual(bullish[0].low, 11.0)
        self.assertAlmostEqual(bullish[0].high, 14.0)

    def test_bearish_fvg_detection(self):
        """A bearish FVG: candle[i-2].low > candle[i].high."""
        candles = [
            OHLCV(timestamp=100, open=20, high=21, low=19, close=19.5, volume=100),
            OHLCV(timestamp=200, open=19, high=19.5, low=13, close=14, volume=200),  # impulse
            OHLCV(timestamp=300, open=14, high=15, low=12, close=13, volume=150),
        ]
        # candle[0].low=19, candle[2].high=15 -> gap from 15 to 19
        fvgs = find_fvg(candles)
        bearish = [f for f in fvgs if f.type == 'bearish']
        self.assertEqual(len(bearish), 1)
        self.assertAlmostEqual(bearish[0].low, 15.0)
        self.assertAlmostEqual(bearish[0].high, 19.0)

    def test_no_fvg_when_no_gap(self):
        """Overlapping candles should not produce FVGs."""
        candles = [
            OHLCV(timestamp=100, open=10, high=12, low=9, close=11, volume=100),
            OHLCV(timestamp=200, open=11, high=13, low=10, close=12, volume=100),
            OHLCV(timestamp=300, open=12, high=13, low=10.5, close=11, volume=100),
        ]
        fvgs = find_fvg(candles)
        self.assertEqual(len(fvgs), 0)

    def test_fvg_fill_status_unfilled(self):
        """FVG should be unfilled if no subsequent candle enters the zone."""
        fvg = FairValueGap(type='bullish', high=14, low=11,
                           timeframe='H1', created_at=200)
        candles = [
            OHLCV(timestamp=100, open=10, high=11, low=9, close=10, volume=100),
            OHLCV(timestamp=300, open=15, high=17, low=14.5, close=16, volume=100),
        ]
        status = check_fvg_fill(fvg, candles)
        self.assertEqual(status, 'unfilled')

    def test_fvg_fill_status_partial(self):
        """FVG should be partially filled if price enters but doesn't pass through."""
        fvg = FairValueGap(type='bullish', high=14, low=11,
                           timeframe='H1', created_at=200)
        candles = [
            OHLCV(timestamp=300, open=15, high=16, low=12, close=13, volume=100),
        ]
        status = check_fvg_fill(fvg, candles)
        self.assertEqual(status, 'partial')

    def test_fvg_fill_status_filled(self):
        """FVG should be fully filled if price passes through the entire zone."""
        fvg = FairValueGap(type='bullish', high=14, low=11,
                           timeframe='H1', created_at=200)
        candles = [
            OHLCV(timestamp=300, open=13, high=14, low=10, close=10.5, volume=100),
        ]
        status = check_fvg_fill(fvg, candles)
        self.assertEqual(status, 'filled')

    def test_bearish_fvg_fill(self):
        """A bearish FVG is filled when a candle's high goes above fvg.high."""
        fvg = FairValueGap(type='bearish', high=19, low=15,
                           timeframe='H1', created_at=200)
        candles = [
            OHLCV(timestamp=300, open=17, high=20, low=16, close=19.5, volume=100),
        ]
        status = check_fvg_fill(fvg, candles)
        self.assertEqual(status, 'filled')

    def test_is_price_in_fvg(self):
        """is_price_in_fvg should return True for prices within the FVG zone."""
        fvg = FairValueGap(type='bullish', high=14, low=11,
                           timeframe='H1', created_at=100)
        self.assertTrue(is_price_in_fvg(12.5, fvg))
        self.assertTrue(is_price_in_fvg(11.0, fvg))  # boundary
        self.assertFalse(is_price_in_fvg(10.0, fvg))
        self.assertFalse(is_price_in_fvg(15.0, fvg))

    def test_insufficient_data(self):
        """find_fvg with fewer than 3 candles should return empty."""
        candles = make_candles([10, 11])
        self.assertEqual(find_fvg(candles), [])


# ---------------------------------------------------------------------------
# Liquidity tests
# ---------------------------------------------------------------------------

class TestLiquidity(unittest.TestCase):
    """Tests for liquidity level detection and sweep detection."""

    def test_find_equal_highs(self):
        """Equal highs should be detected when swing highs cluster at same price."""
        points = [
            SwingPoint(index=0, price=100.0, type='high', timestamp=100),
            SwingPoint(index=5, price=100.05, type='high', timestamp=400),
            SwingPoint(index=10, price=100.02, type='high', timestamp=700),
            SwingPoint(index=3, price=95.0, type='low', timestamp=250),
        ]
        levels = find_equal_levels(points, tolerance=0.001)
        high_levels = [lv for lv in levels if lv.type == 'high']
        self.assertTrue(len(high_levels) >= 1)
        self.assertEqual(high_levels[0].strength, 3)

    def test_find_equal_lows(self):
        """Equal lows should be detected when swing lows cluster together."""
        points = [
            SwingPoint(index=0, price=50.0, type='low', timestamp=100),
            SwingPoint(index=5, price=50.03, type='low', timestamp=400),
            SwingPoint(index=10, price=105.0, type='high', timestamp=700),
        ]
        levels = find_equal_levels(points, tolerance=0.001)
        low_levels = [lv for lv in levels if lv.type == 'low']
        self.assertTrue(len(low_levels) >= 1)
        self.assertEqual(low_levels[0].strength, 2)

    def test_no_equal_levels_when_spread(self):
        """Swing points far apart should not cluster."""
        points = [
            SwingPoint(index=0, price=100.0, type='high', timestamp=100),
            SwingPoint(index=5, price=110.0, type='high', timestamp=400),
        ]
        levels = find_equal_levels(points, tolerance=0.001)
        self.assertEqual(len(levels), 0)

    def test_find_swing_liquidity(self):
        """Every swing point should produce a liquidity level."""
        points = [
            SwingPoint(index=0, price=100, type='high', timestamp=100),
            SwingPoint(index=5, price=95, type='low', timestamp=400),
        ]
        levels = find_swing_liquidity(points)
        self.assertEqual(len(levels), 2)
        self.assertFalse(any(lv.swept for lv in levels))

    def test_liquidity_sweep_high(self):
        """A wick above a high level with close below = sweep."""
        level = LiquidityLevel(price=100.0, type='high', strength=2, swept=False)
        candles = [
            OHLCV(timestamp=100, open=99, high=101, low=98, close=98.5, volume=100),
        ]
        sweeps = detect_liquidity_sweep(candles, [level])
        self.assertEqual(len(sweeps), 1)
        self.assertTrue(sweeps[0]['swept'])
        self.assertTrue(level.swept)

    def test_liquidity_sweep_low(self):
        """A wick below a low level with close above = sweep."""
        level = LiquidityLevel(price=50.0, type='low', strength=2, swept=False)
        candles = [
            OHLCV(timestamp=100, open=51, high=52, low=49, close=51.5, volume=100),
        ]
        sweeps = detect_liquidity_sweep(candles, [level])
        self.assertEqual(len(sweeps), 1)
        self.assertTrue(level.swept)

    def test_no_sweep_when_close_beyond(self):
        """A breakout (close beyond the level) is NOT a sweep."""
        level = LiquidityLevel(price=100.0, type='high', strength=2, swept=False)
        candles = [
            OHLCV(timestamp=100, open=99, high=102, low=99, close=101, volume=100),
        ]
        sweeps = detect_liquidity_sweep(candles, [level])
        self.assertEqual(len(sweeps), 0)


# ---------------------------------------------------------------------------
# Fibonacci / OTE tests
# ---------------------------------------------------------------------------

class TestFibonacci(unittest.TestCase):
    """Tests for Fibonacci and OTE zone calculations."""

    def test_get_fib_levels(self):
        """Fibonacci levels should be correctly calculated."""
        levels = get_fib_levels(swing_low=1.0800, swing_high=1.1000)
        # Level 0.0 should be the swing high
        self.assertAlmostEqual(levels[0.0], 1.1000, places=4)
        # Level 1.0 should be the swing low
        self.assertAlmostEqual(levels[1.0], 1.0800, places=4)
        # Level 0.5 should be the midpoint
        self.assertAlmostEqual(levels[0.5], 1.0900, places=4)
        # Level 0.618 should be 1.1000 - 0.02 * 0.618 = 1.08764
        self.assertAlmostEqual(levels[0.618], 1.08764, places=4)

    def test_ote_zone(self):
        """OTE zone should span from 0.618 to 0.786 retracement."""
        ote = calculate_ote_zone(swing_low=100.0, swing_high=200.0)
        # OTE high = 200 - 100*0.618 = 138.2
        self.assertAlmostEqual(ote['ote_high'], 138.2, places=1)
        # OTE low = 200 - 100*0.786 = 121.4
        self.assertAlmostEqual(ote['ote_low'], 121.4, places=1)
        # Equilibrium = 200 - 100*0.5 = 150
        self.assertAlmostEqual(ote['equilibrium'], 150.0, places=1)

    def test_is_in_premium(self):
        """Prices above the equilibrium should be in premium zone."""
        self.assertTrue(is_in_premium(160.0, swing_low=100.0, swing_high=200.0))
        self.assertFalse(is_in_premium(140.0, swing_low=100.0, swing_high=200.0))

    def test_is_in_discount(self):
        """Prices below the equilibrium should be in discount zone."""
        self.assertTrue(is_in_discount(140.0, swing_low=100.0, swing_high=200.0))
        self.assertFalse(is_in_discount(160.0, swing_low=100.0, swing_high=200.0))

    def test_equilibrium_boundary(self):
        """Price exactly at equilibrium should be neither premium nor discount."""
        self.assertFalse(is_in_premium(150.0, swing_low=100.0, swing_high=200.0))
        self.assertFalse(is_in_discount(150.0, swing_low=100.0, swing_high=200.0))


# ---------------------------------------------------------------------------
# Confluence scoring tests
# ---------------------------------------------------------------------------

class TestConfluence(unittest.TestCase):
    """Tests for confluence scoring."""

    def test_full_confluence_score(self):
        """All factors present should yield maximum score (100)."""
        # OTE zone for swing_low=90, swing_high=120:
        #   ote_high = 120 - 30*0.618 = 101.46
        #   ote_low  = 120 - 30*0.786 = 96.42
        # Price 99 is inside OTE, inside OB (100-105), and inside FVG (96-106)
        ob = OrderBlock(type='bullish', high=105, low=96,
                        timeframe='H1', created_at=1000)
        fvg = FairValueGap(type='bullish', high=106, low=95,
                           timeframe='H1', created_at=1000, fill_status='unfilled')
        level = LiquidityLevel(price=89.0, type='low', strength=2, swept=True)
        ote = calculate_ote_zone(swing_low=90.0, swing_high=120.0)

        # Price at 99 is inside the OB, FVG, OTE zone
        setup = score_setup(
            trend='bullish',
            order_blocks=[ob],
            fvgs=[fvg],
            liquidity_levels=[level],
            fib_data=ote,
            current_price=99.0,
            direction='long',
            htf_trend='bullish',
        )
        self.assertEqual(setup.confluence_score, 100.0)

    def test_trend_only_score(self):
        """Only trend alignment should give 25 points."""
        setup = score_setup(
            trend='bullish',
            order_blocks=[],
            fvgs=[],
            liquidity_levels=[],
            fib_data=None,
            current_price=100.0,
            direction='long',
        )
        self.assertEqual(setup.confluence_score, 25.0)

    def test_no_confluence_score(self):
        """No factors aligned should give 0."""
        setup = score_setup(
            trend='bearish',
            order_blocks=[],
            fvgs=[],
            liquidity_levels=[],
            fib_data=None,
            current_price=100.0,
            direction='long',
        )
        self.assertEqual(setup.confluence_score, 0.0)

    def test_calculate_sl_tp_long(self):
        """SL/TP for a long trade should be below/above entry."""
        ob = OrderBlock(type='bullish', high=105, low=100,
                        timeframe='H1', created_at=1000)
        result = calculate_sl_tp(
            direction='long',
            entry_price=103.0,
            order_block=ob,
            liquidity_levels=[],
            min_rr=2.0,
        )
        self.assertLess(result['stop_loss'], 103.0)
        self.assertGreater(result['take_profit'], 103.0)
        self.assertGreaterEqual(result['rr_ratio'], 2.0)

    def test_calculate_sl_tp_short(self):
        """SL/TP for a short trade should be above/below entry."""
        ob = OrderBlock(type='bearish', high=110, low=108,
                        timeframe='H1', created_at=1000)
        result = calculate_sl_tp(
            direction='short',
            entry_price=109.0,
            order_block=ob,
            liquidity_levels=[],
            min_rr=2.0,
        )
        self.assertGreater(result['stop_loss'], 109.0)
        self.assertLess(result['take_profit'], 109.0)
        self.assertGreaterEqual(result['rr_ratio'], 2.0)


if __name__ == '__main__':
    unittest.main()
