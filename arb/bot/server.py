#!/usr/bin/env python3
"""
HTTP server that runs the trading bot and serves the mobile dashboard.
Provides REST API for bot control and status.
"""

import json
import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from coinbase_client import load_client
from trader import RenderTrader, BotConfig

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

bot: RenderTrader = None
bot_thread: threading.Thread = None
DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"

# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------

class BotHandler(SimpleHTTPRequestHandler):
    """Serves dashboard files + REST API for bot control."""

    def log_message(self, format, *args):
        # Suppress default access logs (too noisy)
        pass

    def _send_json(self, data: dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API endpoints
        if path == "/api/status":
            if bot:
                self._send_json(bot.get_status())
            else:
                self._send_json({"error": "Bot not initialized"}, 500)
            return

        if path == "/api/config":
            if bot:
                self._send_json(bot.config.to_dict())
            else:
                self._send_json({"error": "Bot not initialized"}, 500)
            return

        if path == "/api/trades":
            if bot:
                from dataclasses import asdict
                trades = [asdict(t) for t in bot.trades[-50:]]
                self._send_json({"trades": trades})
            else:
                self._send_json({"trades": []})
            return

        # Serve dashboard files
        if path == "/" or path == "":
            path = "/index.html"

        file_path = DASHBOARD_DIR / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            # Determine content type
            ext = file_path.suffix.lower()
            content_types = {
                ".html": "text/html",
                ".css": "text/css",
                ".js": "application/javascript",
                ".json": "application/json",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }
            ct = content_types.get(ext, "application/octet-stream")

            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global bot, bot_thread
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/start":
            if bot and not bot.running:
                bot_thread = threading.Thread(target=bot.run, daemon=True)
                bot_thread.start()
                self._send_json({"status": "started"})
            elif bot and bot.running:
                self._send_json({"status": "already_running"})
            else:
                self._send_json({"error": "Bot not initialized"}, 500)
            return

        if path == "/api/stop":
            if bot and bot.running:
                bot.stop()
                self._send_json({"status": "stopped"})
            else:
                self._send_json({"status": "not_running"})
            return

        if path == "/api/config":
            if bot:
                body = self._read_body()
                for key, value in body.items():
                    if hasattr(bot.config, key):
                        field_type = type(getattr(bot.config, key))
                        setattr(bot.config, key, field_type(value))
                bot.save_state()
                self._send_json(bot.config.to_dict())
            else:
                self._send_json({"error": "Bot not initialized"}, 500)
            return

        if path == "/api/emergency_sell":
            if bot and bot.position:
                bot.execute_sell("EMERGENCY_MANUAL")
                self._send_json({"status": "sold"})
            else:
                self._send_json({"status": "no_position"})
            return

        self._send_json({"error": "Not found"}, 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global bot

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(__file__).parent / "bot.log"),
        ]
    )
    logger = logging.getLogger("server")

    # Initialize bot
    logger.info("Initializing Coinbase client...")
    client = load_client()

    # Test connection
    balance = client.get_balance("USD")
    logger.info(f"Connected! USD balance: ${balance:.2f}")

    render_balance = client.get_balance("RENDER")
    logger.info(f"RENDER balance: {render_balance:.4f}")

    bot = RenderTrader(client)

    # Start HTTP server
    port = int(os.environ.get("BOT_PORT", "8766"))
    server = HTTPServer(("0.0.0.0", port), BotHandler)
    logger.info(f"Dashboard: http://localhost:{port}")
    logger.info(f"  From iPhone: http://<your-pc-ip>:{port}")
    logger.info("")
    logger.info("Bot is ready. Open the dashboard and press START.")
    logger.info("Or POST to /api/start to begin trading.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if bot.running:
            bot.stop()
        server.shutdown()


if __name__ == "__main__":
    import os
    main()
