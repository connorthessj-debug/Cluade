"""Background macro/regime monitor — polls fetch_fred.py periodically."""

import asyncio
from .scanner import run_fetch_script

REFRESH_SECONDS = 900  # 15 minutes


async def get_macro_snapshot() -> dict:
    """One-shot fetch of macro indicators from fetch_fred.py."""
    return await run_fetch_script("fetch_fred.py")


def classify_regime(regime_indicators: dict) -> str:
    """Derive regime label from FRED indicators."""
    if not regime_indicators:
        return "UNKNOWN"
    derived = regime_indicators.get("derived_regime")
    if derived:
        return derived

    spread = regime_indicators.get("yield_spread_10y2y_bps")
    cpi = regime_indicators.get("cpi_yoy_pct")
    hy = regime_indicators.get("hy_spread_bps")
    breakeven = regime_indicators.get("breakeven_inflation_pct")

    growth_up = (spread is not None and spread > 0) and (hy is None or hy < 500)
    inflation_up = (cpi is not None and cpi > 3.0) or (breakeven is not None and breakeven > 2.5)

    if growth_up and not inflation_up:
        return "GOLDILOCKS"
    if growth_up and inflation_up:
        return "REFLATION"
    if (not growth_up) and inflation_up:
        return "STAGFLATION"
    return "RISK-OFF"
