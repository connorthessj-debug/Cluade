"""Abstract base class for all trading bots.

Provides lifecycle management (start/stop), state persistence, heartbeat
publishing, and the interface contract that every concrete bot must fulfil.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseBot(ABC):
    """Base class that all trading bots inherit from.

    Parameters
    ----------
    name : str
        Unique identifier for this bot instance (e.g. ``"arbitrage"``).
    config : Config
        Resolved system configuration object.
    database : object
        Database adapter exposing ``load_bot_state`` / ``save_bot_state``.
    risk_manager : object
        Risk manager instance for pre-trade checks.
    publisher : object
        Event publisher for status updates and trade notifications.
    """

    def __init__(self, name, config, database, risk_manager, publisher):
        self.name = name
        self.config = config
        self.db = database
        self.risk = risk_manager
        self.publisher = publisher
        self.running = False
        self.last_heartbeat = 0
        self._state = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the bot – load persisted state and enter the main loop."""
        saved = await self.db.load_bot_state(self.name)
        if saved:
            self._state = json.loads(saved)
            logger.info("%s: resuming from saved state", self.name)

        self.running = True
        await self.publisher.publish(self.name, "bot_status", {"status": "started"})
        logger.info("%s: started", self.name)

        try:
            await self.run()
        except Exception as e:
            logger.exception("%s: unhandled error in run loop", self.name)
            await self.publisher.publish(self.name, "error", {"error": str(e)})
            raise

    async def stop(self):
        """Graceful shutdown – persist state, do **not** close positions."""
        self.running = False
        await self._save_state()
        await self.publisher.publish(self.name, "bot_status", {"status": "stopped"})
        logger.info("%s: stopped", self.name)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    async def _save_state(self):
        """Persist the current bot state to the database."""
        await self.db.save_bot_state(self.name, json.dumps(self._state))

    async def _heartbeat(self):
        """Record a heartbeat timestamp in the persisted state."""
        self.last_heartbeat = time.time()
        await self.db.save_bot_state(
            self.name,
            json.dumps(
                {
                    **self._state,
                    "_heartbeat": self.last_heartbeat,
                    "_status": "running",
                }
            ),
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self):
        """Main bot loop – implement in subclasses."""
        pass

    @abstractmethod
    async def on_tick(self):
        """Called each iteration of the main loop."""
        pass
