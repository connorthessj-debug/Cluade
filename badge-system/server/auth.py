"""
API key authentication middleware for the badge server.

The API key is shared between the Pi and the server. Both load it from
the BADGE_API_KEY environment variable.
"""

import functools
import hashlib
import hmac
import os
import time

from flask import request, jsonify

# Load API key from environment
_API_KEY = os.environ.get("BADGE_API_KEY", "")

# Rate limiting: max requests per IP per minute
_RATE_LIMIT = int(os.environ.get("BADGE_RATE_LIMIT", "30"))
_rate_tracker = {}  # ip -> [timestamps]


def require_api_key(f):
    """Decorator that validates the X-API-Key header."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _API_KEY:
            # No key configured — reject all requests for safety
            return jsonify({"error": "Server API key not configured"}), 500

        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(provided_key.encode(), _API_KEY.encode()):
            return jsonify({"error": "Invalid API key"}), 403

        # Rate limiting
        ip = request.remote_addr
        now = time.time()
        if ip not in _rate_tracker:
            _rate_tracker[ip] = []

        # Clean old entries
        _rate_tracker[ip] = [t for t in _rate_tracker[ip] if now - t < 60]

        if len(_rate_tracker[ip]) >= _RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded"}), 429

        _rate_tracker[ip].append(now)

        return f(*args, **kwargs)
    return decorated
