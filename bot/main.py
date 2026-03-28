#!/usr/bin/env python3
"""
SMC Dual-Agent Trading Bot — Main Entry Point
Runs the Overseer in a 24/7 loop on the VPS.

Usage:
    python main.py
"""

import sys
import time
import signal
import logging
from datetime import datetime, timezone

from config import OVERSEER_CYCLE_SECONDS, HEARTBEAT_SECONDS, PAPER_TRADING, DUAL_AGENT_MODE
from utils.logger import setup_logging
from mt5_bridge import MT5Bridge
from risk_manager import RiskManager
from overseer import Overseer

logger = logging.getLogger("smc_bot")

# Graceful shutdown flag
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Shutdown signal received (%s)", signal.Signals(signum).name)
    _shutdown = True


def is_market_open() -> bool:
    """
    Check if the forex market is open.
    Forex trades Sun 21:00 UTC to Fri 21:00 UTC.
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 6=Sun
    hour = now.hour

    # Saturday: always closed
    if weekday == 5:
        return False

    # Sunday: open after ~21:00 UTC (some brokers 22:00)
    if weekday == 6:
        return hour >= 21

    # Friday: close at ~21:00 UTC
    if weekday == 4:
        return hour < 21

    # Mon-Thu: always open
    return True


def main():
    setup_logging()

    mode = "PAPER TRADING (OANDA Demo)" if PAPER_TRADING else "LIVE TRADING"
    agent_mode = "DUAL-AGENT (Scalping + Swing)" if DUAL_AGENT_MODE else "SINGLE-AGENT"

    logger.info("=" * 60)
    logger.info("SMC DUAL-AGENT TRADING BOT — STARTING")
    logger.info("=" * 60)
    logger.info("  Mode        : %s", mode)
    logger.info("  Agent Mode  : %s", agent_mode)
    logger.info("  FTMO Rules  : ENFORCED (even in paper mode)")
    logger.info("=" * 60)

    if PAPER_TRADING:
        logger.info(
            "*** PAPER MODE: Trades execute on OANDA demo account. ***\n"
            "*** No real money at risk. Both agents learning simultaneously. ***"
        )

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Connect to MT5 ────────────────────────────────────────
    mt5 = MT5Bridge()
    if not mt5.connect():
        logger.critical("Cannot connect to MT5. Exiting.")
        sys.exit(1)

    account = mt5.get_account_info()
    if account:
        logger.info(
            "Account: %s | Balance: $%.2f | Equity: $%.2f | Leverage: 1:%d",
            account["login"], account["balance"],
            account["equity"], account["leverage"],
        )
        account_type = "DEMO" if PAPER_TRADING else "LIVE"
        logger.info("Account type: %s", account_type)

    # ── Initialize components ─────────────────────────────────
    risk = RiskManager(mt5)
    overseer = Overseer(mt5, risk)

    logger.info("Overseer initialized. Entering main loop...")
    logger.info("Cycle interval: %ds | Market check enabled", OVERSEER_CYCLE_SECONDS)

    last_heartbeat = time.time()
    consecutive_errors = 0
    max_errors = 10

    # ── Main Loop ─────────────────────────────────────────────
    while not _shutdown:
        try:
            # Heartbeat
            if time.time() - last_heartbeat >= HEARTBEAT_SECONDS:
                status = risk.get_risk_status()
                logger.info(
                    "HEARTBEAT — Equity: $%.2f | Daily DD: %.2f%% | "
                    "Total DD: %.2f%% | Open: %d positions",
                    status.get("equity", 0),
                    status.get("daily_dd_pct", 0),
                    status.get("total_dd_pct", 0),
                    status.get("open_positions", 0),
                )
                last_heartbeat = time.time()

            # Check if market is open
            if not is_market_open():
                logger.debug("Market closed. Sleeping 60s...")
                time.sleep(60)
                continue

            # Ensure MT5 is still connected
            if not mt5.ensure_connected():
                logger.error("MT5 connection lost. Retrying next cycle...")
                time.sleep(OVERSEER_CYCLE_SECONDS)
                continue

            # Run one Overseer cycle
            summary = overseer.run_cycle()

            # Reset error counter on success
            consecutive_errors = 0

            # Sleep until next cycle
            time.sleep(OVERSEER_CYCLE_SECONDS)

        except KeyboardInterrupt:
            break

        except Exception as e:
            consecutive_errors += 1
            logger.error(
                "Cycle error (%d/%d): %s",
                consecutive_errors, max_errors, e,
                exc_info=True,
            )

            if consecutive_errors >= max_errors:
                logger.critical(
                    "Too many consecutive errors (%d). Emergency shutdown.",
                    consecutive_errors,
                )
                risk.emergency_close_all("Too many consecutive errors")
                break

            # Exponential backoff on errors
            wait = min(2 ** consecutive_errors, 120)
            logger.info("Waiting %ds before retry...", wait)
            time.sleep(wait)

    # ── Cleanup ───────────────────────────────────────────────
    logger.info("Shutting down gracefully...")
    mt5.disconnect()
    logger.info("SMC Bot stopped.")


if __name__ == "__main__":
    main()
