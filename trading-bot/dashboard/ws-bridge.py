#!/usr/bin/env python3
"""
WebSocket bridge: polls the SQLite events table for new rows and forwards
them to the dashboard WebSocket server.

Usage:
    python ws-bridge.py [--db PATH] [--ws URL] [--interval SECONDS]
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package is required. Install with: pip install websockets")
    sys.exit(1)


DEFAULT_DB = str(Path(__file__).resolve().parent.parent / "data" / "trading.db")
DEFAULT_WS = "ws://localhost:8080"
DEFAULT_INTERVAL = 0.5  # seconds


async def bridge(db_path: str, ws_url: str, interval: float):
    """Main bridge loop: connect to WS, poll DB, forward events."""

    last_id = 0

    # Determine the starting last_id from the DB so we only forward NEW events
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT MAX(id) as max_id FROM events")
        row = cursor.fetchone()
        if row and row["max_id"]:
            last_id = row["max_id"]
        conn.close()
        print(f"[Bridge] Starting from event id {last_id}")
    except Exception as e:
        print(f"[Bridge] Could not read initial event id: {e}")

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                print(f"[Bridge] Connected to {ws_url}")

                while True:
                    try:
                        conn = sqlite3.connect(db_path)
                        conn.row_factory = sqlite3.Row
                        cursor = conn.execute(
                            "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT 100",
                            (last_id,),
                        )
                        rows = cursor.fetchall()
                        conn.close()

                        for row in rows:
                            event = dict(row)
                            last_id = event["id"]
                            message = json.dumps({
                                "type": "event",
                                "data": event,
                            })
                            await ws.send(message)
                            print(f"[Bridge] Forwarded event #{event['id']}: {event.get('event_type', 'unknown')}")

                    except sqlite3.OperationalError as e:
                        # DB might be locked or table doesn't exist yet
                        print(f"[Bridge] DB error (will retry): {e}")
                    except Exception as e:
                        print(f"[Bridge] Poll error: {e}")

                    await asyncio.sleep(interval)

        except websockets.exceptions.ConnectionClosedError:
            print("[Bridge] WebSocket connection closed. Reconnecting in 3s...")
            await asyncio.sleep(3)
        except ConnectionRefusedError:
            print("[Bridge] Cannot connect to dashboard. Retrying in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Bridge] Unexpected error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Bridge bot events to dashboard WebSocket")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to trading.db")
    parser.add_argument("--ws", default=DEFAULT_WS, help="Dashboard WebSocket URL")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Poll interval in seconds")
    args = parser.parse_args()

    print(f"[Bridge] DB: {args.db}")
    print(f"[Bridge] WS: {args.ws}")
    print(f"[Bridge] Interval: {args.interval}s")

    asyncio.run(bridge(args.db, args.ws, args.interval))


if __name__ == "__main__":
    main()
