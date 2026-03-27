#!/usr/bin/env python3
"""Master process manager for the trading bot system.
Launches all bots + dashboard, monitors health, restarts on failure.
Designed for 24/7 operation.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is on the import path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import Config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "manager.log")),
    ],
)
logger = logging.getLogger("manager")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEALTH_CHECK_INTERVAL = 30  # seconds
HEARTBEAT_STALE_THRESHOLD = 60  # seconds
INITIAL_BACKOFF = 10  # seconds
MAX_BACKOFF = 300  # seconds
BACKOFF_RESET_AFTER = 300  # seconds of successful running
SHUTDOWN_TIMEOUT = 30  # seconds

ALL_BOTS = ["arbitrage", "scalper", "swing"]

DB_PATH = PROJECT_ROOT / "data" / "trading.db"


# ---------------------------------------------------------------------------
# Bot wrapper -- runs in a child process
# ---------------------------------------------------------------------------

def _run_bot_process(bot_name: str) -> None:
    """Entry point for a child process that runs a single bot.

    Creates an asyncio event loop, initialises core components, and starts
    the bot.  This function never returns under normal operation.
    """
    import asyncio as _asyncio

    async def _main():
        from core.config import Config as _Config

        config = _Config()

        # Lazy-import optional components -- they may not exist yet, but the
        # run_all manager still needs to launch what *is* available.
        database = await _make_database()
        risk_manager = _make_risk_manager(config, database)
        publisher = _make_publisher(config)

        bot = _make_bot(bot_name, config, database, risk_manager, publisher)
        logger.info("Child process starting bot: %s (pid=%d)", bot_name, os.getpid())
        await bot.start()

    _asyncio.run(_main())


async def _make_database():
    """Create and initialize the async database adapter."""
    try:
        from core.database import Database
        db = Database(str(DB_PATH))
        await db.initialize()
        return db
    except (ImportError, Exception):
        pass

    # Fallback stub
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    class _StubDB:
        """Minimal async database stub backed by SQLite."""

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
            from datetime import datetime
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
    """Create a risk manager (or stub)."""
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
    """Create an event publisher (or stub)."""
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
    """Instantiate the correct bot by name."""
    if bot_name == "arbitrage":
        try:
            from bots.arbitrage.bot import ArbitrageBot
            # ArbitrageBot needs an exchange_manager; pass None for now and
            # let it fail gracefully if not provided.
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

    # Fallback: a placeholder bot that just heartbeats.
    from bots.base_bot import BaseBot

    class _PlaceholderBot(BaseBot):
        async def run(self):
            logger.info("%s: placeholder bot running (no implementation found)", self.name)
            while self.running:
                await self._heartbeat()
                await asyncio.sleep(10)

        async def on_tick(self):
            pass

    return _PlaceholderBot(bot_name, config, database, risk_manager, publisher)


# ---------------------------------------------------------------------------
# Managed child process wrapper
# ---------------------------------------------------------------------------

class ManagedProcess:
    """Wraps a child process with restart logic and backoff tracking."""

    def __init__(self, name: str, target=None, cmd=None, cwd=None):
        self.name = name
        self._target = target  # Python callable (for bots)
        self._cmd = cmd  # Shell command list (for dashboard, ws-bridge)
        self._cwd = cwd
        self.process = None
        self.start_time = 0.0
        self.restart_count = 0
        self.backoff = INITIAL_BACKOFF

    def start(self):
        """Launch the child process."""
        if self._target is not None:
            from multiprocessing import Process
            self.process = Process(target=self._target, args=(self.name,), daemon=True)
            self.process.start()
        elif self._cmd is not None:
            self.process = subprocess.Popen(
                self._cmd,
                cwd=self._cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        self.start_time = time.time()
        logger.info("Started %s (pid=%s)", self.name, self.pid)

    @property
    def pid(self):
        if self.process is None:
            return None
        if hasattr(self.process, "pid"):
            return self.process.pid
        return None

    def is_alive(self) -> bool:
        if self.process is None:
            return False
        if hasattr(self.process, "is_alive"):
            return self.process.is_alive()
        # subprocess.Popen
        return self.process.poll() is None

    def stop(self):
        """Request graceful stop."""
        if self.process is None:
            return
        try:
            if hasattr(self.process, "terminate"):
                self.process.terminate()
        except Exception:
            pass

    def kill(self):
        """Force kill."""
        if self.process is None:
            return
        try:
            if hasattr(self.process, "kill"):
                self.process.kill()
        except Exception:
            pass

    def maybe_reset_backoff(self):
        """Reset backoff if the process has been running long enough."""
        if time.time() - self.start_time > BACKOFF_RESET_AFTER:
            self.backoff = INITIAL_BACKOFF
            self.restart_count = 0

    def next_backoff(self) -> float:
        """Return the current backoff delay and escalate for next time."""
        delay = self.backoff
        self.backoff = min(self.backoff * 2, MAX_BACKOFF)
        self.restart_count += 1
        return delay


# ---------------------------------------------------------------------------
# Health monitoring
# ---------------------------------------------------------------------------

def _check_heartbeat(bot_name: str) -> bool:
    """Read heartbeat from bot_state table.  Returns True if fresh."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT state_json FROM bot_state WHERE bot_name = ?", (bot_name,)
        ).fetchone()
        conn.close()
        if row is None:
            return True  # No state yet -- give the bot time to initialise.
        state = json.loads(row[0])
        heartbeat = state.get("_heartbeat", 0)
        return (time.time() - heartbeat) < HEARTBEAT_STALE_THRESHOLD
    except Exception:
        return True  # DB not ready -- don't falsely restart.


