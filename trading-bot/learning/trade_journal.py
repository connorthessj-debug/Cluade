"""Trade journaling system for recording and querying completed trades.

The trade journal is the foundation of the learning engine. Every closed trade
is recorded with full context -- setup type, confluence score, market conditions,
and outcome. This rich dataset powers all downstream analysis and optimization.

Accurate journaling is critical: the quality of parameter optimization and
pattern recognition depends entirely on the completeness and correctness of
the data captured here.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class TradeJournal:
    """Persistent trade journal backed by the shared Database instance.

    Records every completed trade with enough context for the performance
    analyzer and pattern memory to derive actionable insights.

    The database is expected to expose:
        - async execute(sql, params) -> None
        - async fetch_all(sql, params) -> List[dict]
        - async fetch_one(sql, params) -> Optional[dict]
    """

    def __init__(self, database) -> None:
        self.db = database

    async def record_trade(self, trade_data: dict) -> None:
        """Record a completed trade with full context.

        Args:
            trade_data: Dictionary containing trade details. Expected keys:
                - bot_name (str): Name of the bot that executed the trade.
                - symbol (str): Instrument traded, e.g. "EUR_USD".
                - side (str): "buy" or "sell".
                - entry_price (float): Price at entry.
                - exit_price (float): Price at exit.
                - pnl (float): Realised profit/loss in account currency.
                - setup_type (str): Signal origin, e.g. "bullish_ob_m15".
                - confluence_score (float): Score at the time of entry.
                - atr (float): Average True Range at entry -- proxy for
                    volatility.
                - volume (float): Volume context at entry.
                - spread (float): Bid-ask spread at entry.
                - r_multiple (float): Risk-adjusted return (PnL / risk).
                - entry_time (str | datetime): ISO-format timestamp or
                    datetime object.
                - exit_time (str | datetime): ISO-format timestamp or
                    datetime object.
                - notes (str, optional): Free-form context or tags.
        """
        entry_time = trade_data.get("entry_time", datetime.utcnow().isoformat())
        exit_time = trade_data.get("exit_time", datetime.utcnow().isoformat())

        if isinstance(entry_time, datetime):
            entry_time = entry_time.isoformat()
        if isinstance(exit_time, datetime):
            exit_time = exit_time.isoformat()

        sql = """
            INSERT INTO trades (
                bot_name, symbol, side, entry_price, exit_price, pnl,
                setup_type, confluence_score, atr, volume, spread,
                r_multiple, entry_time, exit_time, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            trade_data.get("bot_name", ""),
            trade_data.get("symbol", ""),
            trade_data.get("side", ""),
            trade_data.get("entry_price", 0.0),
            trade_data.get("exit_price", 0.0),
            trade_data.get("pnl", 0.0),
            trade_data.get("setup_type", ""),
            trade_data.get("confluence_score", 0.0),
            trade_data.get("atr", 0.0),
            trade_data.get("volume", 0.0),
            trade_data.get("spread", 0.0),
            trade_data.get("r_multiple", 0.0),
            entry_time,
            exit_time,
            trade_data.get("notes", ""),
        )
        await self.db.execute(sql, params)

    async def get_trades(
        self,
        bot_name: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        setup_type: Optional[str] = None,
    ) -> List[dict]:
        """Query trades with flexible optional filters.

        All parameters are optional; when omitted the corresponding filter
        is not applied.

        Args:
            bot_name: Filter by bot.
            symbol: Filter by instrument.
            start_date: ISO-format lower bound on entry_time (inclusive).
            end_date: ISO-format upper bound on entry_time (inclusive).
            setup_type: Filter by setup type string.

        Returns:
            List of trade dictionaries ordered by entry_time descending.
        """
        clauses: List[str] = []
        params: List[Any] = []

        if bot_name is not None:
            clauses.append("bot_name = ?")
            params.append(bot_name)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if start_date is not None:
            clauses.append("entry_time >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("entry_time <= ?")
            params.append(end_date)
        if setup_type is not None:
            clauses.append("setup_type = ?")
            params.append(setup_type)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT * FROM trades {where} ORDER BY entry_time DESC"
        return await self.db.fetch_all(sql, tuple(params))

    async def get_trade_summary(self, bot_name: Optional[str] = None) -> dict:
        """Compute aggregate performance statistics.

        Args:
            bot_name: Optional bot filter; None returns global summary.

        Returns:
            Dictionary with keys: total_trades, wins, losses, win_rate,
            total_pnl, avg_r, profit_factor, max_consecutive_losses,
            best_trade, worst_trade.
        """
        trades = await self.get_trades(bot_name=bot_name)

        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_r": 0.0,
                "profit_factor": 0.0,
                "max_consecutive_losses": 0,
                "best_trade": None,
                "worst_trade": None,
            }

        total = len(trades)
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        win_count = len(wins)
        loss_count = len(losses)

        total_pnl = sum(t.get("pnl", 0) for t in trades)
        r_values = [t.get("r_multiple", 0) for t in trades if t.get("r_multiple") is not None]
        avg_r = sum(r_values) / len(r_values) if r_values else 0.0

        gross_profit = sum(t.get("pnl", 0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Max consecutive losses -- walk trades in chronological order.
        sorted_trades = sorted(trades, key=lambda t: t.get("entry_time", ""))
        max_consec = 0
        current_consec = 0
        for t in sorted_trades:
            if t.get("pnl", 0) <= 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0

        best = max(trades, key=lambda t: t.get("pnl", 0))
        worst = min(trades, key=lambda t: t.get("pnl", 0))

        return {
            "total_trades": total,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": win_count / total if total > 0 else 0.0,
            "total_pnl": total_pnl,
            "avg_r": avg_r,
            "profit_factor": profit_factor,
            "max_consecutive_losses": max_consec,
            "best_trade": best,
            "worst_trade": worst,
        }
