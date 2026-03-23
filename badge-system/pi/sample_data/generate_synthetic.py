#!/usr/bin/env python3
"""
Generate a synthetic face encoding database for testing.

Uses the Labeled Faces in the Wild (LFW) dataset from scikit-learn or
the Olivetti faces dataset as a fallback. Creates fake employee profiles
with real face encodings so you can test the full system without real
employee data.

Usage:
    # Generate 20 synthetic employees using LFW dataset:
    python generate_synthetic.py --count 20 --output ../known_faces.pkl

    # Use Olivetti dataset (smaller, no download needed):
    python generate_synthetic.py --source olivetti --count 10 --output ../known_faces.pkl

    # Use a local directory of face images:
    python generate_synthetic.py --source local --local-dir ./my_faces/ --output ../known_faces.pkl

When real employee photos become available, delete the synthetic database
and re-enroll using enroll.py with real photos.
"""

import argparse
import os
import random
import sys
from pathlib import Path

import numpy as np

# Add parent directory to path so we can import from pi/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from encodings_db import save_db, add_person

# Sample data for generating fake profiles
FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn",
    "Avery", "Dakota", "Skyler", "Jamie", "Drew", "Cameron", "Reese",
    "Finley", "Sage", "River", "Hayden", "Emerson", "Rowan",
    "Sam", "Pat", "Chris", "Robin", "Leslie", "Dana", "Kim",
    "Shannon", "Terry", "Blair",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Jackson", "White", "Harris", "Martin", "Thompson", "Robinson",
    "Clark", "Lewis", "Lee", "Walker", "Hall", "Allen", "Young",
    "King", "Wright", "Lopez", "Hill",
]

DEPARTMENTS = [
    "Engineering", "Marketing", "Sales", "Operations", "Human Resources",
    "Finance", "Legal", "Customer Success", "Product", "Design",
]

TITLES = [
    "Associate", "Specialist", "Analyst", "Coordinator", "Manager",
    "Senior Manager", "Director", "VP", "Engineer", "Senior Engineer",
]


