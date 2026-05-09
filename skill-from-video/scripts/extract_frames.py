#!/usr/bin/env python3
"""Extract scene-change frames from <workdir>/video.mp4.

Iteratively raises the scene threshold until <= MAX_FRAMES (200), and lowers
it (and finally falls back to uniform sampling) to guarantee >= MIN_FRAMES (10)
on short clips.

Outputs:
  <workdir>/frames/0001.jpg, 0002.jpg, ...
  <workdir>/frames/timestamps.json   {"0001.jpg": 12.4, ...}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_FRAMES = 200
MIN_FRAMES = 10
START_THRESHOLD = 0.30


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def probe_duration(mp4: Path) -> float:
    proc = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(mp4),
    ])
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def extract_with_threshold(mp4: Path, frames_dir: Path, threshold: float) -> list[tuple[Path, float]]:
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    pattern = str(frames_dir / "%04d.jpg")
    proc = run([
        "ffmpeg", "-y", "-i", str(mp4),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr",
        "-q:v", "3",
        pattern,
    ])
    # ffmpeg writes showinfo to stderr; parse pts_time per output frame.
    times = re.findall(r"pts_time:([\d.]+)", proc.stderr)
    files = sorted(frames_dir.glob("*.jpg"))
    if len(files) != len(times):
        # Truncate to whichever is shorter; happens occasionally with showinfo.
        n = min(len(files), len(times))
        files = files[:n]
        times = times[:n]
    return [(f, float(t)) for f, t in zip(files, times)]


def extract_uniform(mp4: Path, frames_dir: Path, count: int, duration: float) -> list[tuple[Path, float]]:
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    fps = max(count / max(duration, 1.0), 0.01)
    pattern = str(frames_dir / "%04d.jpg")
    run([
        "ffmpeg", "-y", "-i", str(mp4),
        "-vf", f"fps={fps},showinfo",
        "-vsync", "vfr",
        "-q:v", "3",
        pattern,
    ])
    files = sorted(frames_dir.glob("*.jpg"))[:count]
    if not files:
        return []
    step = duration / max(len(files), 1)
    return [(f, round(step * (i + 0.5), 2)) for i, f in enumerate(files)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    mp4 = workdir / "video.mp4"
    if not mp4.exists():
        print(f"ERROR: {mp4} not found. Run download.py first.", file=sys.stderr)
        return 1

    frames_dir = workdir / "frames"
    duration = probe_duration(mp4)
    print(f"video duration: {duration:.1f}s", file=sys.stderr)

    threshold = START_THRESHOLD
    chosen: list[tuple[Path, float]] = []
    final_threshold = threshold

    # Raise threshold until <= MAX_FRAMES
    for _ in range(8):
        frames = extract_with_threshold(mp4, frames_dir, threshold)
        print(f"  threshold={threshold:.2f} -> {len(frames)} frames", file=sys.stderr)
        if len(frames) <= MAX_FRAMES:
            chosen = frames
            final_threshold = threshold
            break
        threshold = round(threshold + 0.1, 2)
    else:
        chosen = frames[:MAX_FRAMES]
        final_threshold = threshold

    # Lower threshold if too few
    if len(chosen) < MIN_FRAMES:
        for t in (0.20, 0.10, 0.05, 0.02):
            frames = extract_with_threshold(mp4, frames_dir, t)
            print(f"  lowered threshold={t:.2f} -> {len(frames)} frames", file=sys.stderr)
            if len(frames) >= MIN_FRAMES:
                chosen = frames[:MAX_FRAMES]
                final_threshold = t
                break

    # Last-resort uniform sampling
    if len(chosen) < MIN_FRAMES:
        print("  scene detection too sparse; falling back to uniform sampling", file=sys.stderr)
        chosen = extract_uniform(mp4, frames_dir, MIN_FRAMES, duration or 60.0)
        final_threshold = -1.0

    if not chosen:
        print("ERROR: could not extract any frames.", file=sys.stderr)
        return 2

    timestamps = {f.name: round(t, 3) for f, t in chosen}
    (frames_dir / "timestamps.json").write_text(json.dumps(timestamps, indent=2))
    print(json.dumps({
        "frame_count": len(chosen),
        "final_threshold": final_threshold,
        "duration_seconds": duration,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
