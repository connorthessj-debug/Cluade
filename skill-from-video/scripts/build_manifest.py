#!/usr/bin/env python3
"""Build manifest.json mapping each frame to its transcript window.

Reads:
  <workdir>/frames/timestamps.json  {"0001.jpg": 12.4, ...}
  <workdir>/transcript.txt           "[mm:ss] line\n..."

Writes:
  <workdir>/manifest.json
    [{"frame_path": "frames/0001.jpg",
      "timestamp": 12.4,
      "transcript_window": "..."}, ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WINDOW_SECONDS = 5.0
TS_RE = re.compile(r"^\[(\d{2}):(\d{2})\]\s*(.*)$")


def parse_transcript(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for line in text.splitlines():
        m = TS_RE.match(line.strip())
        if not m:
            continue
        ts = int(m.group(1)) * 60 + int(m.group(2))
        out.append((float(ts), m.group(3).strip()))
    return out


def window(transcript: list[tuple[float, str]], center: float, half: float = WINDOW_SECONDS) -> str:
    lo, hi = center - half, center + half
    return " ".join(text for ts, text in transcript if lo <= ts <= hi).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    ts_path = workdir / "frames" / "timestamps.json"
    if not ts_path.exists():
        print(f"ERROR: {ts_path} not found. Run extract_frames.py first.", file=sys.stderr)
        return 1

    timestamps: dict[str, float] = json.loads(ts_path.read_text())
    transcript_text = (workdir / "transcript.txt").read_text(encoding="utf-8") if (workdir / "transcript.txt").exists() else ""
    transcript = parse_transcript(transcript_text)

    manifest = []
    for fname, ts in sorted(timestamps.items()):
        manifest.append({
            "frame_path": f"frames/{fname}",
            "timestamp": ts,
            "transcript_window": window(transcript, ts),
        })

    out_path = workdir / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({
        "manifest_path": str(out_path),
        "frame_count": len(manifest),
        "transcript_lines": len(transcript),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
