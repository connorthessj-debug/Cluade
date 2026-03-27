"""Bayesian parameter optimization for trading bot strategies.

Uses historical trade data to find optimal values for key trading parameters
such as minimum confluence score, risk percentage, minimum reward-to-risk
ratio, and lookback periods.

The optimizer employs Bayesian optimization (via scikit-optimize) which builds
a probabilistic model of the objective function and uses it to select the most
promising parameter combinations to evaluate next.  This is far more sample-
efficient than grid search or random search -- critical when each "evaluation"
replays the entire trade history.

Safety rails:
    - Parameter changes are capped at a configurable percentage of the current
      value (default 10%) to prevent wild swings.
    - Every applied change is logged with a timestamp for full auditability.

Key concepts:
    - **Objective function**: Given a set of candidate parameters, replay
      historical trades and compute a quality metric (profit factor or Sharpe).
      Trades that would have been filtered out under the candidate parameters
      are excluded.
    - **Search space**: Defined per bot type (scalper vs swing) because each
      has different sensible ranges.
    - **gp_minimize**: Gaussian-process-based minimization from skopt.  We
      *negate* the objective because gp_minimize minimises, but we want to
      maximise profit factor.
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from skopt import gp_minimize
    from skopt.space import Integer, Real
    HAS_SKOPT = True
except ImportError:
    HAS_SKOPT = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default search spaces per bot type
# ---------------------------------------------------------------------------

_SEARCH_SPACES: Dict[str, List[Tuple[str, Any]]] = {
    "scalper": [
        ("min_confluence_score", Real(40.0, 85.0, name="min_confluence_score")),
        ("risk_pct", Real(0.1, 1.5, name="risk_pct")),
        ("min_rr", Real(1.0, 5.0, name="min_rr")),
        ("lookback_periods", Integer(10, 100, name="lookback_periods")),
    ],
    "swing": [
        ("min_confluence_score", Real(50.0, 90.0, name="min_confluence_score")),
        ("risk_pct", Real(0.2, 2.0, name="risk_pct")),
        ("min_rr", Real(2.0, 8.0, name="min_rr")),
        ("lookback_periods", Integer(20, 200, name="lookback_periods")),
    ],
}

# Fallback space used when bot type is not recognised.
_DEFAULT_SPACE = _SEARCH_SPACES["scalper"]


class ParameterOptimizer:
    """Bayesian optimizer that tunes bot parameters using historical trades.

    Works with the PerformanceAnalyzer for metric computation and the shared
    Database for persistence and audit logging.
    """

    def __init__(self, database, analyzer) -> None:
        self.db = database
        self.analyzer = analyzer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def optimize(self, bot_name: str, n_calls: int = 50) -> dict:
        """Run Bayesian optimization to find better parameter values.

        The optimizer replays historical trades under candidate parameters,
        removing those that would have been filtered, and measures the
        resulting profit factor.

        Args:
            bot_name: The bot whose parameters to optimize.
            n_calls: Number of evaluations for the Bayesian search.

        Returns:
            Dictionary with keys:
                - suggested_params: dict of param_name -> suggested_value
                - current_params: dict of param_name -> current_value
                - objective_value: best profit factor achieved
                - confidence: rough confidence label ("low", "medium", "high")
                  based on how many trades were available
                - n_trades: number of historical trades used

        Raises:
            RuntimeError: If scikit-optimize is not installed.
        """
        if not HAS_SKOPT:
            raise RuntimeError(
                "scikit-optimize is required for parameter optimization. "
                "Install it with: pip install scikit-optimize"
            )

        trades = await self.analyzer.journal.get_trades(bot_name=bot_name)

        if len(trades) < 20:
            logger.warning(
                "Only %d trades for %s -- need at least 20 for optimization",
                len(trades), bot_name,
            )
            return {
                "suggested_params": {},
                "current_params": {},
                "objective_value": 0.0,
                "confidence": "insufficient_data",
                "n_trades": len(trades),
            }

        # Determine search space based on bot name heuristic.
        space_def = self._get_search_space(bot_name)
        param_names = [name for name, _ in space_def]
        dimensions = [dim for _, dim in space_def]

        current_params = await self._load_current_params(bot_name, param_names)

        # Objective: we *negate* profit factor because gp_minimize minimises.
        def objective(values: list) -> float:
            candidate = dict(zip(param_names, values))
            pf = self._evaluate_params(candidate, trades)
            return -pf  # negate for minimisation

        result = gp_minimize(
            objective,
            dimensions,
            n_calls=n_calls,
            n_random_starts=min(10, n_calls // 3),
            random_state=42,
            verbose=False,
        )

        best_values = result.x
        best_pf = -result.fun
        suggested = dict(zip(param_names, best_values))

        # Round floats for readability.
        for k, v in suggested.items():
            if isinstance(v, float):
                suggested[k] = round(v, 4)

        # Confidence heuristic based on sample size.
        n = len(trades)
        if n >= 200:
            confidence = "high"
        elif n >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        logger.info(
            "Optimization for %s complete: pf=%.2f, confidence=%s, trades=%d",
            bot_name, best_pf, confidence, n,
        )

        return {
            "suggested_params": suggested,
            "current_params": current_params,
            "objective_value": round(best_pf, 4),
            "confidence": confidence,
            "n_trades": n,
        }

    async def apply_optimizations(
        self,
        bot_name: str,
        suggestions: dict,
        max_change_pct: float = 10.0,
    ) -> dict:
        """Apply suggested parameter changes with a safety cap.

        Each parameter is changed by at most ``max_change_pct`` percent of
        its current value.  This prevents the optimizer from making dramatic
        shifts that could destabilise live trading.

        Args:
            bot_name: The bot to update.
            suggestions: Dict of param_name -> suggested_value (from optimize).
            max_change_pct: Maximum allowed change as a percentage of the
                current value.  E.g. 10.0 means a param at 60 can move to
                the range [54, 66].

        Returns:
            Dictionary with keys:
                - applied: dict of param_name -> new_value actually written
                - capped: list of param names that were capped
                - timestamp: ISO-format time of application
        """
        suggested_params = suggestions.get("suggested_params", suggestions)
        current_params = suggestions.get("current_params", None)

        if current_params is None:
            param_names = list(suggested_params.keys())
            current_params = await self._load_current_params(bot_name, param_names)

        applied: Dict[str, Any] = {}
        capped: List[str] = []

        for param, suggested_value in suggested_params.items():
            current_value = current_params.get(param)

            if current_value is None or current_value == 0:
                # No current value to cap against -- apply directly.
                applied[param] = suggested_value
                continue

            max_delta = abs(current_value) * (max_change_pct / 100.0)
            delta = suggested_value - current_value

            if abs(delta) > max_delta:
                capped.append(param)
                capped_value = current_value + math.copysign(max_delta, delta)
                # Preserve type (int vs float).
                if isinstance(suggested_value, int) and isinstance(current_value, int):
                    capped_value = int(round(capped_value))
                else:
                    capped_value = round(capped_value, 4)
                applied[param] = capped_value
            else:
                applied[param] = suggested_value

        timestamp = datetime.utcnow().isoformat()

        # Persist the changes to the database for audit.
        for param, value in applied.items():
            await self.db.execute(
                """
                INSERT INTO parameter_changes
                    (bot_name, parameter, old_value, new_value, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    bot_name,
                    param,
                    str(current_params.get(param, "")),
                    str(value),
                    timestamp,
                ),
            )

        logger.info(
            "Applied %d parameter changes for %s (capped: %s)",
            len(applied), bot_name, capped or "none",
        )

        return {
            "applied": applied,
            "capped": capped,
            "timestamp": timestamp,
        }

    # ------------------------------------------------------------------
    # Core evaluation logic
    # ------------------------------------------------------------------

    def _evaluate_params(self, params: dict, trades: List[dict]) -> float:
        """Simulate how candidate parameters would have filtered trades.

        For each historical trade, check whether it would have been taken
        under the candidate parameters:
            - confluence_score >= min_confluence_score
            - r_multiple target >= min_rr (use the actual r_multiple as a
              proxy for the setup's expected RR at entry)

        Then compute profit factor on the surviving trades.

        Args:
            params: Candidate parameter dict.
            trades: Historical trade records.

        Returns:
            Profit factor of the filtered trade set.  Returns 0.0 when no
            trades survive the filter or there are only losses.
        """
        min_conf = params.get("min_confluence_score", 0.0)
        min_rr = params.get("min_rr", 0.0)

        surviving: List[dict] = []
        for t in trades:
            score = t.get("confluence_score", 0.0) or 0.0
            r_mult = abs(t.get("r_multiple", 0.0) or 0.0)

            # Would this trade have passed the candidate filters?
            if score < min_conf:
                continue
            if r_mult > 0 and r_mult < min_rr:
                # The setup's RR was below the new minimum -- skip.
                continue
            surviving.append(t)

        if not surviving:
            return 0.0

        wins = [t.get("pnl", 0.0) for t in surviving if t.get("pnl", 0) > 0]
        losses = [t.get("pnl", 0.0) for t in surviving if t.get("pnl", 0) <= 0]

        gross_profit = sum(wins)
        gross_loss = sum(abs(l) for l in losses)

        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_search_space(self, bot_name: str) -> List[Tuple[str, Any]]:
        """Select the search space based on bot name.

        Tries to match the bot name against known types (scalper, swing).
        Falls back to the default space.
        """
        lower = bot_name.lower()
        for bot_type, space in _SEARCH_SPACES.items():
            if bot_type in lower:
                return space
        return _DEFAULT_SPACE

    async def _load_current_params(
        self, bot_name: str, param_names: List[str],
    ) -> Dict[str, Any]:
        """Load current parameter values from the database.

        Falls back to sensible defaults when no stored value exists.
        """
        defaults: Dict[str, Any] = {
            "min_confluence_score": 60.0,
            "risk_pct": 0.5,
            "min_rr": 2.0,
            "lookback_periods": 50,
        }

        current: Dict[str, Any] = {}
        for name in param_names:
            row = await self.db.fetch_one(
                """
                SELECT new_value FROM parameter_changes
                WHERE bot_name = ? AND parameter = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (bot_name, name),
            )
            if row and row.get("new_value") is not None:
                try:
                    current[name] = float(row["new_value"])
                except (ValueError, TypeError):
                    current[name] = defaults.get(name, 0.0)
            else:
                current[name] = defaults.get(name, 0.0)

        return current
