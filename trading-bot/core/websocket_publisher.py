"""Event publisher for the trading bot system.

Uses the Database events table as the persistence layer and exposes
a simple publish() interface for all bots to emit structured events.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class WebSocketPublisher:
    """Publishes structured events to the database.

    All bots call publish() to record significant events (trades, signals,
    status changes, errors).  The dashboard layer can then read from the
    events table — or a future WebSocket broadcaster can stream them to
    connected clients.
    """

    # Recognised event types
    EVENT_TRADE_OPENED = "trade_opened"
    EVENT_TRADE_CLOSED = "trade_closed"
    EVENT_SIGNAL_DETECTED = "signal_detected"
    EVENT_BOT_STATUS = "bot_status"
    EVENT_PNL_UPDATE = "pnl_update"
    EVENT_ERROR = "error"

    _VALID_TYPES = {
        EVENT_TRADE_OPENED,
        EVENT_TRADE_CLOSED,
        EVENT_SIGNAL_DETECTED,
        EVENT_BOT_STATUS,
        EVENT_PNL_UPDATE,
        EVENT_ERROR,
    }

    def __init__(self, database) -> None:
        """
        Args:
            database: A Database instance that implements publish_event().
        """
        self._db = database

    async def publish(
        self,
        bot_name: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Persist an event to the database.

        Args:
            bot_name: Identifier of the originating bot.
            event_type: One of the recognised EVENT_* constants.
            data: Arbitrary JSON-serialisable payload.

        Returns:
            The database row id of the inserted event.
        """
        if event_type not in self._VALID_TYPES:
            logger.warning(
                "Unknown event type '%s' from %s – persisting anyway",
                event_type, bot_name,
            )

        payload = data or {}
        payload.setdefault("timestamp", datetime.utcnow().isoformat())

        try:
            event_id = await self._db.publish_event(bot_name, event_type, payload)
            logger.debug(
                "Event published: [%s] %s -> id=%d", bot_name, event_type, event_id
            )
            return event_id
        except Exception as exc:
            logger.error(
                "Failed to publish event [%s] %s: %s", bot_name, event_type, exc
            )
            raise

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def trade_opened(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish a trade_opened event."""
        return await self.publish(bot_name, self.EVENT_TRADE_OPENED, data)

    async def trade_closed(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish a trade_closed event."""
        return await self.publish(bot_name, self.EVENT_TRADE_CLOSED, data)

    async def signal_detected(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish a signal_detected event."""
        return await self.publish(bot_name, self.EVENT_SIGNAL_DETECTED, data)

    async def bot_status(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish a bot_status event."""
        return await self.publish(bot_name, self.EVENT_BOT_STATUS, data)

    async def pnl_update(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish a pnl_update event."""
        return await self.publish(bot_name, self.EVENT_PNL_UPDATE, data)

    async def error(self, bot_name: str, data: Dict[str, Any]) -> int:
        """Publish an error event."""
        return await self.publish(bot_name, self.EVENT_ERROR, data)
