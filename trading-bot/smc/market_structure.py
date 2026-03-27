"""
Market Structure Analysis for Smart Money Concepts (SMC).

Market structure is the foundation of SMC analysis. It identifies the
prevailing trend by analyzing the sequence of swing highs and swing lows:

- **Uptrend**: series of Higher Highs (HH) and Higher Lows (HL)
- **Downtrend**: series of Lower Highs (LH) and Lower Lows (LL)
- **Break of Structure (BOS)**: price closes beyond a prior swing point
  in the direction of the prevailing trend, confirming continuation.
- **Change of Character (CHoCH)**: the first break against the prevailing
  trend, signaling a potential trend reversal.

These concepts originate from ICT (Inner Circle Trader) methodology and
are widely used by institutional and retail traders alike.
"""

from typing import List

from .models import OHLCV, SwingPoint


def detect_swing_points(ohlcv_list: List[OHLCV], lookback: int = 5) -> List[SwingPoint]:
    """Identify swing highs and swing lows in price data.

    A swing high at index ``i`` requires that all ``lookback`` bars to the
    left AND all ``lookback`` bars to the right have strictly lower highs
    than the bar at ``i``.

    A swing low at index ``i`` requires that all ``lookback`` bars to the
    left AND all ``lookback`` bars to the right have strictly higher lows
    than the bar at ``i``.

    Args:
        ohlcv_list: Chronologically ordered OHLCV bars.
        lookback: Number of bars on each side required to confirm a swing.

    Returns:
        List of SwingPoint objects sorted by index.
    """
    if len(ohlcv_list) < 2 * lookback + 1:
        return []

    swing_points: List[SwingPoint] = []

    for i in range(lookback, len(ohlcv_list) - lookback):
        candle = ohlcv_list[i]

        # Check for swing high
        is_swing_high = True
        for j in range(1, lookback + 1):
            if ohlcv_list[i - j].high >= candle.high or ohlcv_list[i + j].high >= candle.high:
                is_swing_high = False
                break

        if is_swing_high:
            swing_points.append(SwingPoint(
                index=i,
                price=candle.high,
                type='high',
                timestamp=candle.timestamp,
            ))

        # Check for swing low
        is_swing_low = True
        for j in range(1, lookback + 1):
            if ohlcv_list[i - j].low <= candle.low or ohlcv_list[i + j].low <= candle.low:
                is_swing_low = False
                break

        if is_swing_low:
            swing_points.append(SwingPoint(
                index=i,
                price=candle.low,
                type='low',
                timestamp=candle.timestamp,
            ))

    swing_points.sort(key=lambda sp: sp.index)
    return swing_points


def classify_structure(swing_points: List[SwingPoint]) -> List[dict]:
    """Classify each swing point relative to the previous swing of the same type.

    Labels:
        - **HH** (Higher High): a swing high whose price exceeds the
          previous swing high.
        - **LH** (Lower High): a swing high below the previous swing high.
        - **HL** (Higher Low): a swing low above the previous swing low.
        - **LL** (Lower Low): a swing low below the previous swing low.

    The first swing high and first swing low have no prior reference and
    are labeled as ``None``.

    Args:
        swing_points: Ordered list of SwingPoint objects.

    Returns:
        List of dicts with keys: ``swing``, ``label``, ``index``, ``price``.
    """
    classifications: List[dict] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None

    for sp in swing_points:
        label = None

        if sp.type == 'high':
            if last_high is not None:
                label = 'HH' if sp.price > last_high.price else 'LH'
            last_high = sp
        else:
            if last_low is not None:
                label = 'HL' if sp.price > last_low.price else 'LL'
            last_low = sp

        classifications.append({
            'swing': sp,
            'label': label,
            'index': sp.index,
            'price': sp.price,
        })

    return classifications


def _get_prevailing_trend(classifications: List[dict]) -> str:
    """Determine the prevailing trend from the most recent classifications.

    Looks at the last swing high label and last swing low label to infer
    trend direction.
    """
    last_high_label = None
    last_low_label = None

    for c in reversed(classifications):
        if c['swing'].type == 'high' and last_high_label is None:
            last_high_label = c['label']
        elif c['swing'].type == 'low' and last_low_label is None:
            last_low_label = c['label']
        if last_high_label is not None and last_low_label is not None:
            break

    if last_high_label == 'HH' and last_low_label == 'HL':
        return 'bullish'
    elif last_high_label == 'LH' and last_low_label == 'LL':
        return 'bearish'
    return 'ranging'


