#!/usr/bin/env python3
"""
Enrollment script: Register a person's face into the recognition database.

Usage:
    # Enroll from a directory of photos:
    python enroll.py --id emp_042 --name "Jane Doe" --dept "Engineering" \
                     --photos ./photos/jane/

    # Enroll from a single photo:
    python enroll.py --id emp_042 --name "Jane Doe" --dept "Engineering" \
                     --photos ./photos/jane.jpg

    # Enroll by capturing from the camera (takes 5 shots):
    python enroll.py --id emp_042 --name "Jane Doe" --dept "Engineering" \
                     --capture 5

    # Optional fields:
    python enroll.py --id emp_042 --name "Jane Doe" --dept "Engineering" \
                     --title "Sr. Engineer" --badge "B-0042" --photos ./photos/jane/
"""

import argparse
import sys
import time
from pathlib import Path

import face_recognition
import cv2

from encodings_db import load_db, save_db, add_person
from config import ENCODINGS_FILE, CAMERA_INDEX


def encode_from_images(image_paths: list) -> list:
    """Extract face encodings from a list of image file paths.

    Returns list of 128-d numpy arrays. Skips images where no face is found.
    """
    encodings = []
    for path in image_paths:
        print(f"  Processing {path}...")
        image = face_recognition.load_image_file(str(path))
        found = face_recognition.face_encodings(image)
        if found:
            encodings.append(found[0])
            print(f"    -> Face found and encoded")
        else:
            print(f"    -> WARNING: No face detected, skipping")
    return encodings


def encode_from_camera(num_captures: int) -> list:
    """Capture photos from the camera and extract face encodings.

    Gives the user a countdown before each capture. Press 'q' to abort.
    """
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return []

    encodings = []
    print(f"Will capture {num_captures} photos. Look at the camera.")
    print("Press 'q' in the preview window to abort.\n")

    for i in range(num_captures):
        print(f"Capture {i + 1}/{num_captures} - get ready...")

        # Show preview for 3 seconds
        for countdown in range(3, 0, -1):
            ret, frame = cap.read()
            if not ret:
                continue
            display = frame.copy()
            cv2.putText(display, str(countdown), (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 255, 0), 4)
            cv2.imshow("Enrollment", display)
            if cv2.waitKey(1000) & 0xFF == ord('q'):
                print("Aborted by user")
                cap.release()
                cv2.destroyAllWindows()
                return encodings

        # Capture
        ret, frame = cap.read()
        if not ret:
            print("  -> Failed to capture frame")
            continue

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        found = face_recognition.face_encodings(rgb_frame)
        if found:
            encodings.append(found[0])
            print(f"  -> Captured and encoded successfully")
        else:
            print(f"  -> No face detected in capture, try again")

        time.sleep(0.5)

    cap.release()
    cv2.destroyAllWindows()
    return encodings


def main():
    parser = argparse.ArgumentParser(description="Enroll a person into the face recognition database")
    parser.add_argument("--id", required=True, help="Unique employee ID (e.g., emp_042)")
    parser.add_argument("--name", required=True, help="Full name")
    parser.add_argument("--dept", default="", help="Department")
    parser.add_argument("--title", default="", help="Job title")
    parser.add_argument("--badge", default="", help="Badge number")
    parser.add_argument("--photos", help="Path to photo file or directory of photos")
    parser.add_argument("--capture", type=int, help="Number of photos to capture from camera")
    parser.add_argument("--db", default=ENCODINGS_FILE, help="Path to encodings database file")

    args = parser.parse_args()

    if not args.photos and not args.capture:
        parser.error("Provide either --photos or --capture")

    print(f"Enrolling: {args.name} (ID: {args.id})")
    print(f"Database:  {args.db}\n")

    # Get face encodings
    encodings = []

    if args.photos:
        photo_path = Path(args.photos)
        if photo_path.is_file():
            image_paths = [photo_path]
        elif photo_path.is_dir():
            image_paths = sorted(
                p for p in photo_path.iterdir()
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")
            )
        else:
            print(f"ERROR: {args.photos} is not a valid file or directory")
            sys.exit(1)

        if not image_paths:
            print("ERROR: No image files found")
            sys.exit(1)

        print(f"Found {len(image_paths)} image(s)")
        encodings = encode_from_images(image_paths)

    if args.capture:
        camera_encodings = encode_from_camera(args.capture)
        encodings.extend(camera_encodings)

    if not encodings:
        print("\nERROR: No face encodings could be extracted. Cannot enroll.")
        sys.exit(1)

    # Save to database
    db = load_db(args.db)
    if args.id in db:
        existing_count = len(db[args.id]["encodings"])
        print(f"\nUpdating existing record (had {existing_count} encodings)")

    db = add_person(db, args.id, args.name, args.dept, encodings,
                    title=args.title, badge_number=args.badge)
    save_db(args.db, db)

    print(f"\nSuccess! Enrolled {args.name} with {len(encodings)} encoding(s)")
    print(f"Total people in database: {len(db)}")


if __name__ == "__main__":
    main()
