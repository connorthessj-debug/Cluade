"""
Swing Agent — H1-D1 trades in trending markets with clean structure.

Takes larger moves with wider stops, minimum 3R, max hold 72 hours.
"""

import logging

import pandas as pd

from config import (
    SWING_ENTRY_TF, SWING_CONFIRM_TF, SWING_STRUCTURE_TF,
    SWING_DEFAULT_SL_PIPS, SWING_MIN_RR,
)
from smc.structure import find_swing_points
from .base import BaseAgent

logger = logging.getLogger(__name__)


class SwingAgent(BaseAgent):
    """Medium-term SMC swing trading agent."""

    agent_name = "swing"

    def get_timeframes(self) -> dict:
        return {
            "entry": SWING_ENTRY_TF,
            "confirm": SWING_CONFIRM_TF,
            "structure": SWING_STRUCTURE_TF,
        }

    def get_min_rr(self) -> float:
        return SWING_MIN_RR

    def calculate_sl_tp(
        self,
        df: pd.DataFrame,
        direction: str,
        entry_zone: dict,
        pip_size: float,
    ) -> dict | None:
        """
        Calculate SL and TP for swing trades.

        SL: Behind the entry zone + structure-based buffer.
        TP: Key structure level (swing high/low) with minimum R:R.
        """
        entry = entry_zone["entry"]
        sl_buffer = SWING_DEFAULT_SL_PIPS * pip_size

        # Use swing points for better TP targeting
        swings = find_swing_points(df)

        if direction == "buy":
            # SL below entry zone
            sl = entry_zone["low"] - sl_buffer
            sl_distance = entry - sl

            # TP: target the next significant swing high above entry
            swing_highs = [s for s in swings if s.kind == "high" and s.price > entry]
            if swing_highs:
                # Take the first major high above entry
                target = swing_highs[-1].price if len(swing_highs) > 1 else swing_highs[0].price
            else:
                target = df["high"].iloc[-50:].max()

            # Ensure minimum R:R
            min_tp = entry + (sl_distance * SWING_MIN_RR)
            tp = max(target, min_tp)

        elif direction == "sell":
            # SL above entry zone
            sl = entry_zone["high"] + sl_buffer
            sl_distance = sl - entry

            # TP: target the next significant swing low below entry
            swing_lows = [s for s in swings if s.kind == "low" and s.price < entry]
            if swing_lows:
                target = swing_lows[-1].price if len(swing_lows) > 1 else swing_lows[0].price
            else:
                target = df["low"].iloc[-50:].min()

            # Ensure minimum R:R
            min_tp = entry - (sl_distance * SWING_MIN_RR)
            tp = min(target, min_tp)

        else:
            return None

        return {"entry": entry, "sl": sl, "tp": tp}
