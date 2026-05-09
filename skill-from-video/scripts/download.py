#!/usr/bin/env python3
"""Download a YouTube video + transcript to a working directory.

Transcript fallback ladder:
  1. yt-dlp auto-subs (vtt)
  2. youtube-transcript-api
  3. faster-whisper local STT (extracts audio with ffmpeg)

Usage:
    python3 download.py --check
    python3 download.py --url <URL> --workdir <dir>
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def check_environment() -> int:
    missing = []
    if not have("yt-dlp"):
        missing.append(("yt-dlp", "pip install yt-dlp   # or: brew install yt-dlp"))
    if not have("ffmpeg"):
        missing.append(("ffmpeg", "brew install ffmpeg   # or: apt-get install ffmpeg"))
    if missing:
        print("Missing required tools:", file=sys.stderr)
        for name, hint in missing:
            print(f"  - {name}: {hint}", file=sys.stderr)
        print(
            "\nOptional (auto-installed on first STT fallback):"
            "\n  - faster-whisper: pip install faster-whisper",
            file=sys.stderr,
        )
        return 1
    print("OK: yt-dlp and ffmpeg are installed.")
    return 0


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kw)


def download_video(url: str, workdir: Path) -> Path:
    out_tmpl = str(workdir / "video.%(ext)s")
    proc = run([
        "yt-dlp",
        "-f", "bv*[height<=720]+ba/b[height<=720]",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        url,
    ])
    if proc.returncode != 0:
        sys.stderr.write(strip_ansi(proc.stderr))
        raise SystemExit(f"yt-dlp failed to download {url}")
    mp4 = workdir / "video.mp4"
    if not mp4.exists():
        # yt-dlp may have produced a different ext; pick the largest video file
        candidates = sorted(workdir.glob("video.*"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise SystemExit("Download succeeded but no video file produced.")
        candidates[0].rename(mp4)
    return mp4


def try_yt_dlp_subs(url: str, workdir: Path) -> str | None:
    out_tmpl = str(workdir / "subs.%(ext)s")
    proc = run([
        "yt-dlp",
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs", "en.*,en",
        "--sub-format", "vtt",
        "-o", out_tmpl,
        url,
    ])
    if proc.returncode != 0:
        return None
    vtts = list(workdir.glob("subs*.vtt"))
    if not vtts:
        return None
    return parse_vtt(vtts[0].read_text(encoding="utf-8", errors="ignore"))


def parse_vtt(vtt: str) -> str:
    """Convert WebVTT to plain '[mm:ss] text' lines, deduplicated."""
    lines: list[str] = []
    last_text = ""
    timestamp = None
    for raw in vtt.splitlines():
        line = strip_ansi(raw).strip()
        if "-->" in line:
            ts = line.split("-->")[0].strip()
            timestamp = vtt_ts_to_seconds(ts)
            continue
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        # strip <c> / <00:00:00.000> inline tags
        text = re.sub(r"<[^>]+>", "", line).strip()
        if not text or text == last_text:
            continue
        if timestamp is None:
            continue
        m, s = divmod(int(timestamp), 60)
        lines.append(f"[{m:02d}:{s:02d}] {text}")
        last_text = text
    return "\n".join(lines)


def vtt_ts_to_seconds(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def try_youtube_transcript_api(url: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return None
    vid = extract_video_id(url)
    if not vid:
        return None
    try:
        entries = YouTubeTranscriptApi.get_transcript(vid)
    except Exception:
        return None
    out = []
    for e in entries:
        ts = int(e.get("start", 0))
        m, s = divmod(ts, 60)
        text = strip_ansi(e.get("text", "").strip())
        if text:
            out.append(f"[{m:02d}:{s:02d}] {text}")
    return "\n".join(out) if out else None


def extract_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url)
    return m.group(1) if m else None


def try_whisper_stt(mp4: Path, workdir: Path) -> str | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        print(
            "faster-whisper not installed. Install with: pip install faster-whisper",
            file=sys.stderr,
        )
        return None

    audio = workdir / "audio.wav"
    proc = run([
        "ffmpeg", "-y", "-i", str(mp4),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav", str(audio),
    ])
    if proc.returncode != 0 or not audio.exists():
        sys.stderr.write(strip_ansi(proc.stderr))
        return None

    model_name = os.environ.get("SKILL_FROM_VIDEO_WHISPER_MODEL", "base")
    print(f"Transcribing with faster-whisper ({model_name})...", file=sys.stderr)
    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments, _info = model.transcribe(str(audio), vad_filter=True)
    out = []
    for seg in segments:
        ts = int(seg.start)
        m, s = divmod(ts, 60)
        text = strip_ansi(seg.text.strip())
        if text:
            out.append(f"[{m:02d}:{s:02d}] {text}")
    try:
        audio.unlink()
    except OSError:
        pass
    return "\n".join(out) if out else None


def fetch_transcript(url: str, mp4: Path, workdir: Path) -> str:
    for label, fn in [
        ("yt-dlp auto-subs", lambda: try_yt_dlp_subs(url, workdir)),
        ("youtube-transcript-api", lambda: try_youtube_transcript_api(url)),
        ("faster-whisper STT", lambda: try_whisper_stt(mp4, workdir)),
    ]:
        print(f"Trying transcript source: {label}", file=sys.stderr)
        try:
            text = fn()
        except Exception as e:
            print(f"  {label} failed: {e}", file=sys.stderr)
            text = None
        if text:
            print(f"  Got transcript from {label} ({len(text)} chars).", file=sys.stderr)
            return text
    print("WARNING: all transcript sources failed; writing empty transcript.", file=sys.stderr)
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Verify dependencies and exit.")
    ap.add_argument("--url", help="YouTube URL.")
    ap.add_argument("--workdir", help="Working directory.")
    args = ap.parse_args()

    if args.check:
        return check_environment()

    if not args.url or not args.workdir:
        ap.error("--url and --workdir are required (or use --check).")

    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    if check_environment() != 0:
        return 1

    mp4 = download_video(args.url, workdir)
    transcript = fetch_transcript(args.url, mp4, workdir)
    (workdir / "transcript.txt").write_text(transcript, encoding="utf-8")
    print(f"video: {mp4}")
    print(f"transcript: {workdir / 'transcript.txt'} ({len(transcript)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
