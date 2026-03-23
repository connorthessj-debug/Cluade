"""
Face encoding database manager.

Stores face encodings and metadata in an encrypted pickle file.
Each person can have multiple encodings (different angles/lighting)
for better recognition accuracy.

Database structure:
{
    "emp_001": {
        "name": "Jane Doe",
        "department": "Engineering",
        "title": "Software Engineer",
        "badge_number": "B-0042",
        "encodings": [<128-d numpy array>, ...]
    },
    ...
}
"""

import os
import pickle
import hashlib
from pathlib import Path

import numpy as np

# Optional encryption support
try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def _get_cipher():
    """Get Fernet cipher from environment variable."""
    key = os.environ.get("BADGE_ENCRYPTION_KEY", "")
    if not key or not HAS_CRYPTO:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def load_db(path: str) -> dict:
    """Load face encoding database from a pickle file.

    If BADGE_ENCRYPTION_KEY is set and cryptography is installed,
    the file is decrypted before loading.
    """
    if not Path(path).exists():
        return {}

    raw = Path(path).read_bytes()
    cipher = _get_cipher()
    if cipher:
        raw = cipher.decrypt(raw)

    return pickle.loads(raw)


def save_db(path: str, db: dict) -> None:
    """Save face encoding database to a pickle file.

    If BADGE_ENCRYPTION_KEY is set and cryptography is installed,
    the file is encrypted before saving.
    """
    raw = pickle.dumps(db)
    cipher = _get_cipher()
    if cipher:
        raw = cipher.encrypt(raw)

    Path(path).write_bytes(raw)


def add_person(db: dict, employee_id: str, name: str, department: str,
               encodings: list, title: str = "", badge_number: str = "") -> dict:
    """Add or update a person in the database.

    Args:
        db: The encoding database dict.
        employee_id: Unique employee identifier.
        name: Full name.
        department: Department name.
        encodings: List of 128-d numpy face encoding arrays.
        title: Job title (optional).
        badge_number: Badge number (optional).

    Returns:
        Updated database dict.
    """
    db[employee_id] = {
        "name": name,
        "department": department,
        "title": title,
        "badge_number": badge_number,
        "encodings": encodings,
    }
    return db


def remove_person(db: dict, employee_id: str) -> dict:
    """Remove a person from the database."""
    db.pop(employee_id, None)
    return db


def get_all_encodings(db: dict) -> tuple:
    """Extract all encodings and their employee IDs for matching.

    Returns:
        (known_encodings, known_ids) where known_encodings is a list of
        128-d numpy arrays and known_ids is the corresponding employee ID
        for each encoding.
    """
    known_encodings = []
    known_ids = []
    for emp_id, record in db.items():
        for encoding in record["encodings"]:
            known_encodings.append(encoding)
            known_ids.append(emp_id)
    return known_encodings, known_ids


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key. Store this securely."""
    if not HAS_CRYPTO:
        raise RuntimeError("Install cryptography: pip install cryptography")
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    # Quick test
    db = {}
    fake_encoding = np.random.randn(128)
    db = add_person(db, "test_001", "Test User", "QA", [fake_encoding])
    save_db("test_db.pkl", db)
    loaded = load_db("test_db.pkl")
    assert "test_001" in loaded
    assert loaded["test_001"]["name"] == "Test User"
    assert len(loaded["test_001"]["encodings"]) == 1
    os.remove("test_db.pkl")
    print("encodings_db: all tests passed")
