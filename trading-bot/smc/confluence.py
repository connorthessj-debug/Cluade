"""Multi-factor confluence scoring and trade setup generation.

Confluence scoring combines multiple SMC signals into a single probability
score (0-100) for a potential trade. Higher scores indicate that more
institutional footprints align at the entry zone, increasing the likelihood
of a successful trade.

Scoring breakdown (0-100):
    - Trend alignment (market structure matches trade direction): +25
    - Order block at entry zone:                                  +20
    - Fair Value Gap at entry zone:                                +15
    - Price in OTE (Optimal Trade Entry) zone:                     +15
    - Liquidity swept before entry:                                +15
    - Higher timeframe confirmation:                               +10

Usage:
    >>> setup = score_setup(
    ...     trend='bullish',
    ...     order_blocks=obs,
    ...     fvgs=fvgs,
    ...     liquidity_levels=levels,
    ...     fib_data=ote_zone,
    ...     current_price=49200.0,
    ...     direction='long',
    ... )
    >>> if setup.confluence_score >= 60:
    ...     entry = find_entry('long', obs, fvgs, ote_zone, current_price)
    ...     sl_tp = calculate_sl_tp('long', entry['entry_price'], ob, levels)
"""

from typing import Any, Dict, List, Optional, Tuple

from .models import (
    OHLCV,
    FairValueGap,
    LiquidityLevel,
    OrderBlock,
    SwingPoint,
    TradeSetup,
)


# ---------------------------------------------------------------------------
# Score weights
# ---------------------------------------------------------------------------
_WEIGHT_TREND = 25
_WEIGHT_ORDER_BLOCK = 20
_WEIGHT_FVG = 15
_WEIGHT_OTE = 15
_WEIGHT_LIQUIDITY_SWEEP = 15
_WEIGHT_HTF_CONFIRMATION = 10