def detect_bos(ohlcv: List[OHLCV], swing_points: List[SwingPoint]) -> List[dict]:
    """Detect Break of Structure (BOS) events.

    A BOS confirms trend continuation:

    - **Bullish BOS**: in an uptrend, price *closes* above a prior swing
      high, confirming bullish momentum.
    - **Bearish BOS**: in a downtrend, price *closes* below a prior swing
      low, confirming bearish momentum.

    The algorithm walks through candles after each swing point and checks
    whether subsequent closes break the swing level in the trend direction.

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        swing_points: Swing points detected from the same OHLCV data.

    Returns:
        List of dicts with keys: ``type``, ``price``, ``index``,
        ``broken_swing``.
    """
    if len(swing_points) < 3:
        return []

    classifications = classify_structure(swing_points)
    bos_events: List[dict] = []

    # Track the most recent swing highs and lows
    swing_highs = [sp for sp in swing_points if sp.type == 'high']
    swing_lows = [sp for sp in swing_points if sp.type == 'low']

    # For each swing high, check if a subsequent candle closes above it (bullish BOS)
    for i, sh in enumerate(swing_highs):
        # Determine local trend at this swing: need at least one prior high and low
        local_trend = _local_trend_at(classifications, sh.index)
        if local_trend != 'bullish':
            continue

        # Find the next swing after this one to bound the search
        end_idx = swing_highs[i + 1].index if i + 1 < len(swing_highs) else len(ohlcv)

        for bar_idx in range(sh.index + 1, min(end_idx, len(ohlcv))):
            if ohlcv[bar_idx].close > sh.price:
                bos_events.append({
                    'type': 'bullish',
                    'price': ohlcv[bar_idx].close,
                    'index': bar_idx,
                    'broken_swing': sh,
                })
                break

    # For each swing low, check if a subsequent candle closes below it (bearish BOS)
    for i, sl in enumerate(swing_lows):
        local_trend = _local_trend_at(classifications, sl.index)
        if local_trend != 'bearish':
            continue

        end_idx = swing_lows[i + 1].index if i + 1 < len(swing_lows) else len(ohlcv)

        for bar_idx in range(sl.index + 1, min(end_idx, len(ohlcv))):
            if ohlcv[bar_idx].close < sl.price:
                bos_events.append({
                    'type': 'bearish',
                    'price': ohlcv[bar_idx].close,
                    'index': bar_idx,
                    'broken_swing': sl,
                })
                break

    bos_events.sort(key=lambda e: e['index'])
    return bos_events


def _local_trend_at(classifications: List[dict], up_to_index: int) -> str:
    """Determine trend from classifications up to a given bar index."""
    relevant = [c for c in classifications if c['index'] <= up_to_index]

    last_high_label = None
    last_low_label = None

    for c in reversed(relevant):
        if c['swing'].type == 'high' and last_high_label is None:
            last_high_label = c['label']
        elif c['swing'].type == 'low' and last_low_label is None:
            last_low_label = c['label']
        if last_high_label is not None and last_low_label is not None:
            break

    if last_high_label == 'HH' and last_low_label in ('HL', None):
        return 'bullish'
    if last_high_label in ('LH', None) and last_low_label == 'LL':
        return 'bearish'
    # Single-sided checks
    if last_high_label == 'HH':
        return 'bullish'
    if last_low_label == 'LL':
        return 'bearish'
    return 'ranging'


def detect_choch(ohlcv: List[OHLCV], swing_points: List[SwingPoint]) -> List[dict]:
    """Detect Change of Character (CHoCH) events.

    A CHoCH is the *first* break against the prevailing trend, signaling
    a potential reversal:

    - **Bullish CHoCH**: during a downtrend (LH/LL sequence), price closes
      above a prior swing high for the first time.
    - **Bearish CHoCH**: during an uptrend (HH/HL sequence), price closes
      below a prior swing low for the first time.

    CHoCH events are high-value signals because they mark the earliest
    detectable shift in institutional order flow.

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        swing_points: Swing points detected from the same OHLCV data.

    Returns:
        List of dicts with keys: ``type``, ``price``, ``index``.
    """
    if len(swing_points) < 3:
        return []

    classifications = classify_structure(swing_points)
    choch_events: List[dict] = []

    swing_highs = [sp for sp in swing_points if sp.type == 'high']
    swing_lows = [sp for sp in swing_points if sp.type == 'low']

    # Bullish CHoCH: in a bearish trend, close above a swing high
    for i, sh in enumerate(swing_highs):
        local_trend = _local_trend_at(classifications, sh.index)
        if local_trend != 'bearish':
            continue

        end_idx = swing_highs[i + 1].index if i + 1 < len(swing_highs) else len(ohlcv)

        for bar_idx in range(sh.index + 1, min(end_idx, len(ohlcv))):
            if ohlcv[bar_idx].close > sh.price:
                choch_events.append({
                    'type': 'bullish',
                    'price': ohlcv[bar_idx].close,
                    'index': bar_idx,
                })
                break

    # Bearish CHoCH: in a bullish trend, close below a swing low
    for i, sl in enumerate(swing_lows):
        local_trend = _local_trend_at(classifications, sl.index)
        if local_trend != 'bullish':
            continue

        end_idx = swing_lows[i + 1].index if i + 1 < len(swing_lows) else len(ohlcv)

        for bar_idx in range(sl.index + 1, min(end_idx, len(ohlcv))):
            if ohlcv[bar_idx].close < sl.price:
                choch_events.append({
                    'type': 'bearish',
                    'price': ohlcv[bar_idx].close,
                    'index': bar_idx,
                })
                break

    choch_events.sort(key=lambda e: e['index'])
    return choch_events


def get_trend(swing_points: List[SwingPoint]) -> str:
    """Determine the current market trend from swing point structure.

    Examines the most recent swing high and swing low classifications:

    - ``'bullish'``: last swing high is HH and last swing low is HL.
    - ``'bearish'``: last swing high is LH and last swing low is LL.
    - ``'ranging'``: mixed signals or insufficient data.

    Args:
        swing_points: Ordered list of SwingPoint objects.

    Returns:
        One of ``'bullish'``, ``'bearish'``, or ``'ranging'``.
    """
    if len(swing_points) < 4:
        return 'ranging'

    classifications = classify_structure(swing_points)
    return _get_prevailing_trend(classifications)
