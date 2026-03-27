#!/usr/bin/env python3
"""Run a single trading bot for development/testing."""

import asyncio
import logging
import signal
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_bot")

VALID_BOTS = ("arbitrage", "scalper", "swing")

DB_PATH = PROJECT_ROOT / "data" / "trading.db"


async def _make_database():
    """Create and initialize a database adapter (real or stub)."""
    try:
        from core.database import Database
        db = Database(str(DB_PATH))
        await db.initialize()
        return db
    except (ImportError, Exception):
        pass

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    class _StubDB:
        def __init__(self):
            self._conn = sqlite3.connect(str(DB_PATH))
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS bot_state "
                "(bot_name TEXT PRIMARY KEY, state_json TEXT, updated_at TEXT)"
            )
            self._conn.commit()

        async def load_bot_state(self, bot_name):
            row = self._conn.execute(
                "SELECT state_json FROM bot_state WHERE bot_name = ?", (bot_name,)
            ).fetchone()
            return row[0] if row else None

        async def save_bot_state(self, bot_name, state):
            self._conn.execute(
                "INSERT OR REPLACE INTO bot_state (bot_name, state_json, updated_at) "
                "VALUES (?, ?, ?)",
                (bot_name, state, datetime.utcnow().isoformat()),
            )
            self._conn.commit()

        async def initialize(self):
            pass

        async def close(self):
            self._conn.close()

        async def save_trade(self, trade):
            pass

        async def get_trades(self, **kw):
            return []

        async def save_position(self, position):
            pass

        async def get_positions(self, **kw):
            return []

        async def publish_event(self, bot_name, event_type, data=None):
            pass

    return _StubDB()


def _make_risk_manager(config, database):
    """Create a risk manager (real or stub)."""
    try:
        from core.risk_manager import RiskManager
        return RiskManager(config, database)
    except ImportError:
        pass

    class _StubRisk:
        async def check_trade(self, *a, **kw):
            return True

        async def update_position(self, *a, **kw):
            pass

        @property
        def kill_switch_triggered(self):
            return False

    return _StubRisk()


def _make_publisher(config):
    """Create an event publisher (real or stub)."""
    try:
        from core.publisher import Publisher
        return Publisher(config)
    except ImportError:
        pass

    class _StubPublisher:
        async def publish(self, source, event_type, data=None):
            logger.debug("Event: %s/%s %s", source, event_type, data)

    return _StubPublisher()


def _make_bot(bot_name, config, database, risk_manager, publisher):
    """Instantiate the correct bot class by name."""
    if bot_name == "arbitrage":
        try:
            from bots.arbitrage.bot import ArbitrageBot
            return ArbitrageBot(config, database, risk_manager, publisher,
                                exchange_manager=None)
        except (ImportError, TypeError):
            pass
    elif bot_name == "scalper":
        try:
            from bots.scalper.bot import ScalperBot
            return ScalperBot(config, database, risk_manager, publisher)
        except ImportError:
            pass
    elif bot_name == "swing":
        try:
            from bots.swing.bot import SwingBot
            return SwingBot(config, database, risk_manager, publisher)
        except ImportError:
            pass

    # Fallback placeholder
    from bots.base_bot import BaseBot

    class _PlaceholderBot(BaseBot):
        async def run(self):
            logger.info("%s: placeholder bot running (no concrete implementation)", self.name)
            while self.running:
                await self._heartbeat()
                await asyncio.sleep(10)

        async def on_tick(self):
            pass

    return _PlaceholderBot(bot_name, config, database, risk_manager, publisher)


async def run(bot_name: str) -> None:
    """Initialise components and run the specified bot until interrupted."""
    from core.config import Config

    logger.info("Initialising components for bot: %s", bot_name)
    config = Config()

    database = await _make_database()
    risk_manager = _make_risk_manager(config, database)
    publisher = _make_publisher(config)

    bot = _make_bot(bot_name, config, database, risk_manager, publisher)

    # Wire up graceful shutdown on SIGINT / SIGTERM.
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _on_signal():
        logger.info("Shutdown signal received -- stopping %s", bot_name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # Run bot and wait for shutdown concurrently.
    bot_task = asyncio.create_task(bot.start())
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, pending = await asyncio.wait(
        [bot_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
    )

    # Initiate graceful stop.
    await bot.stop()

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("%s shut down cleanly", bot_name)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in VALID_BOTS:
        print(f"Usage: {sys.argv[0]} {{{','.join(VALID_BOTS)}}}")
        sys.exit(1)

    bot_name = sys.argv[1]
    logger.info("=== Running single bot: %s ===", bot_name)

    try:
        asyncio.run(run(bot_name))
    except KeyboardInterrupt:
        logger.info("Interrupted -- exiting")


if __name__ == "__main__":
    main()
