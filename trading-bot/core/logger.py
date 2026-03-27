"""Structured logging for the trading bot system.

Provides both standard file/console logging and database-backed event
logging via BotLogger.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str,
    log_dir: str = "data/logs",
    level: int = logging.DEBUG,
) -> logging.Logger:
    """Create and configure a logger with file and console handlers.

    Args:
        name: Logger name (typically the bot/module name).
        log_dir: Directory for log files.
        level: Minimum log level.

    Returns:
        Configured logging.Logger instance.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers when called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (one file per logger name)
    file_handler = logging.FileHandler(
        log_path / f"{name}.log", encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


class BotLogger:
    """Logger that writes to both standard logging and the event database.

    Wraps a standard logger and optionally persists important events
    to the Database so they can be surfaced in the dashboard.
    """

    def __init__(self, name: str, database=None, log_dir: str = "data/logs"):
        """
        Args:
            name: Bot/module name used for the underlying logger.
            database: Optional Database instance for event persistence.
            log_dir: Directory for log files.
        """
        self._logger = setup_logger(name, log_dir=log_dir)
        self._db = database
        self._name = name

    # ------------------------------------------------------------------
    # Standard log methods
    # ------------------------------------------------------------------

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._logger.critical(msg, *args, **kwargs)

    # ------------------------------------------------------------------
    # Database-backed event logging
    # ------------------------------------------------------------------

    async def log_event(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        level: str = "info",
    ) -> None:
        """Log a message and optionally persist it as a database event.

        Args:
            event_type: Short event identifier (e.g. 'trade_opened').
            data: Arbitrary JSON-serialisable payload.
            level: Log level string ('debug', 'info', 'warning', 'error', 'critical').
        """
        message = f"[{event_type}] {data}" if data else f"[{event_type}]"
        log_fn = getattr(self._logger, level, self._logger.info)
        log_fn(message)

        if self._db is not None:
            try:
                await self._db.publish_event(self._name, event_type, data)
            except Exception as exc:
                self._logger.error(
                    "Failed to persist event %s to database: %s", event_type, exc
                )

    async def trade_opened(self, data: Dict[str, Any]) -> None:
        """Convenience: log a trade_opened event."""
        await self.log_event("trade_opened", data)

    async def trade_closed(self, data: Dict[str, Any]) -> None:
        """Convenience: log a trade_closed event."""
        await self.log_event("trade_closed", data)

    async def signal_detected(self, data: Dict[str, Any]) -> None:
        """Convenience: log a signal_detected event."""
        await self.log_event("signal_detected", data)

    async def bot_status(self, data: Dict[str, Any]) -> None:
        """Convenience: log a bot_status event."""
        await self.log_event("bot_status", data)

    async def pnl_update(self, data: Dict[str, Any]) -> None:
        """Convenience: log a pnl_update event."""
        await self.log_event("pnl_update", data)

    async def log_error(self, data: Dict[str, Any]) -> None:
        """Convenience: log an error event."""
        await self.log_event("error", data, level="error")