def generate_profile(index: int) -> dict:
    """Generate a fake employee profile."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    dept = random.choice(DEPARTMENTS)
    title = random.choice(TITLES)

    return {
        "employee_id": f"EMP-{index:04d}",
        "name": f"{first} {last}",
        "department": dept,
        "title": f"{title}, {dept}",
        "badge_number": f"B-{random.randint(1000, 9999)}",
    }


def load_lfw_faces(count: int):
    """Load face images from the LFW dataset via scikit-learn.

    Downloads automatically on first use (~200MB).
    Returns list of (name, [images]) tuples.
    """
    try:
        from sklearn.datasets import fetch_lfw_people
    except ImportError:
        print("ERROR: scikit-learn required for LFW. Install with:")
        print("  pip install scikit-learn")
        sys.exit(1)

    print("Loading LFW dataset (may download ~200MB on first run)...")
    lfw = fetch_lfw_people(min_faces_per_person=3, resize=1.0)

    # Group images by person
    from collections import defaultdict
    person_images = defaultdict(list)
    for img, label in zip(lfw.images, lfw.target):
        person_images[label].append(img)

    # Select people with enough images
    selected = []
    for label, images in person_images.items():
        if len(selected) >= count:
            break
        if len(images) >= 2:
            selected.append((lfw.target_names[label], images[:5]))

    return selected


def load_olivetti_faces(count: int):
    """Load face images from the Olivetti dataset (40 people, 10 each).

    Small dataset, included in scikit-learn, no download needed.
    """
    try:
        from sklearn.datasets import fetch_olivetti_faces
    except ImportError:
        print("ERROR: scikit-learn required. Install with:")
        print("  pip install scikit-learn")
        sys.exit(1)

    print("Loading Olivetti faces dataset...")
    data = fetch_olivetti_faces()

    # 40 people, 10 images each
    selected = []
    for person_id in range(min(count, 40)):
        start = person_id * 10
        images = data.images[start:start + 10]
        # Olivetti images are 64x64 grayscale, scale up for face_recognition
        selected.append((f"Person_{person_id}", images[:5]))

    return selected


def load_local_faces(local_dir: str, count: int):
    """Load face images from a local directory.

    Expected structure:
        local_dir/
            person1/
                photo1.jpg
                photo2.jpg
            person2/
                photo1.jpg
    """
    import face_recognition

    local_path = Path(local_dir)
    if not local_path.is_dir():
        print(f"ERROR: {local_dir} is not a directory")
        sys.exit(1)

    selected = []
    for person_dir in sorted(local_path.iterdir()):
        if len(selected) >= count:
            break
        if not person_dir.is_dir():
            continue

        images = []
        for img_path in sorted(person_dir.iterdir()):
            if img_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                img = face_recognition.load_image_file(str(img_path))
                images.append(img)

        if images:
            selected.append((person_dir.name, images[:5]))

    return selected


def encode_faces(people_images: list) -> list:
    """Convert image arrays to face encodings.

    Args:
        people_images: List of (name, [image_arrays]) tuples.

    Returns:
        List of (name, [128-d encoding arrays]) tuples.
    """
    import face_recognition

    results = []
    for name, images in people_images:
        encodings = []
        for img in images:
            # Handle grayscale images (Olivetti)
            if len(img.shape) == 2:
                img = np.stack([img] * 3, axis=-1)
                # Scale from 0-1 float to 0-255 uint8 if needed
                if img.max() <= 1.0:
                    img = (img * 255).astype(np.uint8)

            # Resize small images (Olivetti is 64x64, too small for face_recognition)
            if img.shape[0] < 100 or img.shape[1] < 100:
                from PIL import Image
                pil_img = Image.fromarray(img)
                pil_img = pil_img.resize((250, 250), Image.LANCZOS)
                img = np.array(pil_img)

            found = face_recognition.face_encodings(img)
            if found:
                encodings.append(found[0])

        if encodings:
            results.append((name, encodings))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic face encoding database for testing"
    )
    parser.add_argument("--count", type=int, default=20,
                        help="Number of synthetic employees (default: 20)")
    parser.add_argument("--source", choices=["lfw", "olivetti", "local"],
                        default="olivetti",
                        help="Face dataset source (default: olivetti)")
    parser.add_argument("--local-dir", help="Directory of face images (for --source local)")
    parser.add_argument("--output", default="../known_faces.pkl",
                        help="Output database path (default: ../known_faces.pkl)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")

    args = parser.parse_args()
    random.seed(args.seed)

    if args.source == "local" and not args.local_dir:
        parser.error("--local-dir required when --source is local")

    # Load face images
    print(f"Source: {args.source}")
    if args.source == "lfw":
        people = load_lfw_faces(args.count)
    elif args.source == "olivetti":
        people = load_olivetti_faces(args.count)
    else:
        people = load_local_faces(args.local_dir, args.count)

    if not people:
        print("ERROR: No face images loaded")
        sys.exit(1)

    print(f"Loaded {len(people)} people from dataset")

    # Generate face encodings
    print("Generating face encodings (this may take a minute)...")
    encoded_people = encode_faces(people)
    print(f"Successfully encoded {len(encoded_people)} people")

    if not encoded_people:
        print("ERROR: Could not encode any faces")
        sys.exit(1)

    # Build the database with fake profiles
    db = {}
    for i, (_, encodings) in enumerate(encoded_people[:args.count]):
        profile = generate_profile(i + 1)
        db = add_person(
            db,
            employee_id=profile["employee_id"],
            name=profile["name"],
            department=profile["department"],
            encodings=encodings,
            title=profile["title"],
            badge_number=profile["badge_number"],
        )

    # Save
    output_path = str(Path(args.output).resolve())
    save_db(output_path, db)
    print(f"\nSaved {len(db)} synthetic employees to {output_path}")
    print("\nSample entries:")
    for emp_id, record in list(db.items())[:3]:
        print(f"  {emp_id}: {record['name']} - {record['department']} "
              f"({len(record['encodings'])} encodings)")

    print(f"\nTo test recognition, run:")
    print(f"  cd .. && python recognize.py --dry-run --preview")


if __name__ == "__main__":
    main()