def score_setup(
    trend: str,
    order_blocks: List[OrderBlock],
    fvgs: List[FairValueGap],
    liquidity_levels: List[LiquidityLevel],
    fib_data: Optional[dict],
    current_price: float,
    direction: str,
    htf_trend: Optional[str] = None,
) -> TradeSetup:
    """Score a potential trade setup based on SMC confluence factors.

    Evaluates how many independent SMC signals align at the current price
    and trade direction. Each factor contributes points toward a maximum
    score of 100.

    Scoring:
        - Trend alignment (+25): Market structure (HH/HL or LH/LL) matches
          the intended trade direction. Trading with the trend is the single
          most important factor.
        - Order block at entry (+20): Price is sitting inside an unmitigated
          order block of the correct type (bullish OB for longs, bearish OB
          for shorts). This confirms institutional interest at the level.
        - FVG at entry (+15): Price is within a fair value gap, indicating
          an inefficiency that price is likely to respect.
        - OTE zone (+15): Price is in the 0.618-0.786 Fibonacci retracement
          zone, the highest-probability entry area.
        - Liquidity swept (+15): A liquidity sweep has occurred in the
          expected direction (sell-side swept for longs, buy-side swept for
          shorts), confirming smart money accumulation/distribution.
        - HTF confirmation (+10): The higher-timeframe trend aligns with the
          trade direction, providing structural backing.

    Args:
        trend: Current market structure trend ('bullish', 'bearish', 'ranging').
        order_blocks: Active (unmitigated) order blocks.
        fvgs: Active fair value gaps.
        liquidity_levels: Known liquidity levels (with sweep status).
        fib_data: OTE zone dict from ``calculate_ote_zone()`` with keys
            ``ote_high``, ``ote_low``. Pass None if unavailable.
        current_price: The current market price.
        direction: Intended trade direction ('long' or 'short').
        htf_trend: Optional higher-timeframe trend for confirmation.
            Pass the trend string from a higher timeframe analysis.

    Returns:
        A TradeSetup with the confluence score and component breakdown.
        Entry, stop loss, and take profit are initialized to 0.0; refine
        them using ``find_entry()`` and ``calculate_sl_tp()``.
    """
    score = 0.0
    components: Dict[str, Any] = {}

    # 1. Trend alignment (+25)
    trend_aligned = _check_trend_alignment(trend, direction)
    if trend_aligned:
        score += _WEIGHT_TREND
    components['trend_alignment'] = {
        'aligned': trend_aligned,
        'trend': trend,
        'direction': direction,
        'score': _WEIGHT_TREND if trend_aligned else 0,
    }

    # 2. Order block at entry zone (+20)
    matching_ob = _find_matching_ob(order_blocks, current_price, direction)
    ob_present = matching_ob is not None
    if ob_present:
        score += _WEIGHT_ORDER_BLOCK
    components['order_block'] = {
        'present': ob_present,
        'ob': matching_ob,
        'score': _WEIGHT_ORDER_BLOCK if ob_present else 0,
    }

    # 3. FVG at entry zone (+15)
    matching_fvg = _find_matching_fvg(fvgs, current_price, direction)
    fvg_present = matching_fvg is not None
    if fvg_present:
        score += _WEIGHT_FVG
    components['fvg'] = {
        'present': fvg_present,
        'fvg': matching_fvg,
        'score': _WEIGHT_FVG if fvg_present else 0,
    }

    # 4. Price in OTE zone (+15)
    in_ote = _check_ote(fib_data, current_price)
    if in_ote:
        score += _WEIGHT_OTE
    components['ote_zone'] = {
        'in_ote': in_ote,
        'fib_data': fib_data,
        'score': _WEIGHT_OTE if in_ote else 0,
    }

    # 5. Liquidity swept before entry (+15)
    swept = _check_liquidity_swept(liquidity_levels, direction)
    if swept:
        score += _WEIGHT_LIQUIDITY_SWEEP
    components['liquidity_sweep'] = {
        'swept': swept,
        'score': _WEIGHT_LIQUIDITY_SWEEP if swept else 0,
    }

    # 6. Higher timeframe confirmation (+10)
    htf_confirmed = _check_htf_confirmation(htf_trend, direction)
    if htf_confirmed:
        score += _WEIGHT_HTF_CONFIRMATION
    components['htf_confirmation'] = {
        'confirmed': htf_confirmed,
        'htf_trend': htf_trend,
        'score': _WEIGHT_HTF_CONFIRMATION if htf_confirmed else 0,
    }

    return TradeSetup(
        signal_type='smc_confluence',
        direction=direction,
        entry_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        confluence_score=min(score, 100.0),
        components=components,
    )


