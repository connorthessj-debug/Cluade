"""
Instrument configurations — tick sizes, point values, commissions, session hours,
and Yahoo Finance ticker mappings.
"""

INSTRUMENTS = {
    "mnq": {
        "name": "Mini Nasdaq 100 Futures",
        "symbol": "NQ=F",
        "tick_size": 0.25,
        "point_value": 2.0,
        "commission": 0.62,
        "slippage_ticks": 2,
        "spread": 0.25,
        "min_volume": 0,
        "sessStartHour": 9,
        "sessStartMin": 30,
        "sessEndHour": 16,
        "sessEndMin": 0,
    },
    "gold": {
        "name": "Gold Futures",
        "symbol": "GC=F",
        "tick_size": 0.10,
        "point_value": 10.0,
        "commission": 1.25,
        "slippage_ticks": 2,
        "spread": 0.30,
        "min_volume": 0,
        "sessStartHour": 8,
        "sessStartMin": 0,
        "sessEndHour": 17,
        "sessEndMin": 0,
    },
    "es": {
        "name": "E-mini S&P 500 Futures",
        "symbol": "ES=F",
        "tick_size": 0.25,
        "point_value": 12.5,
        "commission": 1.18,
        "slippage_ticks": 1,
        "spread": 0.25,
        "min_volume": 0,
        "sessStartHour": 9,
        "sessStartMin": 30,
        "sessEndHour": 16,
        "sessEndMin": 0,
    },
    "oil": {
        "name": "Crude Oil Futures",
        "symbol": "CL=F",
        "tick_size": 0.01,
        "point_value": 10.0,
        "commission": 1.25,
        "slippage_ticks": 2,
        "spread": 0.03,
        "min_volume": 0,
        "sessStartHour": 9,
        "sessStartMin": 0,
        "sessEndHour": 14,
        "sessEndMin": 30,
    },
    "eurusd": {
        "name": "EUR/USD",
        "symbol": "EURUSD=X",
        "tick_size": 0.0001,
        "point_value": 100000.0,
        "commission": 0.50,
        "slippage_ticks": 1,
        "spread": 0.00010,
        "min_volume": 0,
        "sessStartHour": 8,
        "sessStartMin": 0,
        "sessEndHour": 17,
        "sessEndMin": 0,
    },
    "btc": {
        "name": "Bitcoin Futures",
        "symbol": "BTC=F",
        "tick_size": 5.0,
        "point_value": 5.0,
        "commission": 5.00,
        "slippage_ticks": 1,
        "spread": 15.0,
        "min_volume": 0,
        "sessStartHour": 0,
        "sessStartMin": 0,
        "sessEndHour": 23,
        "sessEndMin": 59,
    },
}

# Trading style default overrides
STYLE_DEFAULTS = {
    "smc_swing": {
        "swingLen": 5,
        "structureLen": 50,
        "obMaxAge": 100,
        "obMitigateBody": True,
        "obMaxCount": 10,
        "fvgEnabled": True,
        "fvgMinSize": 0.5,
        "fvgMaxAge": 50,
        "liqEnabled": True,
        "eqTolerance": 0.1,
        "liqLookback": 20,
        "pdLookback": 50,
        "htfBars": 16,
        "htfSwingLen": 5,
        "atrPeriod": 14,
        "atrSlMult": 1.5,
        "rrRatio": 2.0,
        "useTrailing": True,
        "trailAfterR": 1.0,
        "sessEnabled": True,
        "maxDailyTrades": 3,
    },
    "scalping": {
        "swingLen": 3,
        "structureLen": 20,
        "obMaxAge": 30,
        "obMitigateBody": True,
        "obMaxCount": 15,
        "fvgEnabled": True,
        "fvgMinSize": 0.1,
        "fvgMaxAge": 15,
        "liqEnabled": True,
        "eqTolerance": 0.05,
        "liqLookback": 10,
        "pdLookback": 20,
        "htfBars": 4,
        "htfSwingLen": 3,
        "atrPeriod": 10,
        "atrSlMult": 0.7,
        "rrRatio": 1.2,
        "useTrailing": False,
        "trailAfterR": 0.5,
        "sessEnabled": True,
        "maxDailyTrades": 8,
    },
}


def get_params(instrument: str, style: str = "smc_swing") -> dict:
    """
    Build a complete parameter dict for a given instrument and trading style.

    Args:
        instrument: Key from INSTRUMENTS (e.g. "mnq", "gold")
        style: Key from STYLE_DEFAULTS (e.g. "smc_swing", "scalping")

    Returns:
        Complete parameter dict ready for SMCEngine
    """
    if instrument not in INSTRUMENTS:
        raise ValueError(f"Unknown instrument: {instrument}. Available: {list(INSTRUMENTS.keys())}")
    if style not in STYLE_DEFAULTS:
        raise ValueError(f"Unknown style: {style}. Available: {list(STYLE_DEFAULTS.keys())}")

    inst = INSTRUMENTS[instrument]
    params = {**STYLE_DEFAULTS[style]}

    # Apply instrument-specific values
    params["tick_size"] = inst["tick_size"]
    params["point_value"] = inst["point_value"]
    params["commission"] = inst["commission"]
    params["slippage_ticks"] = inst["slippage_ticks"]
    params["spread"] = inst.get("spread", 0.0)
    params["min_volume"] = inst.get("min_volume", 0)
    params["sessStartHour"] = inst["sessStartHour"]
    params["sessStartMin"] = inst["sessStartMin"]
    params["sessEndHour"] = inst["sessEndHour"]
    params["sessEndMin"] = inst["sessEndMin"]

    # Scale FVG min size relative to typical price levels
    # (0.5 points on NQ ~20000 is tiny; need different scale for EURUSD ~1.10)
    if instrument == "eurusd":
        params["fvgMinSize"] = 0.0005 if style == "smc_swing" else 0.0002
    elif instrument == "oil":
        params["fvgMinSize"] = 0.05 if style == "smc_swing" else 0.02
    elif instrument == "btc":
        params["fvgMinSize"] = 50.0 if style == "smc_swing" else 20.0
    elif instrument == "gold":
        params["fvgMinSize"] = 1.0 if style == "smc_swing" else 0.3

    return params
