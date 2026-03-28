#!/usr/bin/env python3
"""
Kiosk mode: button-activated license scanning for badge printing.

Workflow:
    1. Screen shows "Press button to scan" idle message
    2. Person presses physical button (GPIO) or keyboard key
    3. Screen shows live camera feed with guide overlay
    4. Person holds driver's license up to the camera
    5. System captures the image, reads the license via OCR
    6. Extracted data is shown on screen for confirmation
    7. On confirm, data is sent to the badge server → Gutenberg prints badge
    8. Returns to idle state

Hardware:
    - Raspberry Pi 4/5 with display (HDMI or DSI touchscreen)
    - USB webcam or Pi Camera Module
    - Physical button on GPIO pin (or keyboard SPACE as fallback)

Usage:
    # With GPIO button on pin 17:
    python kiosk.py

    # Keyboard-only mode (no GPIO, use SPACE to trigger):
    python kiosk.py --no-gpio

    # Dry run (no server calls):
    python kiosk.py --dry-run --no-gpio

    # Custom GPIO pin:
    python kiosk.py --gpio-pin 27
"""

import argparse
import json
import sys
import time
import threading
from datetime import datetime
from enum import Enum

import cv2
import numpy as np
import requests

from config import (
    BADGE_SERVER_URL, API_KEY, TLS_CERT_PATH,
    CAMERA_INDEX, DEVICE_ID,
    KIOSK_GPIO_PIN, KIOSK_COUNTDOWN_SECONDS,
    KIOSK_IDLE_TIMEOUT, KIOSK_WINDOW_NAME,
)
from license_reader import read_license

# Optional GPIO support (only on Raspberry Pi)
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False


class KioskState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    PROCESSING = "processing"
    CONFIRM = "confirm"
    SENDING = "sending"
    SUCCESS = "success"
    ERROR = "error"


# UI Colors (BGR)
COLOR_BG = (40, 40, 40)
COLOR_WHITE = (255, 255, 255)
COLOR_GREEN = (0, 200, 0)
COLOR_RED = (0, 0, 200)
COLOR_BLUE = (200, 100, 0)
COLOR_YELLOW = (0, 220, 255)
COLOR_GUIDE = (0, 255, 255)  # Yellow guide rectangle


