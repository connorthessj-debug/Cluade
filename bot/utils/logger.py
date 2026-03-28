"""
Logging setup for the SMC trading bot.
Logs to both console and rotating file.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, LOG_LEVEL, LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT


def setup_logging():
    """Configure logging with console and file handlers."""
    # Create log directory
    os.makedirs(LOG_DIR, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Format
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler (rotating)
    log_file = os.path.join(LOG_DIR, "smc_bot.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
        backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Trade log (separate file for trade history)
    trade_fmt = logging.Formatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    trade_file = os.path.join(LOG_DIR, "trades.log")
    trade_handler = RotatingFileHandler(
        trade_file,
        maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
        backupCount=LOG_BACKUP_COUNT,
    )
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(trade_fmt)

    trade_logger = logging.getLogger("trades")
    trade_logger.addHandler(trade_handler)
    trade_logger.propagate = False