def find_entry(
    direction: str,
    order_blocks: List[OrderBlock],
    fvgs: List[FairValueGap],
    fib_data: Optional[dict],
    current_price: float,
) -> dict:
    """Find the optimal entry price based on confluence of OB + FVG + OTE.

    The best entry sits where multiple institutional zones overlap. This
    function identifies candidate zones and selects the one with the highest
    confluence, breaking ties by proximity to the current price.

    Priority (highest to lowest):
        1. OB + FVG overlap inside OTE zone (triple confluence).
        2. OB + FVG overlap (double confluence).
        3. OB inside OTE zone.
        4. FVG inside OTE zone.
        5. Standalone order block.
        6. Standalone fair value gap.
        7. OTE zone midpoint.
        8. Fallback to current market price.

    For long entries, lower prices are preferred (buy cheap in discount).
    For short entries, higher prices are preferred (sell expensive in premium).

    Args:
        direction: 'long' or 'short'.
        order_blocks: Active (unmitigated) order blocks.
        fvgs: Active fair value gaps.
        fib_data: OTE zone dict with ``ote_high`` and ``ote_low`` keys,
            or None if unavailable.
        current_price: Current market price.

    Returns:
        Dict with keys:
            - ``entry_price``: Recommended entry price.
            - ``zone_type``: Description of the entry zone confluence.
            - ``zone_high``: Upper boundary of the entry zone.
            - ``zone_low``: Lower boundary of the entry zone.
    """
    relevant_obs = _get_relevant_obs(order_blocks, direction)
    relevant_fvgs = _get_relevant_fvgs(fvgs, direction)

    ote_high = fib_data['ote_high'] if fib_data else None
    ote_low = fib_data['ote_low'] if fib_data else None

    candidates: List[dict] = []

    # 1. OB + FVG overlap inside OTE (triple confluence)
    for ob in relevant_obs:
        for fvg in relevant_fvgs:
            overlap = _get_overlap(ob.low, ob.high, fvg.low, fvg.high)
            if overlap is not None:
                o_low, o_high = overlap
                if ote_high is not None and ote_low is not None:
                    ote_overlap = _get_overlap(o_low, o_high, ote_low, ote_high)
                    if ote_overlap is not None:
                        candidates.append({
                            'entry_price': (ote_overlap[0] + ote_overlap[1]) / 2,
                            'zone_type': 'ob_fvg_ote_confluence',
                            'zone_high': ote_overlap[1],
                            'zone_low': ote_overlap[0],
                            'priority': 1,
                        })
                # 2. OB + FVG overlap (no OTE)
                candidates.append({
                    'entry_price': (o_low + o_high) / 2,
                    'zone_type': 'ob_fvg_overlap',
                    'zone_high': o_high,
                    'zone_low': o_low,
                    'priority': 2,
                })

    # 3. OB inside OTE
    if ote_high is not None and ote_low is not None:
        for ob in relevant_obs:
            overlap = _get_overlap(ob.low, ob.high, ote_low, ote_high)
            if overlap is not None:
                candidates.append({
                    'entry_price': (overlap[0] + overlap[1]) / 2,
                    'zone_type': 'ob_in_ote',
                    'zone_high': overlap[1],
                    'zone_low': overlap[0],
                    'priority': 3,
                })

        # 4. FVG inside OTE
        for fvg in relevant_fvgs:
            overlap = _get_overlap(fvg.low, fvg.high, ote_low, ote_high)
            if overlap is not None:
                candidates.append({
                    'entry_price': (overlap[0] + overlap[1]) / 2,
                    'zone_type': 'fvg_in_ote',
                    'zone_high': overlap[1],
                    'zone_low': overlap[0],
                    'priority': 4,
                })

    # 5. Standalone OB
    for ob in relevant_obs:
        candidates.append({
            'entry_price': (ob.low + ob.high) / 2,
            'zone_type': 'order_block',
            'zone_high': ob.high,
            'zone_low': ob.low,
            'priority': 5,
        })

    # 6. Standalone FVG
    for fvg in relevant_fvgs:
        candidates.append({
            'entry_price': (fvg.low + fvg.high) / 2,
            'zone_type': 'fair_value_gap',
            'zone_high': fvg.high,
            'zone_low': fvg.low,
            'priority': 6,
        })

    # 7. OTE zone midpoint
    if ote_high is not None and ote_low is not None:
        candidates.append({
            'entry_price': (ote_low + ote_high) / 2,
            'zone_type': 'ote_zone',
            'zone_high': ote_high,
            'zone_low': ote_low,
            'priority': 7,
        })

    if not candidates:
        return {
            'entry_price': current_price,
            'zone_type': 'market_price',
            'zone_high': current_price,
            'zone_low': current_price,
        }

    # Sort by priority first, then by proximity to current price
    candidates.sort(
        key=lambda c: (c['priority'], abs(c['entry_price'] - current_price))
    )

    best = candidates[0]
    return {
        'entry_price': best['entry_price'],
        'zone_type': best['zone_type'],
        'zone_high': best['zone_high'],
        'zone_low': best['zone_low'],
    }