class BadgeKiosk:
    """Main kiosk controller."""

    def __init__(self, use_gpio=True, gpio_pin=17, dry_run=False):
        self.state = KioskState.IDLE
        self.use_gpio = use_gpio and HAS_GPIO
        self.gpio_pin = gpio_pin
        self.dry_run = dry_run
        self.button_pressed = False
        self.last_license_data = None
        self.status_message = ""
        self.state_start_time = time.time()

        # Camera
        self.cap = None
        self.frame = None

    def setup_gpio(self):
        """Configure GPIO button with pull-up resistor."""
        if not self.use_gpio:
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(
            self.gpio_pin, GPIO.FALLING,
            callback=self._gpio_callback,
            bouncetime=500,
        )
        print(f"GPIO button configured on pin {self.gpio_pin}")

    def _gpio_callback(self, channel):
        """Called when physical button is pressed."""
        self.button_pressed = True

    def setup_camera(self):
        """Open the camera."""
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            print(f"ERROR: Cannot open camera {CAMERA_INDEX}")
            sys.exit(1)

        # Set resolution for better OCR
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def draw_idle_screen(self, display: np.ndarray):
        """Draw the idle state screen."""
        h, w = display.shape[:2]

        # Dark background
        display[:] = COLOR_BG

        # Title
        _put_centered_text(display, "BADGE KIOSK", w // 2, h // 4,
                           cv2.FONT_HERSHEY_SIMPLEX, 2.0, COLOR_WHITE, 3)

        # Instruction
        if self.use_gpio:
            msg = "Press the button to scan your license"
        else:
            msg = "Press SPACE to scan your license"

        _put_centered_text(display, msg, w // 2, h // 2,
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, COLOR_BLUE, 2)

        # Blinking indicator
        if int(time.time() * 2) % 2:
            _put_centered_text(display, "[READY]", w // 2, int(h * 0.65),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_GREEN, 2)

    def draw_scanning_screen(self, display: np.ndarray, frame: np.ndarray):
        """Draw the scanning state with camera feed and guide overlay."""
        h, w = display.shape[:2]

        # Show camera feed
        resized = cv2.resize(frame, (w, h))
        display[:] = resized

        # Draw license guide rectangle (card aspect ratio ~3.375:2.125)
        card_w = int(w * 0.6)
        card_h = int(card_w * 2.125 / 3.375)
        x1 = (w - card_w) // 2
        y1 = (h - card_h) // 2
        x2 = x1 + card_w
        y2 = y1 + card_h

        # Dashed rectangle guide
        cv2.rectangle(display, (x1, y1), (x2, y2), COLOR_GUIDE, 2)

        # Corner markers for alignment
        corner_len = 30
        for cx, cy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            dx = corner_len if cx == x1 else -corner_len
            dy = corner_len if cy == y1 else -corner_len
            cv2.line(display, (cx, cy), (cx + dx, cy), COLOR_GUIDE, 3)
            cv2.line(display, (cx, cy), (cx, cy + dy), COLOR_GUIDE, 3)

        # Instructions overlay
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)

        _put_centered_text(display, "Hold license inside the frame - Press SPACE to capture",
                           w // 2, 35, cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_WHITE, 2)

        # Countdown or capture prompt
        elapsed = time.time() - self.state_start_time
        if KIOSK_COUNTDOWN_SECONDS > 0:
            remaining = max(0, KIOSK_COUNTDOWN_SECONDS - int(elapsed))
            if remaining > 0:
                _put_centered_text(display, f"Auto-capture in {remaining}s",
                                   w // 2, h - 30, cv2.FONT_HERSHEY_SIMPLEX,
                                   0.6, COLOR_YELLOW, 2)

    def draw_processing_screen(self, display: np.ndarray):
        """Show a processing/reading indicator."""
        h, w = display.shape[:2]
        display[:] = COLOR_BG

        _put_centered_text(display, "Reading license...", w // 2, h // 2 - 30,
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, COLOR_YELLOW, 2)

        # Spinning indicator
        angle = int(time.time() * 360) % 360
        center = (w // 2, h // 2 + 50)
        end_x = int(center[0] + 30 * np.cos(np.radians(angle)))
        end_y = int(center[1] + 30 * np.sin(np.radians(angle)))
        cv2.line(display, center, (end_x, end_y), COLOR_WHITE, 3)

    def draw_confirm_screen(self, display: np.ndarray, data):
        """Show parsed license data for confirmation."""
        h, w = display.shape[:2]
        display[:] = COLOR_BG

        _put_centered_text(display, "License Scanned", w // 2, 50,
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, COLOR_GREEN, 2)

        # Show extracted fields
        fields = data.to_dict()
        y = 120
        for label, value in [
            ("Name", fields["full_name"]),
            ("License #", fields["license_number"]),
            ("DOB", fields["date_of_birth"]),
            ("State", fields["state"]),
        ]:
            if value:
                text = f"{label}: {value}"
                cv2.putText(display, text, (50, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_WHITE, 2)
                y += 45

        # Show face if extracted
        if data.face_image is not None:
            face_h, face_w = data.face_image.shape[:2]
            scale = min(150 / face_w, 150 / face_h)
            face_resized = cv2.resize(data.face_image,
                                      (int(face_w * scale), int(face_h * scale)))
            fh, fw = face_resized.shape[:2]
            x_off = w - fw - 50
            y_off = 100
            display[y_off:y_off + fh, x_off:x_off + fw] = face_resized

        # Confidence
        conf_color = COLOR_GREEN if data.confidence > 0.5 else COLOR_YELLOW
        cv2.putText(display, f"Confidence: {data.confidence:.0%}", (50, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, conf_color, 1)

        # Action buttons
        y_btn = h - 80
        _put_centered_text(display, "ENTER = Print Badge    ESC = Cancel",
                           w // 2, y_btn, cv2.FONT_HERSHEY_SIMPLEX,
                           0.7, COLOR_BLUE, 2)

        if not data.is_valid:
            _put_centered_text(display, "WARNING: Could not read name. Try again?",
                               w // 2, y_btn + 40, cv2.FONT_HERSHEY_SIMPLEX,
                               0.6, COLOR_RED, 2)

    def draw_success_screen(self, display: np.ndarray):
        """Show success after badge is queued."""
        h, w = display.shape[:2]
        display[:] = COLOR_BG

        _put_centered_text(display, "Badge Sent to Printer!", w // 2, h // 2 - 20,
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, COLOR_GREEN, 3)

        _put_centered_text(display, self.status_message, w // 2, h // 2 + 40,
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_WHITE, 1)

    def draw_error_screen(self, display: np.ndarray):
        """Show error state."""
        h, w = display.shape[:2]
        display[:] = COLOR_BG

        _put_centered_text(display, "Error", w // 2, h // 2 - 40,
                           cv2.FONT_HERSHEY_SIMPLEX, 1.5, COLOR_RED, 3)

        _put_centered_text(display, self.status_message, w // 2, h // 2 + 20,
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_WHITE, 1)

        _put_centered_text(display, "Press any key to try again", w // 2, h // 2 + 70,
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_BLUE, 1)

    def send_to_server(self, data) -> bool:
        """Send the scanned license data to the badge server."""
        fields = data.to_dict()

        payload = {
            "employee_id": fields["license_number"] or "WALK-IN",
            "name": fields["full_name"],
            "department": f"Visitor - {fields['state']}" if fields["state"] else "Visitor",
            "confidence": data.confidence,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "device_id": DEVICE_ID,
            "source": "license_scan",
            "license_data": fields,
        }

        if self.dry_run:
            print(f"[DRY RUN] Would send: {json.dumps(payload, indent=2)}")
            self.status_message = f"Badge for {fields['full_name']} (dry run)"
            return True

        if not API_KEY:
            self.status_message = "No API key configured"
            return False

        url = f"{BADGE_SERVER_URL}/api/print-badge"
        headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

        verify = True
        if TLS_CERT_PATH:
            verify = False if TLS_CERT_PATH.lower() == "false" else TLS_CERT_PATH

        try:
            resp = requests.post(url, json=payload, headers=headers,
                                 verify=verify, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                job_id = result.get("badge_job_id", "?")
                self.status_message = f"Badge queued: {job_id}"
                return True
            else:
                self.status_message = f"Server error: {resp.status_code}"
                return False
        except requests.exceptions.ConnectionError:
            self.status_message = "Cannot reach badge server"
            return False
        except Exception as e:
            self.status_message = str(e)
            return False

    def transition(self, new_state: KioskState):
        """Change to a new state and reset timer."""
        self.state = new_state
        self.state_start_time = time.time()

    def run(self):
        """Main kiosk event loop."""
        self.setup_camera()
        if self.use_gpio:
            self.setup_gpio()

        # Create fullscreen window
        cv2.namedWindow(KIOSK_WINDOW_NAME, cv2.WINDOW_NORMAL)

        # Display buffer
        display = np.zeros((720, 1280, 3), dtype=np.uint8)

        print("Kiosk started. Press Q to quit.")
        if not self.use_gpio:
            print("GPIO disabled. Use SPACE to trigger scan.")

        captured_frame = None

        try:
            while True:
                ret, frame = self.cap.read()
                if ret:
                    self.frame = frame

                # Handle state
                if self.state == KioskState.IDLE:
                    self.draw_idle_screen(display)

                    # Check for button press
                    if self.button_pressed:
                        self.button_pressed = False
                        self.transition(KioskState.SCANNING)

                elif self.state == KioskState.SCANNING:
                    if self.frame is not None:
                        self.draw_scanning_screen(display, self.frame)

                    # Auto-capture after countdown
                    elapsed = time.time() - self.state_start_time
                    if KIOSK_COUNTDOWN_SECONDS > 0 and elapsed >= KIOSK_COUNTDOWN_SECONDS:
                        captured_frame = self.frame.copy() if self.frame is not None else None
                        self.transition(KioskState.PROCESSING)

                elif self.state == KioskState.PROCESSING:
                    self.draw_processing_screen(display)
                    cv2.imshow(KIOSK_WINDOW_NAME, display)
                    cv2.waitKey(1)

                    if captured_frame is not None:
                        print("Processing license...")
                        self.last_license_data = read_license(captured_frame)
                        print(f"  Name: {self.last_license_data.full_name or '(not found)'}")
                        print(f"  License #: {self.last_license_data.license_number or '(not found)'}")
                        print(f"  Confidence: {self.last_license_data.confidence:.0%}")
                        self.transition(KioskState.CONFIRM)
                    else:
                        self.status_message = "No frame captured"
                        self.transition(KioskState.ERROR)

                elif self.state == KioskState.CONFIRM:
                    self.draw_confirm_screen(display, self.last_license_data)

                elif self.state == KioskState.SENDING:
                    display[:] = COLOR_BG
                    _put_centered_text(display, "Sending to printer...",
                                       640, 360, cv2.FONT_HERSHEY_SIMPLEX,
                                       1.0, COLOR_YELLOW, 2)
                    cv2.imshow(KIOSK_WINDOW_NAME, display)
                    cv2.waitKey(1)

                    if self.send_to_server(self.last_license_data):
                        self.transition(KioskState.SUCCESS)
                    else:
                        self.transition(KioskState.ERROR)

                elif self.state == KioskState.SUCCESS:
                    self.draw_success_screen(display)
                    if time.time() - self.state_start_time > 3:
                        self.transition(KioskState.IDLE)

                elif self.state == KioskState.ERROR:
                    self.draw_error_screen(display)
                    if time.time() - self.state_start_time > KIOSK_IDLE_TIMEOUT:
                        self.transition(KioskState.IDLE)

                # Show display
                cv2.imshow(KIOSK_WINDOW_NAME, display)

                # Handle keyboard input
                key = cv2.waitKey(16) & 0xFF  # ~60 FPS

                if key == ord('q'):
                    break
                elif key == ord(' '):
                    if self.state == KioskState.IDLE:
                        self.button_pressed = True
                    elif self.state == KioskState.SCANNING:
                        captured_frame = self.frame.copy() if self.frame is not None else None
                        self.transition(KioskState.PROCESSING)
                elif key == 13:  # ENTER
                    if self.state == KioskState.CONFIRM:
                        self.transition(KioskState.SENDING)
                elif key == 27:  # ESC
                    if self.state in (KioskState.SCANNING, KioskState.CONFIRM,
                                      KioskState.ERROR):
                        self.transition(KioskState.IDLE)

                # GPIO button also triggers capture during scanning
                if self.state == KioskState.SCANNING and self.button_pressed:
                    self.button_pressed = False
                    captured_frame = self.frame.copy() if self.frame is not None else None
                    self.transition(KioskState.PROCESSING)

        except KeyboardInterrupt:
            print("\nShutting down kiosk...")
        finally:
            self.cap.release()
            cv2.destroyAllWindows()
            if self.use_gpio and HAS_GPIO:
                GPIO.cleanup()
            print("Kiosk stopped.")


def _put_centered_text(img, text, x, y, font, scale, color, thickness):
    """Draw text centered at (x, y)."""
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    tx = x - text_size[0] // 2
    ty = y + text_size[1] // 2
    cv2.putText(img, text, (tx, ty), font, scale, color, thickness)


def main():
    parser = argparse.ArgumentParser(description="Badge kiosk - license scanning mode")
    parser.add_argument("--no-gpio", action="store_true",
                        help="Disable GPIO, use keyboard only")
    parser.add_argument("--gpio-pin", type=int, default=KIOSK_GPIO_PIN,
                        help=f"GPIO pin for the button (default: {KIOSK_GPIO_PIN})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't send to server")
    args = parser.parse_args()

    kiosk = BadgeKiosk(
        use_gpio=not args.no_gpio,
        gpio_pin=args.gpio_pin,
        dry_run=args.dry_run,
    )
    kiosk.run()


if __name__ == "__main__":
    main()