# ---------------------------------------------------------------------------
# Main manager loop
# ---------------------------------------------------------------------------

class ProcessManager:
    """Orchestrates launching, monitoring, and restarting child processes."""

    def __init__(self, bot_names: list, run_dashboard: bool = True):
        self.managed: list[ManagedProcess] = []
        self._shutdown = False

        # Bot processes
        for name in bot_names:
            self.managed.append(
                ManagedProcess(name=name, target=_run_bot_process)
            )

        # Dashboard processes
        if run_dashboard:
            ws_bridge = PROJECT_ROOT / "dashboard" / "ws-bridge.py"
            if ws_bridge.exists():
                self.managed.append(
                    ManagedProcess(
                        name="ws-bridge",
                        cmd=[sys.executable, str(ws_bridge)],
                        cwd=str(PROJECT_ROOT),
                    )
                )

            dashboard_dir = PROJECT_ROOT / "dashboard"
            if (dashboard_dir / "package.json").exists():
                self.managed.append(
                    ManagedProcess(
                        name="dashboard",
                        cmd=["npm", "start"],
                        cwd=str(dashboard_dir),
                    )
                )

    def start_all(self):
        """Launch every managed process."""
        logger.info("Starting %d managed processes", len(self.managed))
        for mp in self.managed:
            try:
                mp.start()
            except Exception:
                logger.exception("Failed to start %s", mp.name)

    def stop_all(self):
        """Gracefully stop all processes, force-kill after timeout."""
        logger.info("Stopping all processes (timeout=%ds)", SHUTDOWN_TIMEOUT)
        for mp in self.managed:
            mp.stop()

        deadline = time.time() + SHUTDOWN_TIMEOUT
        while time.time() < deadline:
            alive = [mp for mp in self.managed if mp.is_alive()]
            if not alive:
                break
            time.sleep(0.5)

        # Force-kill survivors.
        for mp in self.managed:
            if mp.is_alive():
                logger.warning("Force-killing %s", mp.name)
                mp.kill()

    def health_check(self):
        """Check every managed process; restart any that are dead or stale."""
        for mp in self.managed:
            if self._shutdown:
                return

            mp.maybe_reset_backoff()

            needs_restart = False

            if not mp.is_alive():
                logger.warning("%s: process died", mp.name)
                needs_restart = True
            elif mp.name in ALL_BOTS and not _check_heartbeat(mp.name):
                logger.warning("%s: heartbeat stale (>%ds)", mp.name, HEARTBEAT_STALE_THRESHOLD)
                mp.stop()
                needs_restart = True

            if needs_restart:
                delay = mp.next_backoff()
                logger.info(
                    "%s: restarting in %.0fs (attempt #%d)",
                    mp.name,
                    delay,
                    mp.restart_count,
                )
                time.sleep(delay)
                if not self._shutdown:
                    try:
                        mp.start()
                    except Exception:
                        logger.exception("Failed to restart %s", mp.name)

    def run_forever(self):
        """Main loop: start processes, then monitor until shutdown."""
        self.start_all()
        logger.info("All processes launched -- entering health-check loop")

        while not self._shutdown:
            time.sleep(HEALTH_CHECK_INTERVAL)
            if not self._shutdown:
                self.health_check()

        self.stop_all()
        logger.info("Manager shut down cleanly")

    def request_shutdown(self):
        self._shutdown = True


# ---------------------------------------------------------------------------
# Signal handling & entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Trading bot process manager")
    parser.add_argument(
        "--bots",
        type=str,
        default=",".join(ALL_BOTS),
        help="Comma-separated list of bots to run (default: all)",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Skip launching the dashboard and WS bridge",
    )
    args = parser.parse_args()

    bot_names = [b.strip() for b in args.bots.split(",") if b.strip()]
    invalid = [b for b in bot_names if b not in ALL_BOTS]
    if invalid:
        parser.error(f"Unknown bot(s): {invalid}. Choose from {ALL_BOTS}")

    manager = ProcessManager(bot_names, run_dashboard=not args.no_dashboard)

    def _signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s -- initiating graceful shutdown", sig_name)
        manager.request_shutdown()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("=== Trading Bot Manager starting ===")
    logger.info("Bots: %s | Dashboard: %s", bot_names, not args.no_dashboard)

    manager.run_forever()


if __name__ == "__main__":
    main()
