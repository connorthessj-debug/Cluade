"""
Configuration for the Raspberry Pi facial recognition module.

All secrets (API key, server URL) are loaded from environment variables.
Copy .env.example to .env and fill in your values.
"""

import os

# --- Server Connection ---
# The badge server URL. When using WireGuard VPN, this is the server's
# VPN IP address (e.g., 10.0.0.1). Set via BADGE_SERVER_URL env var.
BADGE_SERVER_URL = os.environ.get("BADGE_SERVER_URL", "https://10.0.0.1:5000")

# API key shared between Pi and server. Generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
API_KEY = os.environ.get("BADGE_API_KEY", "")

# Path to the server's TLS certificate for verification.
# Set to False (string "false") to skip verification during development ONLY.
TLS_CERT_PATH = os.environ.get("BADGE_TLS_CERT", "")

# --- Face Recognition ---
# Distance threshold for face matching. Lower = stricter.
# 0.6 is the default; 0.45 is recommended for higher accuracy.
CONFIDENCE_THRESHOLD = float(os.environ.get("BADGE_CONFIDENCE", "0.45"))

# Use "hog" on Raspberry Pi (CPU-only), "cnn" if you have a GPU/Coral TPU.
DETECTION_MODEL = os.environ.get("BADGE_DETECTION_MODEL", "hog")

# Path to the face encodings database (pickle file).
ENCODINGS_FILE = os.environ.get("BADGE_ENCODINGS_FILE", "known_faces.pkl")

# --- Camera ---
CAMERA_INDEX = int(os.environ.get("BADGE_CAMERA_INDEX", "0"))

# Process every Nth frame to save CPU. Higher = less CPU but slower detection.
FRAME_SKIP = int(os.environ.get("BADGE_FRAME_SKIP", "5"))

# Scale factor for face detection (0.25 = 1/4 resolution). Lower = faster.
DETECTION_SCALE = float(os.environ.get("BADGE_DETECTION_SCALE", "0.25"))

# --- Cooldown ---
# Don't re-trigger a badge print for the same person within this many seconds.
COOLDOWN_SECONDS = int(os.environ.get("BADGE_COOLDOWN", "300"))

# --- Device Identity ---
DEVICE_ID = os.environ.get("BADGE_DEVICE_ID", "pi-front-desk-01")

# --- Kiosk Mode (license scanning) ---
# GPIO pin for the physical trigger button (BCM numbering).
KIOSK_GPIO_PIN = int(os.environ.get("KIOSK_GPIO_PIN", "17"))

# Seconds to show camera feed before auto-capturing. 0 = manual only.
KIOSK_COUNTDOWN_SECONDS = int(os.environ.get("KIOSK_COUNTDOWN", "10"))

# Return to idle screen after this many seconds of inactivity.
KIOSK_IDLE_TIMEOUT = int(os.environ.get("KIOSK_IDLE_TIMEOUT", "10"))

# Window title for the kiosk display.
KIOSK_WINDOW_NAME = os.environ.get("KIOSK_WINDOW_NAME", "Badge Kiosk")
