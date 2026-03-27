"""Pattern memory system for the trading bot learning engine.

Stores and retrieves observed market patterns along with their outcomes,
enabling the bot to adjust its confidence in a setup based on how similar
conditions performed historically.

This is the bot's "experience" layer.  Every completed trade deposits a
pattern (the conditions under which it was taken) and its outcome.  When
a new trade opportunity arises, the bot queries pattern memory for similar
historical setups and adjusts its confluence score accordingly.

The memory is self-maintaining: a periodic ``prune()`` call removes patterns
that have too few observations to be statistically meaningful, preventing
noise from polluting the signal.

Matching strategy:
    - Categorical fields (trend, has_ob, has_fvg, etc.) must match exactly.
    - Continuous fields (volatility_regime) use fuzzy matching with a
      configurable tolerance band.
    - Confidence in a pattern scales with sample size -- small samples
      produce smaller score adjustments.
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Fields that must match exactly for a pattern lookup.
_CATEGORICAL_KEYS = [
    "trend", "has_ob", "has_fvg", "in_ote", "liquidity_swept",
    "hour", "day_of_week",
]

# Fields that use fuzzy (numeric tolerance) matching.
_CONTINUOUS_KEYS = [
    "volatility_regime",
]

# Default tolerance for continuous field matching (as a fraction).
_CONTINUOUS_TOLERANCE = 0.25


class PatternMemory:
    """Persistent pattern memory backed by the shared Database instance.

    Stores condition-outcome pairs in the ``learned_patterns`` table and
    provides fuzzy-match querying with statistical confidence gating.

    Expected database schema for ``learned_patterns``::

        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_name TEXT NOT NULL,
            conditions TEXT NOT NULL,   -- JSON-encoded conditions dict
            win INTEGER NOT NULL,       -- 1 for win, 0 for loss
            r_multiple REAL NOT NULL,
            pnl REAL NOT NULL,
            timestamp TEXT NOT NULL
        );
    """

    def __init__(self, database) -> None:
        self.db = database

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store_pattern(
        self,
        bot_name: str,
        conditions: dict,
        outcome: dict,
    ) -> None:
        """Record a pattern observation.

        Args:
            bot_name: Bot that generated the trade.
            conditions: Market context at entry time.  Expected keys:
                trend (str), has_ob (bool), has_fvg (bool), in_ote (bool),
                liquidity_swept (bool), hour (int), day_of_week (int),
                volatility_regime (str or float).
            outcome: Trade result.  Expected keys:
                win (bool), r_multiple (float), pnl (float).
        """
        sql = """
            INSERT INTO learned_patterns
                (bot_name, conditions, win, r_multiple, pnl, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            bot_name,
            json.dumps(conditions, default=str),
            1 if outcome.get("win", False) else 0,
            outcome.get("r_multiple", 0.0),
            outcome.get("pnl", 0.0),
            datetime.utcnow().isoformat(),
        )
        await self.db.execute(sql, params)

    async def query_similar(
        self,
        conditions: dict,
        min_sample: int = 20,
    ) -> Optional[dict]:
        """Find historically similar patterns and aggregate their outcomes.

        Retrieves all stored patterns, filters to those matching the given
        conditions (exact match on categorical fields, fuzzy match on
        continuous fields), and returns aggregate statistics if the sample
        size is large enough.

        Args:
            conditions: Current market conditions to match against.
            min_sample: Minimum number of matching patterns required.

        Returns:
            A dict with keys ``success_rate``, ``avg_r``, ``sample_size``,
            ``confidence`` if enough matches are found; otherwise ``None``.
        """
        rows = await self.db.fetch_all(
            "SELECT conditions, win, r_multiple, pnl FROM learned_patterns",
            (),
        )

        matches: List[dict] = []
        for row in rows:
            stored_conditions = self._parse_conditions(row.get("conditions", "{}"))
            if self._conditions_match(conditions, stored_conditions):
                matches.append(row)

        if len(matches) < min_sample:
            return None

        wins = sum(1 for m in matches if m.get("win", 0) == 1)
        r_values = [m.get("r_multiple", 0.0) for m in matches]
        success_rate = wins / len(matches)
        avg_r = sum(r_values) / len(r_values) if r_values else 0.0

        # Confidence scales with sqrt(sample_size), capped at 1.0.
        # 100 samples -> confidence ~1.0, 20 samples -> ~0.45.
        confidence = min(1.0, math.sqrt(len(matches)) / 10.0)

        return {
            "success_rate": round(success_rate, 4),
            "avg_r": round(avg_r, 4),
            "sample_size": len(matches),
            "confidence": round(confidence, 4),
        }

    async def adjust_score(
        self,
        base_score: float,
        conditions: dict,
    ) -> float:
        """Adjust a confluence score based on historical pattern performance.

        Queries pattern memory for setups with similar conditions.  If a
        statistically significant sample exists, the score is nudged:
            - Success rate > 60%: boost by up to +10 points.
            - Success rate < 40%: penalise by up to -15 points.

        The magnitude of the adjustment scales with both the deviation from
        the 50% baseline and the confidence (sample size).  This means a
        pattern with 200 observations at 30% win rate produces a larger
        penalty than one with 25 observations at the same rate.

        Args:
            base_score: The raw confluence score before adjustment.
            conditions: Current market conditions for the setup.

        Returns:
            The adjusted score (always clamped to [0, 100]).
        """
        result = await self.query_similar(conditions)

        if result is None:
            return base_score

        success_rate = result["success_rate"]
        confidence = result["confidence"]

        adjustment = 0.0

        if success_rate > 0.60:
            # Positive boost: up to +10 points.
            # Scale by how far above 60% and by confidence.
            deviation = (success_rate - 0.60) / 0.40  # 0..1
            adjustment = deviation * 10.0 * confidence

        elif success_rate < 0.40:
            # Negative penalty: up to -15 points.
            # Scale by how far below 40% and by confidence.
            deviation = (0.40 - success_rate) / 0.40  # 0..1
            adjustment = -deviation * 15.0 * confidence

        adjusted = base_score + adjustment
        adjusted = max(0.0, min(100.0, adjusted))

        logger.debug(
            "Pattern adjustment: base=%.1f, adj=%.1f, result=%.1f "
            "(sr=%.2f, conf=%.2f, n=%d)",
            base_score, adjustment, adjusted,
            success_rate, confidence, result["sample_size"],
        )

        return round(adjusted, 2)

    async def prune(self, min_sample: int = 20) -> int:
        """Remove under-represented patterns from memory.

        Groups stored patterns by their conditions JSON.  Any group with
        fewer than ``min_sample`` observations is deleted.  This keeps the
        memory table focused on statistically meaningful data.

        Args:
            min_sample: Minimum observations to retain a pattern group.

        Returns:
            Number of rows deleted.
        """
        rows = await self.db.fetch_all(
            "SELECT id, conditions FROM learned_patterns",
            (),
        )

        # Group row IDs by conditions hash.
        groups: Dict[str, List[int]] = {}
        for row in rows:
            cond_str = row.get("conditions", "{}")
            groups.setdefault(cond_str, []).append(row["id"])

        ids_to_delete: List[int] = []
        for cond_str, row_ids in groups.items():
            if len(row_ids) < min_sample:
                ids_to_delete.extend(row_ids)

        if ids_to_delete:
            # Delete in batches to avoid excessively long SQL.
            batch_size = 500
            for i in range(0, len(ids_to_delete), batch_size):
                batch = ids_to_delete[i : i + batch_size]
                placeholders = ",".join("?" for _ in batch)
                await self.db.execute(
                    f"DELETE FROM learned_patterns WHERE id IN ({placeholders})",
                    tuple(batch),
                )

        logger.info(
            "Pruned %d under-represented pattern rows (min_sample=%d)",
            len(ids_to_delete), min_sample,
        )

        return len(ids_to_delete)

    async def get_stats(self) -> dict:
        """Return summary statistics about the pattern memory.

        Returns:
            Dictionary with keys:
                - total_patterns: total number of stored observations
                - avg_sample_size: average group size across distinct
                  condition sets
                - most_common_setups: list of (conditions_summary, count)
                  for the top 5 most observed condition sets
        """
        rows = await self.db.fetch_all(
            "SELECT conditions FROM learned_patterns",
            (),
        )

        if not rows:
            return {
                "total_patterns": 0,
                "avg_sample_size": 0.0,
                "most_common_setups": [],
            }

        # Count by conditions hash.
        counts: Dict[str, int] = {}
        for row in rows:
            cond_str = row.get("conditions", "{}")
            counts[cond_str] = counts.get(cond_str, 0) + 1

        total = len(rows)
        n_groups = len(counts) if counts else 1
        avg_sample = total / n_groups

        # Top 5 most common.
        sorted_conditions = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        most_common = []
        for cond_str, count in sorted_conditions[:5]:
            try:
                cond = json.loads(cond_str)
                summary = self._summarise_conditions(cond)
            except (json.JSONDecodeError, TypeError):
                summary = cond_str[:80]
            most_common.append({"conditions": summary, "count": count})

        return {
            "total_patterns": total,
            "avg_sample_size": round(avg_sample, 2),
            "most_common_setups": most_common,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_conditions(raw: str) -> dict:
        """Parse a JSON conditions string, returning empty dict on failure."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _conditions_match(query: dict, stored: dict) -> bool:
        """Check whether stored conditions match the query.

        Categorical keys must match exactly (with type coercion for bools).
        Continuous keys use a tolerance band.

        Args:
            query: The conditions we are looking for.
            stored: A previously stored conditions dict.

        Returns:
            True if all present query keys match within tolerance.
        """
        # Categorical exact matching.
        for key in _CATEGORICAL_KEYS:
            if key not in query:
                continue
            if key not in stored:
                return False

            q_val = query[key]
            s_val = stored[key]

            # Normalise bools.
            if isinstance(q_val, bool):
                q_val = int(q_val)
            if isinstance(s_val, bool):
                s_val = int(s_val)

            if str(q_val) != str(s_val):
                return False

        # Continuous fuzzy matching.
        for key in _CONTINUOUS_KEYS:
            if key not in query:
                continue
            if key not in stored:
                return False

            try:
                q_val = float(query[key])
                s_val = float(stored[key])
            except (ValueError, TypeError):
                # Fall back to exact string match for non-numeric.
                if str(query[key]) != str(stored[key]):
                    return False
                continue

            if s_val == 0 and q_val == 0:
                continue
            ref = max(abs(q_val), abs(s_val), 1e-9)
            if abs(q_val - s_val) / ref > _CONTINUOUS_TOLERANCE:
                return False

        return True

    @staticmethod
    def _summarise_conditions(conditions: dict) -> str:
        """Create a short human-readable summary of a conditions dict."""
        parts: List[str] = []
        if "trend" in conditions:
            parts.append(str(conditions["trend"]))
        flags = []
        for flag in ("has_ob", "has_fvg", "in_ote", "liquidity_swept"):
            if conditions.get(flag):
                flags.append(flag.replace("has_", "").replace("_", ""))
        if flags:
            parts.append("+".join(flags))
        if "hour" in conditions:
            parts.append(f"h{conditions['hour']}")
        if "day_of_week" in conditions:
            parts.append(f"d{conditions['day_of_week']}")
        return " | ".join(parts) if parts else "unknown"
