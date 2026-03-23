#!/usr/bin/env python3
"""
Badge Server: receives facial recognition events from the Raspberry Pi
and dispatches badge print jobs to Gutenberg.

Usage:
    # Development (HTTP, no TLS):
    BADGE_API_KEY=your-key python app.py

    # Production (HTTPS with TLS):
    BADGE_API_KEY=your-key python app.py --tls

    # With gunicorn:
    BADGE_API_KEY=your-key gunicorn --certfile certs/cert.pem --keyfile certs/key.pem app:app
"""

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify

from auth import require_api_key
from gutenberg_adapter import GutenbergAdapter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("badge_server.log"),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
gutenberg = GutenbergAdapter()

# Audit log file
AUDIT_LOG = Path(os.environ.get("BADGE_AUDIT_LOG", "audit.jsonl"))


def _audit_log(event: dict):
    """Append an event to the audit log (JSON Lines format)."""
    event["server_timestamp"] = datetime.utcnow().isoformat() + "Z"
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


@app.route("/api/print-badge", methods=["POST"])
@require_api_key
def print_badge():
    """Receive a recognition event and queue a badge print.

    Expected JSON body:
    {
        "employee_id": "EMP-0042",
        "name": "Jane Doe",
        "department": "Engineering",
        "confidence": 0.87,
        "timestamp": "2026-03-23T14:30:00Z",
        "device_id": "pi-front-desk-01"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    required = ["employee_id", "name"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # Validate confidence is reasonable
    confidence = data.get("confidence", 0)
    if not isinstance(confidence, (int, float)) or confidence < 0:
        return jsonify({"error": "Invalid confidence value"}), 400

    employee_id = data["employee_id"]
    name = data["name"]
    department = data.get("department", "")
    device_id = data.get("device_id", "unknown")

    logger.info(f"Recognition event: {name} (ID: {employee_id}) "
                f"from {device_id}, confidence: {confidence:.1%}")

    # Audit log
    _audit_log({
        "event": "recognition",
        "employee_id": employee_id,
        "name": name,
        "department": department,
        "confidence": confidence,
        "device_id": device_id,
        "client_timestamp": data.get("timestamp", ""),
        "client_ip": request.remote_addr,
    })

    # Send to Gutenberg
    try:
        job_id = gutenberg.print_badge(
            employee_id=employee_id,
            name=name,
            department=department,
            confidence=confidence,
        )
        logger.info(f"Badge job created: {job_id}")
        _audit_log({"event": "badge_queued", "job_id": job_id, "employee_id": employee_id})
        return jsonify({"status": "queued", "badge_job_id": job_id})

    except Exception as e:
        logger.error(f"Failed to create badge job: {e}")
        return jsonify({"error": "Badge printing failed"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required)."""
    return jsonify({
        "status": "ok",
        "gutenberg_mode": gutenberg.mode,
        "server_time": datetime.utcnow().isoformat() + "Z",
    })


def main():
    parser = argparse.ArgumentParser(description="Badge print server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port (default: 5000)")
    parser.add_argument("--tls", action="store_true",
                        help="Enable TLS with certs in ./certs/")
    args = parser.parse_args()

    ssl_context = None
    if args.tls:
        cert = Path("certs/cert.pem")
        key = Path("certs/key.pem")
        if not cert.exists() or not key.exists():
            logger.error("TLS certs not found. Run scripts/generate_certs.sh first.")
            return
        ssl_context = (str(cert), str(key))
        logger.info("TLS enabled")

    logger.info(f"Starting badge server on {args.host}:{args.port}")
    logger.info(f"Gutenberg mode: {gutenberg.mode}")

    app.run(host=args.host, port=args.port, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