def calculate_sl_tp(
    direction: str,
    entry_price: float,
    order_block: Optional[OrderBlock],
    liquidity_levels: List[LiquidityLevel],
    min_rr: float = 2.0,
    buffer_pct: float = 0.001,
) -> dict:
    """Calculate stop loss and take profit levels for a trade setup.

    Stop loss placement:
        - For longs: placed below the order block low with a small buffer
          to avoid getting stopped on a wick that merely tests the OB.
          Falls back to the nearest swing low liquidity below entry.
        - For shorts: placed above the order block high with buffer.
          Falls back to the nearest swing high liquidity above entry.

    Take profit placement:
        - Targets the next unswept liquidity level in the trade direction.
        - For longs: the nearest unswept high-side liquidity above entry
          (buy-stop liquidity that price is expected to seek).
        - For shorts: the nearest unswept low-side liquidity below entry
          (sell-stop liquidity that price is expected to seek).
        - If the resulting R:R ratio is below ``min_rr``, the TP is
          extended to satisfy the minimum requirement.

    Args:
        direction: 'long' or 'short'.
        entry_price: The planned entry price.
        order_block: The order block used for the trade (for SL placement).
            Pass None if no OB is available.
        liquidity_levels: Known liquidity levels for TP targeting.
        min_rr: Minimum required reward-to-risk ratio. Default is 2.0 (2R).
        buffer_pct: Buffer added beyond the SL level as a fraction of the
            entry price. Default is 0.1% (0.001).

    Returns:
        Dict with keys:
            - ``stop_loss``: The stop loss price.
            - ``take_profit``: The take profit price.
            - ``risk``: Absolute distance from entry to SL.
            - ``reward``: Absolute distance from entry to TP.
            - ``rr_ratio``: The reward-to-risk ratio.
    """
    buffer = entry_price * buffer_pct

    # --- Stop Loss ---
    stop_loss = _calculate_stop_loss(
        direction, entry_price, order_block, liquidity_levels, buffer,
    )

    # --- Take Profit ---
    take_profit = _calculate_take_profit(
        direction, entry_price, liquidity_levels,
    )

    # Calculate risk and reward
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)

    # Enforce minimum R:R ratio
    if risk > 0 and (reward / risk) < min_rr:
        min_reward = risk * min_rr
        if direction == 'long':
            take_profit = entry_price + min_reward
        else:
            take_profit = entry_price - min_reward
        reward = min_reward

    rr_ratio = reward / risk if risk > 0 else 0.0

    return {
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'risk': risk,
        'reward': reward,
        'rr_ratio': rr_ratio,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_trend_alignment(trend: str, direction: str) -> bool:
    """Check if the market structure trend aligns with trade direction."""
    if direction == 'long' and trend == 'bullish':
        return True
    if direction == 'short' and trend == 'bearish':
        return True
    return False


def _find_matching_ob(
    order_blocks: List[OrderBlock],
    price: float,
    direction: str,
) -> Optional[OrderBlock]:
    """Find an unmitigated order block containing the current price."""
    target_type = 'bullish' if direction == 'long' else 'bearish'
    for ob in order_blocks:
        if ob.mitigated:
            continue
        if ob.type == target_type and ob.low <= price <= ob.high:
            return ob
    return None


def _find_matching_fvg(
    fvgs: List[FairValueGap],
    price: float,
    direction: str,
) -> Optional[FairValueGap]:
    """Find a FVG containing the current price matching the trade direction."""
    target_type = 'bullish' if direction == 'long' else 'bearish'
    for fvg in fvgs:
        if fvg.fill_status == 'filled':
            continue
        if fvg.type == target_type and fvg.low <= price <= fvg.high:
            return fvg
    return None


def _check_ote(fib_data: Optional[dict], price: float) -> bool:
    """Check if price is within the OTE zone."""
    if fib_data is None:
        return False
    ote_low = fib_data.get('ote_low')
    ote_high = fib_data.get('ote_high')
    if ote_low is None or ote_high is None:
        return False
    return ote_low <= price <= ote_high


def _check_liquidity_swept(
    liquidity_levels: List[LiquidityLevel],
    direction: str,
) -> bool:
    """Check if liquidity has been swept in the expected direction.

    For long entries, sell-side liquidity (below swing lows) should have been
    swept -- this confirms smart money accumulated after hunting stops.
    For short entries, buy-side liquidity (above swing highs) should be swept.
    """
    for level in liquidity_levels:
        if not level.swept:
            continue
        if direction == 'long' and level.type == 'low':
            return True
        if direction == 'short' and level.type == 'high':
            return True
    return False


def _check_htf_confirmation(htf_trend: Optional[str], direction: str) -> bool:
    """Check if the higher-timeframe trend confirms the trade direction."""
    if htf_trend is None:
        return False
    if direction == 'long' and htf_trend == 'bullish':
        return True
    if direction == 'short' and htf_trend == 'bearish':
        return True
    return False


def _get_relevant_obs(
    order_blocks: List[OrderBlock],
    direction: str,
) -> List[OrderBlock]:
    """Filter order blocks relevant to the trade direction."""
    target_type = 'bullish' if direction == 'long' else 'bearish'
    return [ob for ob in order_blocks if ob.type == target_type and not ob.mitigated]


def _get_relevant_fvgs(
    fvgs: List[FairValueGap],
    direction: str,
) -> List[FairValueGap]:
    """Filter FVGs relevant to the trade direction."""
    target_type = 'bullish' if direction == 'long' else 'bearish'
    return [
        fvg for fvg in fvgs
        if fvg.type == target_type and fvg.fill_status != 'filled'
    ]


def _get_overlap(
    low1: float,
    high1: float,
    low2: float,
    high2: float,
) -> Optional[Tuple[float, float]]:
    """Calculate the overlap between two price ranges.

    Returns:
        Tuple (overlap_low, overlap_high) if ranges overlap, None otherwise.
    """
    overlap_low = max(low1, low2)
    overlap_high = min(high1, high2)
    if overlap_low < overlap_high:
        return (overlap_low, overlap_high)
    return None


def _calculate_stop_loss(
    direction: str,
    entry_price: float,
    order_block: Optional[OrderBlock],
    liquidity_levels: List[LiquidityLevel],
    buffer: float,
) -> float:
    """Determine the stop loss price.

    Places SL beyond the order block boundary (with buffer), or falls back
    to the nearest relevant liquidity level. Last resort uses 2% from entry.
    """
    if direction == 'long':
        if order_block is not None:
            return order_block.low - buffer
        # Fallback: nearest swing low below entry
        lows_below = [
            lv.price for lv in liquidity_levels
            if lv.type == 'low' and lv.price < entry_price
        ]
        if lows_below:
            return max(lows_below) - buffer
        return entry_price * 0.98

    else:
        if order_block is not None:
            return order_block.high + buffer
        # Fallback: nearest swing high above entry
        highs_above = [
            lv.price for lv in liquidity_levels
            if lv.type == 'high' and lv.price > entry_price
        ]
        if highs_above:
            return min(highs_above) + buffer
        return entry_price * 1.02


def _calculate_take_profit(
    direction: str,
    entry_price: float,
    liquidity_levels: List[LiquidityLevel],
) -> float:
    """Determine the take profit price.

    Targets the next unswept liquidity level in the trade direction.
    Falls back to 4% from entry if no targets are available.
    """
    if direction == 'long':
        targets = [
            lv.price for lv in liquidity_levels
            if lv.type == 'high' and lv.price > entry_price and not lv.swept
        ]
        if targets:
            return min(targets)
        return entry_price * 1.04

    else:
        targets = [
            lv.price for lv in liquidity_levels
            if lv.type == 'low' and lv.price < entry_price and not lv.swept
        ]
        if targets:
            return max(targets)
        return entry_price * 0.96
