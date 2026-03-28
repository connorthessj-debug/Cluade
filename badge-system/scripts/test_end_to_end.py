#!/usr/bin/env python3
"""
End-to-end test: verifies the full pipeline works.

1. Loads the face encoding database
2. Simulates a recognition event
3. Sends it to the badge server
4. Checks that a badge job was created

Usage:
    # Test against a running server:
    BADGE_API_KEY=your-key python scripts/test_end_to_end.py

    # Test just the local components (no server needed):
    python scripts/test_end_to_end.py --local-only
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pi"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))


def test_encodings_db():
    """Test that the encoding database can be loaded."""
    from encodings_db import load_db, get_all_encodings
    from config import ENCODINGS_FILE

    print(f"[TEST] Loading encoding database from {ENCODINGS_FILE}...")
    db = load_db(ENCODINGS_FILE)

    if not db:
        print("[FAIL] Database is empty. Run generate_synthetic.py first.")
        return False

    encodings, ids = get_all_encodings(db)
    print(f"[PASS] Loaded {len(db)} people, {len(encodings)} total encodings")

    # Print first few entries
    for emp_id, record in list(db.items())[:3]:
        print(f"       {emp_id}: {record['name']} ({record['department']})")

    return True


def test_badge_template():
    """Test that badge rendering works."""
    from badge_template import render_badge

    output = "./output/test_badge.png"
    print(f"[TEST] Rendering test badge to {output}...")

    try:
        render_badge(
            name="Test Person",
            employee_id="TEST-001",
            department="Quality Assurance",
            output_path=output,
        )
        if Path(output).exists():
            size = Path(output).stat().st_size
            print(f"[PASS] Badge rendered ({size} bytes)")
            return True
        else:
            print("[FAIL] Badge file not created")
            return False
    except Exception as e:
        print(f"[FAIL] Badge rendering error: {e}")
        return False


def test_gutenberg_adapter():
    """Test that the Gutenberg adapter creates a job file."""
    os.environ.setdefault("GUTENBERG_MODE", "watched_folder")
    os.environ.setdefault("GUTENBERG_WATCH_DIR", "./badge_queue")

    from gutenberg_adapter import GutenbergAdapter

    print("[TEST] Testing Gutenberg adapter (watched_folder mode)...")
    adapter = GutenbergAdapter()
    job_id = adapter.print_badge(
        employee_id="TEST-001",
        name="Test Person",
        department="QA",
        confidence=0.95,
    )

    job_file = Path("./badge_queue") / f"{job_id}.json"
    if job_file.exists():
        data = json.loads(job_file.read_text())
        print(f"[PASS] Job file created: {job_file}")
        print(f"       Job ID: {job_id}")
        print(f"       Template: {data['template']}")
        # Clean up
        job_file.unlink()
        return True
    else:
        print(f"[FAIL] Job file not found: {job_file}")
        return False


def test_server_connection():
    """Test connection to the badge server."""
    import requests

    server_url = os.environ.get("BADGE_SERVER_URL", "https://10.0.0.1:5000")
    api_key = os.environ.get("BADGE_API_KEY", "")
    tls_cert = os.environ.get("BADGE_TLS_CERT", "")

    verify = True
    if tls_cert:
        verify = False if tls_cert.lower() == "false" else tls_cert

    print(f"[TEST] Connecting to badge server at {server_url}...")

    try:
        resp = requests.get(f"{server_url}/api/health", verify=verify, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[PASS] Server is up (mode: {data.get('gutenberg_mode', '?')})")
        else:
            print(f"[FAIL] Server returned {resp.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] Cannot reach server. Is it running? Is VPN connected?")
        return False
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

    # Test badge print endpoint
    if not api_key:
        print("[SKIP] No BADGE_API_KEY set, skipping print test")
        return True

    print(f"[TEST] Sending test badge request...")
    resp = requests.post(
        f"{server_url}/api/print-badge",
        json={
            "employee_id": "TEST-001",
            "name": "Test Person",
            "department": "QA",
            "confidence": 0.95,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "device_id": "test-script",
        },
        headers={"X-API-Key": api_key},
        verify=verify,
        timeout=10,
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"[PASS] Badge queued: {data.get('badge_job_id', '?')}")
        return True
    else:
        print(f"[FAIL] Server returned {resp.status_code}: {resp.text[:200]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="End-to-end test")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip server connection test")
    args = parser.parse_args()

    print("=" * 50)
    print("Badge System - End-to-End Test")
    print("=" * 50)
    print()

    results = []

    results.append(("Encoding Database", test_encodings_db()))
    print()
    results.append(("Badge Template", test_badge_template()))
    print()
    results.append(("Gutenberg Adapter", test_gutenberg_adapter()))
    print()

    if not args.local_only:
        results.append(("Server Connection", test_server_connection()))
    else:
        print("[SKIP] Server connection test (--local-only)")

    print()
    print("=" * 50)
    print("Results:")
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("All tests passed!")
    else:
        print("Some tests failed. Check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
