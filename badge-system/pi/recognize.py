#!/usr/bin/env python3
"""
Main recognition loop: captures frames from the camera, detects and matches
faces against the enrolled database, and sends recognition events to the
badge server over HTTPS.

Usage:
    # Run with defaults from config.py / environment:
    python recognize.py

    # Override settings:
    BADGE_SERVER_URL=https://10.0.0.1:5000 BADGE_API_KEY=mykey python recognize.py

    # Dry run (no server calls, just prints matches):
    python recognize.py --dry-run

    # Show camera preview window:
    python recognize.py --preview
"""

import argparse
import json
import sys
import time
from datetime import datetime

import cv2
import face_recognition
import numpy as np
import requests

from config import (
    BADGE_SERVER_URL, API_KEY, TLS_CERT_PATH,
    CONFIDENCE_THRESHOLD, DETECTION_MODEL, ENCODINGS_FILE,
    CAMERA_INDEX, FRAME_SKIP, DETECTION_SCALE,
    COOLDOWN_SECONDS, DEVICE_ID,
)
from encodings_db import load_db, get_all_encodings


class CooldownTracker:
    """Prevents re-triggering badge prints for the same person."""

    def __init__(self, cooldown_seconds: int):
        self.cooldown = cooldown_seconds
        self._last_seen = {}  # employee_id -> timestamp

    def should_trigger(self, employee_id: str) -> bool:
        now = time.time()
        last = self._last_seen.get(employee_id, 0)
        if now - last >= self.cooldown:
            self._last_seen[employee_id] = now
            return True
        return False

    def time_remaining(self, employee_id: str) -> int:
        elapsed = time.time() - self._last_seen.get(employee_id, 0)
        return max(0, int(self.cooldown - elapsed))


def send_recognition_event(employee_id: str, name: str, department: str,
                           confidence: float, dry_run: bool = False) -> bool:
    """POST a recognition event to the badge server.

    Returns True if the server accepted the request (or if dry_run).
    """
    payload = {
        "employee_id": employee_id,
        "name": name,
        "department": department,
        "confidence": round(confidence, 4),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "device_id": DEVICE_ID,
    }

    if dry_run:
        print(f"  [DRY RUN] Would send: {json.dumps(payload)}")
        return True

    if not API_KEY:
        print("  WARNING: No API key set (BADGE_API_KEY). Skipping server call.")
        return False

    url = f"{BADGE_SERVER_URL}/api/print-badge"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    # Determine TLS verification
    verify = True
    if TLS_CERT_PATH:
        if TLS_CERT_PATH.lower() == "false":
            verify = False  # Development only!
        else:
            verify = TLS_CERT_PATH

    try:
        resp = requests.post(url, json=payload, headers=headers,
                             verify=verify, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            print(f"  -> Badge queued: {result.get('badge_job_id', 'unknown')}")
            return True
        else:
            print(f"  -> Server error {resp.status_code}: {resp.text[:200]}")
            return False
    except requests.exceptions.ConnectionError:
        print("  -> ERROR: Cannot reach badge server. Is VPN connected?")
        return False
    except requests.exceptions.Timeout:
        print("  -> ERROR: Server request timed out")
        return False
    except Exception as e:
        print(f"  -> ERROR: {e}")
        return False


def run_recognition_loop(dry_run: bool = False, show_preview: bool = False):
    """Main loop: capture frames, detect faces, match, and send events."""

    # Load the face database
    print(f"Loading face database from {ENCODINGS_FILE}...")
    db = load_db(ENCODINGS_FILE)
    if not db:
        print("ERROR: No faces enrolled. Run enroll.py first.")
        sys.exit(1)

    known_encodings, known_ids = get_all_encodings(db)
    print(f"Loaded {len(db)} people ({len(known_encodings)} total encodings)")
    print(f"Detection model: {DETECTION_MODEL}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print(f"Cooldown: {COOLDOWN_SECONDS}s")
    if dry_run:
        print("MODE: Dry run (no server calls)")
    print()

    # Open camera
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera {CAMERA_INDEX}")
        sys.exit(1)

    cooldown = CooldownTracker(COOLDOWN_SECONDS)
    frame_count = 0
    print("Recognition active. Press Ctrl+C to stop.")
    if show_preview:
        print("Preview window open. Press 'q' in the window to stop.")
    print("-" * 50)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Failed to read frame, retrying...")
                time.sleep(0.1)
                continue

            frame_count += 1

            # Only process every Nth frame
            if frame_count % FRAME_SKIP != 0:
                if show_preview:
                    cv2.imshow("Badge Recognition", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue

            # Downscale for faster detection
            small = cv2.resize(frame, (0, 0),
                               fx=DETECTION_SCALE, fy=DETECTION_SCALE)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            # Detect faces
            face_locations = face_recognition.face_locations(
                rgb_small, model=DETECTION_MODEL
            )

            if not face_locations:
                if show_preview:
                    cv2.imshow("Badge Recognition", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue

            # Get encodings for detected faces
            face_encodings = face_recognition.face_encodings(
                rgb_small, face_locations
            )

            for face_encoding, face_location in zip(face_encodings, face_locations):
                # Compare against all known faces
                distances = face_recognition.face_distance(
                    known_encodings, face_encoding
                )

                if len(distances) == 0:
                    continue

                best_idx = np.argmin(distances)
                best_distance = distances[best_idx]

                # Check if it's a match (lower distance = better match)
                if best_distance > CONFIDENCE_THRESHOLD:
                    label = "Unknown"
                    if show_preview:
                        _draw_face_box(frame, face_location, label, (0, 0, 255))
                    continue

                # We have a match
                employee_id = known_ids[best_idx]
                person = db[employee_id]
                name = person["name"]
                department = person["department"]
                confidence = 1.0 - best_distance  # Convert distance to confidence

                if show_preview:
                    label = f"{name} ({confidence:.0%})"
                    _draw_face_box(frame, face_location, label, (0, 255, 0))

                # Check cooldown
                if not cooldown.should_trigger(employee_id):
                    remaining = cooldown.time_remaining(employee_id)
                    continue

                # Send to badge server
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] MATCH: {name} (ID: {employee_id}, "
                      f"confidence: {confidence:.1%})")
                send_recognition_event(
                    employee_id, name, department, confidence, dry_run
                )

            if show_preview:
                cv2.imshow("Badge Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("\nStopping recognition...")
    finally:
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()
        print("Camera released. Goodbye.")


def _draw_face_box(frame, face_location, label, color):
    """Draw a bounding box and label on the frame (scaled back up)."""
    scale = 1.0 / DETECTION_SCALE
    top, right, bottom, left = face_location
    top = int(top * scale)
    right = int(right * scale)
    bottom = int(bottom * scale)
    left = int(left * scale)

    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
    cv2.rectangle(frame, (left, bottom - 25), (right, bottom), color, cv2.FILLED)
    cv2.putText(frame, label, (left + 6, bottom - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def main():
    parser = argparse.ArgumentParser(description="Facial recognition badge system")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without sending to server")
    parser.add_argument("--preview", action="store_true",
                        help="Show camera preview window")
    args = parser.parse_args()

    run_recognition_loop(dry_run=args.dry_run, show_preview=args.preview)


if __name__ == "__main__":
    main()
