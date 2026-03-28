# Facial Recognition Badge System

Automatic badge printing using a Raspberry Pi kiosk at the office window.
A person presses a button, holds their driver's license to the camera, and
the system reads it via OCR + face extraction, then securely sends the data
to a badge server that triggers Gutenberg to print their badge.

**Two operating modes:**
- **Kiosk mode** (primary): Button-activated license scanning with on-screen guide
- **Passive mode**: Continuous facial recognition against an enrolled database

## Architecture

```
┌──────────────────────────┐     WireGuard VPN      ┌─────────────────────────┐
│   RASPBERRY PI KIOSK     │    (encrypted tunnel)   │   GUTENBERG PC          │
│                          │ ─────────────────────►  │                         │
│  [Button] → Screen on    │   HTTPS + API Key       │  Flask server           │
│  Camera → Show feed      │   POST /api/print-badge │  → Gutenberg adapter    │
│  Hold up license         │   (name + ID only)      │  → Badge printer        │
│  OCR → Extract name/ID   │                         │                         │
│  Confirm → Send          │                         │                         │
└──────────────────────────┘                         └─────────────────────────┘
```

## Security

- **Biometric data stays on the Pi** — only employee ID and name are transmitted
- **WireGuard VPN** encrypts the connection between networks
- **TLS** encrypts the HTTP traffic inside the tunnel
- **API key** authenticates requests (constant-time comparison)
- **Rate limiting** prevents abuse
- **Audit log** records all recognition events and badge prints
- **Optional encryption** for the face encoding database at rest

## Quick Start

### 1. Set up the Raspberry Pi

```bash
git clone <repo-url> && cd Cluade/badge-system

# Install dependencies (takes 30-60 min for dlib compilation)
bash scripts/setup_pi.sh

# Test the kiosk (keyboard mode, no GPIO needed, no server needed)
source .venv/bin/activate
cd pi
python kiosk.py --no-gpio --dry-run
# Press SPACE → hold license to camera → SPACE to capture → ENTER to confirm

# Or test the license reader directly
python license_reader.py --camera
# Press SPACE to capture, see parsed fields
```

### 2. Set up the Badge Server (Gutenberg PC)

```bash
cd badge-system
pip install -r requirements-server.txt

# Generate TLS certificates
bash scripts/generate_certs.sh

# Generate a shared API key
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy the output — you'll need it for both machines

# Configure
cp .env.example .env
# Edit .env: set BADGE_API_KEY, GUTENBERG_MODE, etc.

# Start the server
source .env
python server/app.py --tls
```

### 3. Set up WireGuard VPN (both machines)

Since the Pi and Gutenberg PC are on different networks:

```bash
# On the server:
bash scripts/setup_wireguard.sh server

# On the Pi:
bash scripts/setup_wireguard.sh pi

# Exchange public keys and configure as instructed
# Test: ping 10.0.0.1 (from Pi) / ping 10.0.0.2 (from server)
```

### 4. Run

```bash
# On the server:
BADGE_API_KEY=your-key python server/app.py --tls

# On the Pi — Kiosk mode (license scanning):
BADGE_API_KEY=your-key BADGE_SERVER_URL=https://10.0.0.1:5000 python pi/kiosk.py

# Or — Passive mode (facial recognition):
BADGE_API_KEY=your-key BADGE_SERVER_URL=https://10.0.0.1:5000 python pi/recognize.py
```

### 5. Enroll Real People (for passive recognition mode)

```bash
# Delete synthetic data
rm pi/known_faces.pkl

# Enroll each person
python pi/enroll.py --id EMP-001 --name "Jane Doe" --dept "Engineering" --photos /path/to/photos/
python pi/enroll.py --id EMP-002 --name "John Smith" --dept "Sales" --capture 5
```

## Project Structure

```
badge-system/
├── pi/                         # Raspberry Pi code
│   ├── config.py               # Settings (from env vars)
│   ├── kiosk.py                # KIOSK MODE: button → camera → OCR → badge
│   ├── license_reader.py       # Driver's license OCR + face extraction
│   ├── recognize.py            # PASSIVE MODE: continuous face recognition
│   ├── enroll.py               # Enroll people (photos or camera)
│   ├── encodings_db.py         # Face encoding database manager
│   └── sample_data/
│       └── generate_synthetic.py  # Generate test data
│
├── server/                     # Badge server code (Gutenberg PC)
│   ├── app.py                  # Flask HTTPS server
│   ├── auth.py                 # API key authentication
│   ├── gutenberg_adapter.py    # Gutenberg integration (4 modes)
│   ├── badge_template.py       # Badge image renderer (Pillow)
│   └── certs/                  # TLS certificates (gitignored)
│
├── shared/
│   └── models.py               # Shared data models
│
├── scripts/
│   ├── generate_certs.sh       # Generate TLS certificates
│   ├── setup_wireguard.sh      # WireGuard VPN setup
│   ├── setup_pi.sh             # Pi dependency installer
│   └── test_end_to_end.py      # Full system test
│
├── .env.example                # Environment variable template
├── requirements-pi.txt         # Pi Python dependencies
└── requirements-server.txt     # Server Python dependencies
```

## Gutenberg Integration Modes

Set `GUTENBERG_MODE` in your `.env`:

| Mode | Description |
|------|-------------|
| `watched_folder` | Drop JSON files into a directory Gutenberg monitors (default, most compatible) |
| `cli` | Invoke Gutenberg's command-line interface |
| `api` | Call Gutenberg's REST API |
| `direct_print` | Render badge image with Pillow and send to system printer |

## Hardware Requirements

- **Raspberry Pi 4 or 5** (2GB+ RAM recommended)
- **USB webcam** or **Pi Camera Module** (CSI)
- **Display** — HDMI monitor or Pi DSI touchscreen (for kiosk mode)
- **Push button** — connected to GPIO pin 17 (or any configurable pin)
- **MicroSD card** (16GB+)
- **Power supply** for the Pi
- **Badge printer** connected to the Gutenberg PC

### GPIO Wiring (Kiosk Button)

```
GPIO 17 ──── [Button] ──── GND
```

The button uses an internal pull-up resistor. Pressing connects GPIO 17 to
ground, triggering the scan. No external resistor needed.

You can also use keyboard SPACE as a fallback with `--no-gpio`.

## End-to-End Test

```bash
# Local components only (no server needed):
python scripts/test_end_to_end.py --local-only

# Full test (server must be running):
BADGE_API_KEY=your-key python scripts/test_end_to_end.py
```
