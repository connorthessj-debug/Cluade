#!/usr/bin/env python3
"""Run a single trading bot for development/testing."""

import asyncio
import logging
import signal
import sys
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


def _make_database(config):
    """Create a database adapter (real or stub)."""
    try:
        from core.database import Database  # type: ignore[import-not-found]
        return Database(config)
    except ImportError:
        pass

    import sqlite3

    db_path = PROJECT_ROOT / "data" / "trading.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class _StubDB:
        def __init__(self):
            self._conn = sqlite3.connect(str(db_path))
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS bot_state "
                "(bot_name TEXT PRIMARY KEY, state TEXT)"
            )
            self._conn.commit()

        async def load_bot_state(self, bot_name):
            row = self._conn.execute(
                "SELECT state FROM bot_state WHERE bot_name = ?", (bot_name,)
            ).fetchone()
            return row[0] if row else None

        async def save_bot_state(self, bot_name, state):
            self._conn.execute(
                "INSERT OR REPLACE INTO bot_state (bot_name, state) VALUES (?, ?)",
                (bot_name, state),
            )
            self._conn.commit()

        async def execute(self, sql, params=()):
            self._conn.execute(sql, params)
            self._conn.commit()

        async def fetch_all(self, sql, params=()):
            cur = self._conn.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]

        async def fetch_one(self, sql, params=()):
            cur = self._conn.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None

    return _StubDB()


def _make_risk_manager(config, database):
    """Create a risk manager (real or stub)."""
    try:
        from core.risk_manager import RiskManager  # type: ignore[import-not-found]
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
        from core.publisher import Publisher  # type: ignore[import-not-found]
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
            from bots.arbitrage.bot import ArbitrageBot  # type: ignore[import-not-found]
            return ArbitrageBot(config, database, risk_manager, publisher)
        except ImportError:
            pass
    elif bot_name == "scalper":
        try:
            from bots.scalper.bot import ScalperBot  # type: ignore[import-not-found]
            return ScalperBot(config, database, risk_manager, publisher)
        except ImportError:
            pass
    elif bot_name == "swing":
        try:
            from bots.swing.bot import SwingBot  # type: ignore[import-not-found]
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

    database = _make_database(config)
    risk_manager = _make_risk_manager(config, database)
    publisher = _make_publisher(config)

    bot = _make_bot(bot_name, config, database, risk_manager, publisher)

    # Wire up graceful shutdown on SIGINT / SIGTERM.
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _on_signal():
        logger.info("Shutdown signal received — stopping %s", bot_name)
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
        logger.info("Interrupted — exiting")


if __name__ == "__main__":
    main()
