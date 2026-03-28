"""
SMC Dual-Agent Trading Bot — Clean Trade Logger

Writes structured trade records to logs/trades.csv.
One row per event: OPEN, CLOSE, BLOCK.
Easy to view in terminal with `column -s, -t < logs/trades.csv`
"""

import os
import csv
import logging
from datetime import datetime, timezone

from config import LOG_DIR

logger = logging.getLogger(__name__)

_CSV_PATH = os.path.join(LOG_DIR, "trades.csv")

_HEADER = [
    "timestamp", "event", "agent", "exchange", "symbol", "direction",
    "size", "entry", "sl", "tp", "rr", "ticket",
    "pnl", "hold_time", "reason",
]


def _ensure_file():
    """Create CSV with header if it doesn't exist."""
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(_CSV_PATH):
        with open(_CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(_HEADER)


def _write_row(row: dict):
    """Append a single row to the trade log."""
    _ensure_file()
    with open(_CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADER, extrasaction="ignore")
        writer.writerow(row)


def log_open(trade: dict, agent: str = "", exchange: str = ""):
    """Log a trade that was opened."""
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "event": "OPEN",
        "agent": agent.upper(),
        "exchange": exchange.upper(),
        "symbol": trade.get("symbol", ""),
        "direction": trade.get("direction", "").upper(),
        "size": trade.get("lot_size", ""),
        "entry": trade.get("price", ""),
        "sl": trade.get("sl", ""),
        "tp": trade.get("tp", ""),
        "rr": trade.get("rr", trade.get("risk_reward", "")),
        "ticket": trade.get("ticket", ""),
        "pnl": "",
        "hold_time": "",
        "reason": "",
    }
    _write_row(row)
    logger.info(
        "TRADE LOG | OPEN | %s | %s %s %s @ %s | SL=%s TP=%s | R:R=%s",
        agent.upper(), trade.get("direction", "").upper(),
        trade.get("symbol", ""), trade.get("lot_size", ""),
        trade.get("price", ""), trade.get("sl", ""),
        trade.get("tp", ""), trade.get("rr", trade.get("risk_reward", "")),
    )


def log_close(trade: dict, pnl: float = 0.0, hold_time: str = "",
              reason: str = "", exchange: str = ""):
    """Log a trade that was closed."""
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "event": "CLOSE",
        "agent": trade.get("agent", trade.get("comment", "")).upper(),
        "exchange": exchange.upper(),
        "symbol": trade.get("symbol", ""),
        "direction": trade.get("direction", "").upper(),
        "size": trade.get("lot_size", ""),
        "entry": trade.get("open_price", trade.get("price", "")),
        "sl": trade.get("sl", ""),
        "tp": trade.get("tp", ""),
        "rr": "",
        "ticket": trade.get("ticket", ""),
        "pnl": f"{pnl:.2f}",
        "hold_time": hold_time,
        "reason": reason,
    }
    _write_row(row)
    logger.info(
        "TRADE LOG | CLOSE | %s %s | P&L=$%.2f | %s",
        trade.get("direction", "").upper(),
        trade.get("symbol", ""), pnl, reason,
    )


def log_block(proposal: dict, agent: str = "", reason: str = ""):
    """Log a trade that was blocked by the Overseer."""
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "event": "BLOCK",
        "agent": agent.upper(),
        "exchange": "",
        "symbol": proposal.get("symbol", ""),
        "direction": proposal.get("direction", "").upper(),
        "size": "",
        "entry": "",
        "sl": proposal.get("sl", ""),
        "tp": proposal.get("tp", ""),
        "rr": proposal.get("risk_reward", ""),
        "ticket": "",
        "pnl": "",
        "hold_time": "",
        "reason": reason,
    }
    _write_row(row)
