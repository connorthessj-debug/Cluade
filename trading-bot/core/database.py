"""Async SQLite database layer for the trading bot system.

Uses aiosqlite with WAL mode for concurrent reads and a write lock
to guarantee thread-safe writes across all bot coroutines.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


class Database:
    """Async SQLite database with WAL mode and thread-safe writes."""

    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Open the database connection and create all tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        async with self._write_lock:
            await self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id              TEXT PRIMARY KEY,
                    bot_name        TEXT NOT NULL,
                    exchange        TEXT NOT NULL,
                    symbol          TEXT NOT NULL,
                    side            TEXT NOT NULL,
                    entry_price     REAL NOT NULL,
                    exit_price      REAL,
                    amount          REAL NOT NULL,
                    pnl             REAL,
                    fees            REAL DEFAULT 0,
                    entry_time      TEXT NOT NULL,
                    exit_time       TEXT,
                    setup_type      TEXT DEFAULT '',
                    notes           TEXT DEFAULT '',
                    r_multiple      REAL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id              TEXT PRIMARY KEY,
                    bot_name        TEXT NOT NULL,
                    exchange        TEXT NOT NULL,
                    symbol          TEXT NOT NULL,
                    side            TEXT NOT NULL,
                    entry_price     REAL NOT NULL,
                    amount          REAL NOT NULL,
                    stop_loss       REAL,
                    take_profit     REAL,
                    opened_at       TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'open'
                );

                CREATE TABLE IF NOT EXISTS bot_state (
                    bot_name        TEXT PRIMARY KEY,
                    state_json      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id              TEXT PRIMARY KEY,
                    bot_name        TEXT NOT NULL,
                    symbol          TEXT NOT NULL,
                    timeframe       TEXT DEFAULT '',
                    signal_type     TEXT NOT NULL,
                    score           REAL DEFAULT 0,
                    data_json       TEXT DEFAULT '{}',
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name        TEXT NOT NULL,
                    event_type      TEXT NOT NULL,
                    data_json       TEXT DEFAULT '{}',
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name        TEXT NOT NULL,
                    metric_name     TEXT NOT NULL,
                    metric_value    REAL NOT NULL,
                    recorded_at     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name        TEXT NOT NULL,
                    pattern_name    TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    score           REAL DEFAULT 0,
                    sample_size     INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trades_bot ON trades(bot_name);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
                CREATE INDEX IF NOT EXISTS idx_events_bot ON events(bot_name);
                CREATE INDEX IF NOT EXISTS idx_signals_bot ON signals(bot_name);
                """
            )
            await self._db.commit()

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    async def save_trade(self, trade) -> None:
        """Persist a Trade dataclass to the database."""
        async with self._write_lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO trades
                   (id, bot_name, exchange, symbol, side, entry_price, exit_price,
                    amount, pnl, fees, entry_time, exit_time, setup_type, notes, r_multiple)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.id,
                    trade.bot_name,
                    trade.exchange,
                    trade.symbol,
                    trade.side,
                    trade.entry_price,
                    trade.exit_price,
                    trade.amount,
                    trade.pnl,
                    trade.fees,
                    trade.entry_time.isoformat(),
                    trade.exit_time.isoformat() if trade.exit_time else None,
                    trade.setup_type,
                    trade.notes,
                    trade.r_multiple,
                ),
            )
            await self._db.commit()

    async def get_trades(
        self,
        bot_name: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve trades with optional filters."""
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []
        if bot_name:
            query += " AND bot_name = ?"
            params.append(bot_name)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def save_position(self, position) -> None:
        """Persist a Position dataclass."""
        async with self._write_lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO positions
                   (id, bot_name, exchange, symbol, side, entry_price, amount,
                    stop_loss, take_profit, opened_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    position.id,
                    position.bot_name,
                    position.exchange,
                    position.symbol,
                    position.side,
                    position.entry_price,
                    position.amount,
                    position.stop_loss,
                    position.take_profit,
                    position.opened_at.isoformat(),
                    position.status,
                ),
            )
            await self._db.commit()

    async def update_position(self, position_id: str, **kwargs) -> None:
        """Update specific fields on an existing position."""
        if not kwargs:
            return
        set_clauses = []
        params: list = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            if isinstance(value, datetime):
                params.append(value.isoformat())
            else:
                params.append(value)
        params.append(position_id)

        async with self._write_lock:
            await self._db.execute(
                f"UPDATE positions SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            await self._db.commit()

    async def get_positions(
        self,
        bot_name: Optional[str] = None,
        status: Optional[str] = "open",
    ) -> List[Dict[str, Any]]:
        """Retrieve positions with optional filters."""
        query = "SELECT * FROM positions WHERE 1=1"
        params: list = []
        if bot_name:
            query += " AND bot_name = ?"
            params.append(bot_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at DESC"

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Bot state
    # ------------------------------------------------------------------

    async def save_bot_state(self, bot_name: str, state: Dict[str, Any]) -> None:
        """Save or update serialised bot state."""
        async with self._write_lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO bot_state (bot_name, state_json, updated_at)
                   VALUES (?, ?, ?)""",
                (bot_name, json.dumps(state), datetime.utcnow().isoformat()),
            )
            await self._db.commit()

    async def load_bot_state(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """Load serialised bot state, or None if not found."""
        cursor = await self._db.execute(
            "SELECT state_json FROM bot_state WHERE bot_name = ?", (bot_name,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["state_json"])
        return None

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    async def save_signal(self, signal) -> None:
        """Persist a Signal dataclass."""
        async with self._write_lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO signals
                   (id, bot_name, symbol, timeframe, signal_type, score, data_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.id,
                    signal.bot_name,
                    signal.symbol,
                    signal.timeframe,
                    signal.signal_type,
                    signal.score,
                    json.dumps(signal.data),
                    signal.created_at.isoformat(),
                ),
            )
            await self._db.commit()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def publish_event(
        self, bot_name: str, event_type: str, data: Optional[Dict[str, Any]] = None
    ) -> int:
        """Insert an event and return its id."""
        async with self._write_lock:
            cursor = await self._db.execute(
                """INSERT INTO events (bot_name, event_type, data_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    bot_name,
                    event_type,
                    json.dumps(data or {}),
                    datetime.utcnow().isoformat(),
                ),
            )
            await self._db.commit()
            return cursor.lastrowid

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------

    async def get_performance_metrics(
        self, bot_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieve recent performance metric records."""
        query = "SELECT * FROM performance_metrics WHERE 1=1"
        params: list = []
        if bot_name:
            query += " AND bot_name = ?"
            params.append(bot_name)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_performance_metric(
        self, bot_name: str, metric_name: str, metric_value: float
    ) -> None:
        """Record a performance metric data-point."""
        async with self._write_lock:
            await self._db.execute(
                """INSERT INTO performance_metrics
                   (bot_name, metric_name, metric_value, recorded_at)
                   VALUES (?, ?, ?, ?)""",
                (bot_name, metric_name, metric_value, datetime.utcnow().isoformat()),
            )
            await self._db.commit()

    # ------------------------------------------------------------------
    # Learned patterns
    # ------------------------------------------------------------------

    async def save_learned_pattern(
        self,
        bot_name: str,
        pattern_name: str,
        parameters: Dict[str, Any],
        score: float = 0.0,
        sample_size: int = 0,
    ) -> None:
        """Insert or update a learned pattern."""
        now = datetime.utcnow().isoformat()
        async with self._write_lock:
            await self._db.execute(
                """INSERT INTO learned_patterns
                   (bot_name, pattern_name, parameters_json, score, sample_size,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    bot_name,
                    pattern_name,
                    json.dumps(parameters),
                    score,
                    sample_size,
                    now,
                    now,
                ),
            )
            await self._db.commit()

    async def get_learned_patterns(
        self, bot_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve learned patterns, optionally filtered by bot."""
        query = "SELECT * FROM learned_patterns WHERE 1=1"
        params: list = []
        if bot_name:
            query += " AND bot_name = ?"
            params.append(bot_name)
        query += " ORDER BY updated_at DESC"

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["parameters"] = json.loads(d.pop("parameters_json"))
            results.append(d)
        return results
