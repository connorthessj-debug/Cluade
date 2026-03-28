#!/bin/bash
# Raspberry Pi setup script for the facial recognition badge system.
#
# This installs all dependencies on a fresh Raspberry Pi OS (Bookworm).
# Tested on Pi 4 and Pi 5.
#
# WARNING: Compiling dlib takes 30-60 minutes on a Pi 4.
#
# Usage:
#   bash scripts/setup_pi.sh

set -e

echo "=== Badge System - Raspberry Pi Setup ==="
echo
echo "This will install:"
echo "  - Python 3 build dependencies"
echo "  - OpenCV"
echo "  - dlib + face_recognition"
echo "  - Other Python packages"
echo
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo
echo "=== Step 1: System packages ==="
sudo apt update
sudo apt install -y \
    python3-pip python3-venv python3-dev \
    cmake build-essential \
    libopenblas-dev liblapack-dev \
    libatlas-base-dev gfortran \
    libhdf5-dev libhdf5-serial-dev \
    libjpeg-dev libpng-dev libtiff-dev \
    libavcodec-dev libavformat-dev libswscale-dev \
    libv4l-dev libxvidcore-dev libx264-dev \
    libgtk-3-dev libcanberra-gtk3-module \
    libboost-all-dev \
    tesseract-ocr

echo
echo "=== Step 2: Python virtual environment ==="
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate

echo
echo "=== Step 3: Python packages (except dlib) ==="
pip install --upgrade pip setuptools wheel
pip install numpy opencv-python Pillow requests pytesseract

echo
echo "=== Step 4: dlib (this takes 30-60 minutes on Pi 4) ==="
echo "Compiling dlib from source..."
pip install dlib

echo
echo "=== Step 5: face_recognition ==="
pip install face_recognition

echo
echo "=== Step 6: Optional packages ==="
pip install cryptography  # For encrypted face database

echo
echo "=== Setup Complete ==="
echo
echo "Activate the environment with:"
echo "  source .venv/bin/activate"
echo
echo "Next steps:"
echo "  1. Test kiosk mode:          cd pi && python kiosk.py --no-gpio --dry-run"
echo "  2. Test license reader:      cd pi && python license_reader.py --camera"
echo "  3. Set up WireGuard:         bash scripts/setup_wireguard.sh pi"
echo "  4. Configure environment:    cp .env.example .env && nano .env"
echo
echo "Two operating modes:"
echo "  - Kiosk mode (license scan): python pi/kiosk.py"
echo "  - Passive recognition:       python pi/recognize.py --preview"
