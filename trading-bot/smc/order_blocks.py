"""Order Block (OB) identification and management.

Order blocks are institutional footprints left in price action. They represent
zones where large market participants (banks, hedge funds) placed significant
orders that caused an impulsive move (Break of Structure).

Key concepts:
    - **Bullish OB**: The last bearish (down) candle before a bullish BOS move.
      This zone acted as the launch pad for the impulsive rally and often
      serves as future support when price returns to it.
    - **Bearish OB**: The last bullish (up) candle before a bearish BOS move.
      This zone marks where selling pressure overwhelmed buyers and often
      acts as future resistance.
    - **Mitigation**: An OB is considered mitigated (used up) when price has
      traded back through the entire zone, meaning the resting orders have
      been filled. Mitigated OBs lose their significance.

Usage:
    >>> bos_list = detect_bos(ohlcv, swing_points)
    >>> obs = find_order_blocks(ohlcv, bos_list, lookback=20)
    >>> for ob in obs:
    ...     if not check_mitigation(ob, ohlcv):
    ...         print(f"Active {ob.type} OB: {ob.low:.2f} - {ob.high:.2f}")
"""

from typing import List

from .models import OHLCV, OrderBlock


def find_order_blocks(
    ohlcv: List[OHLCV],
    bos_list: List[dict],
    lookback: int = 20,
) -> List[OrderBlock]:
    """Identify order blocks associated with Break of Structure events.

    For each BOS event, this function scans backward up to ``lookback`` bars
    to find the last opposite-color candle before the impulsive move:

    - For a bullish BOS: find the last bearish candle (close < open) in the
      lookback window before the BOS bar. The OB zone spans the candle body
      (low = min(open, close), high = max(open, close)).
    - For a bearish BOS: find the last bullish candle (close > open).

    Only the most recent unmitigated OB of each type is kept to avoid
    cluttering the signal space with stale zones.

    Args:
        ohlcv: Chronologically ordered OHLCV bars.
        bos_list: BOS events from ``detect_bos()``. Each dict must contain
            ``type`` ('bullish'/'bearish') and ``index`` (bar index).
        lookback: Maximum number of bars to search backward from the BOS
            event to find the order block candle.

    Returns:
        List of OrderBlock objects, sorted by creation time (ascending).
    """
    if not ohlcv or not bos_list:
        return []

    order_blocks: List[OrderBlock] = []

    for bos in bos_list:
        bos_type: str = bos['type']
        bos_index: int = bos['index']

        # Search backward from the BOS bar for the originating candle
        search_start = max(0, bos_index - lookback)
        ob_candle_idx = _find_ob_candle(ohlcv, bos_type, bos_index, search_start)

        if ob_candle_idx is None:
            continue

        candle = ohlcv[ob_candle_idx]

        # OB zone is the candle body (not the wicks)
        body_high = max(candle.open, candle.close)
        body_low = min(candle.open, candle.close)

        ob = OrderBlock(
            type=bos_type,
            high=body_high,
            low=body_low,
            timeframe='',  # Set by caller based on data timeframe
            created_at=candle.timestamp,
            mitigated=False,
        )

        order_blocks.append(ob)

    # Remove mitigated OBs by checking price action after creation
    active_obs = _filter_unmitigated(order_blocks, ohlcv)

    # Keep only the most recent unmitigated OB per type
    result = _keep_most_recent(active_obs)
    result.sort(key=lambda ob: ob.created_at)

    return result


def _find_ob_candle(
    ohlcv: List[OHLCV],
    bos_type: str,
    bos_index: int,
    search_start: int,
) -> int | None:
    """Find the last opposite-color candle before a BOS event.

    For a bullish BOS, look for the last bearish candle (close < open).
    For a bearish BOS, look for the last bullish candle (close > open).

    Scans backward from one bar before the BOS bar.
    """
    for i in range(bos_index - 1, search_start - 1, -1):
        if i < 0:
            break
        candle = ohlcv[i]

        if bos_type == 'bullish' and candle.close < candle.open:
            # Found a bearish candle before bullish BOS
            return i
        elif bos_type == 'bearish' and candle.close > candle.open:
            # Found a bullish candle before bearish BOS
            return i

    return None


def _filter_unmitigated(
    order_blocks: List[OrderBlock],
    ohlcv: List[OHLCV],
) -> List[OrderBlock]:
    """Remove order blocks that have been mitigated by subsequent price action."""
    active: List[OrderBlock] = []

    for ob in order_blocks:
        if not check_mitigation(ob, ohlcv):
            active.append(ob)
        else:
            ob.mitigated = True

    return active


def _keep_most_recent(order_blocks: List[OrderBlock]) -> List[OrderBlock]:
    """Keep only the most recent OB of each type (bullish/bearish).

    In practice, the most recent unmitigated OB is the most relevant for
    trade entry decisions. Older OBs of the same type are superseded.
    """
    latest_bullish: OrderBlock | None = None
    latest_bearish: OrderBlock | None = None

    for ob in order_blocks:
        if ob.type == 'bullish':
            if latest_bullish is None or ob.created_at > latest_bullish.created_at:
                latest_bullish = ob
        else:
            if latest_bearish is None or ob.created_at > latest_bearish.created_at:
                latest_bearish = ob

    result: List[OrderBlock] = []
    if latest_bullish is not None:
        result.append(latest_bullish)
    if latest_bearish is not None:
        result.append(latest_bearish)

    return result


def check_mitigation(ob: OrderBlock, ohlcv: List[OHLCV]) -> bool:
    """Check whether an order block has been mitigated by price action.

    Mitigation means price has traded through the entire OB zone, implying
    that the resting institutional orders have been filled:

    - **Bullish OB mitigated**: a candle closes below the OB's low boundary.
      This indicates the support zone has been broken.
    - **Bearish OB mitigated**: a candle closes above the OB's high boundary.
      This indicates the resistance zone has been broken.

    Only candles after the OB creation time are considered.

    Args:
        ob: The OrderBlock to check.
        ohlcv: Full OHLCV data series.

    Returns:
        True if the OB has been mitigated, False if it is still active.
    """
    for candle in ohlcv:
        if candle.timestamp <= ob.created_at:
            continue

        if ob.type == 'bullish' and candle.close < ob.low:
            return True
        elif ob.type == 'bearish' and candle.close > ob.high:
            return True

    return False


def is_price_in_ob(price: float, ob: OrderBlock) -> bool:
    """Check if a price is within an order block zone.

    Args:
        price: The price level to check.
        ob: The OrderBlock zone.

    Returns:
        True if the price is between the OB's low and high (inclusive).
    """
    return ob.low <= price <= ob.high
