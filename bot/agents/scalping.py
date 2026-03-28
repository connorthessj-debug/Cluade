"""
Scalping Agent — M1-M5 trades during high volatility and session opens.

Takes quick trades with tight stops, minimum 2R, max hold 2 hours.
"""

import logging

import pandas as pd

from config import (
    SCALP_ENTRY_TF, SCALP_CONFIRM_TF, SCALP_STRUCTURE_TF,
    SCALP_DEFAULT_SL_PIPS, SCALP_MIN_RR,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class ScalpingAgent(BaseAgent):
    """Short-term SMC scalping agent."""

    agent_name = "scalping"

    def get_timeframes(self) -> dict:
        return {
            "entry": SCALP_ENTRY_TF,
            "confirm": SCALP_CONFIRM_TF,
            "structure": SCALP_STRUCTURE_TF,
        }

    def get_min_rr(self) -> float:
        return SCALP_MIN_RR

    def calculate_sl_tp(
        self,
        df: pd.DataFrame,
        direction: str,
        entry_zone: dict,
        pip_size: float,
    ) -> dict | None:
        """
        Calculate SL and TP for scalp trades.

        SL: Behind the entry zone (OB/FVG) + buffer.
        TP: Based on recent structure level or minimum R:R.
        """
        entry = entry_zone["entry"]
        sl_buffer = SCALP_DEFAULT_SL_PIPS * pip_size

        if direction == "buy":
            # SL below the entry zone low
            sl = entry_zone["low"] - sl_buffer
            sl_distance = entry - sl

            # TP: look for recent swing high or use min R:R
            recent_highs = df["high"].iloc[-30:]
            target = recent_highs.max()

            # Ensure minimum R:R
            min_tp = entry + (sl_distance * SCALP_MIN_RR)
            tp = max(target, min_tp)

        elif direction == "sell":
            # SL above the entry zone high
            sl = entry_zone["high"] + sl_buffer
            sl_distance = sl - entry

            # TP: look for recent swing low or use min R:R
            recent_lows = df["low"].iloc[-30:]
            target = recent_lows.min()

            # Ensure minimum R:R
            min_tp = entry - (sl_distance * SCALP_MIN_RR)
            tp = min(target, min_tp)

        else:
            return None

        return {"entry": entry, "sl": sl, "tp": tp}
