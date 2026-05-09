#!/usr/bin/env python3
"""Optional GitHub-backed cache for processed videos.

Cache layout in $SKILL_FROM_VIDEO_CACHE_REPO (a local clone or HTTPS URL):
    <url_hash>/manifest.json
    <url_hash>/transcript.txt
    <url_hash>/frames/0001.jpg ...
    <url_hash>/url.txt

Modes:
  --lookup <URL> --workdir <dir>   Populate <dir> from cache if hit. Exit 0
                                   on hit, 10 on miss.
  --push   <URL> --workdir <dir>   Push <dir> contents to cache.
                                   Idempotent; no-op if env var unset.

Auth: relies on the user's existing git credentials (SSH or HTTPS token).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_VAR = "SKILL_FROM_VIDEO_CACHE_REPO"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()[:16]


def repo_url() -> str | None:
    return os.environ.get(ENV_VAR)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=cwd)


def clone_or_pull(remote: str) -> Path:
    """Clone the cache repo into a temp dir (or reuse local path)."""
    if remote.startswith(("/", "~")) or Path(remote).expanduser().exists():
        local = Path(remote).expanduser().resolve()
        if (local / ".git").exists():
            run(["git", "pull", "--ff-only"], cwd=local)
            return local
    tmp = Path(tempfile.mkdtemp(prefix="skill-from-video-cache-"))
    proc = run(["git", "clone", "--depth", "1", remote, str(tmp)])
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"Failed to clone cache repo: {remote}")
    return tmp


def lookup(url: str, workdir: Path) -> int:
    remote = repo_url()
    if not remote:
        return 10
    try:
        repo = clone_or_pull(remote)
    except SystemExit:
        return 10
    src = repo / url_hash(url)
    if not (src / "manifest.json").exists():
        return 10
    workdir.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        dst = workdir / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    print(f"cache HIT for {url} -> {workdir}")
    return 0


def push(url: str, workdir: Path) -> int:
    remote = repo_url()
    if not remote:
        print(f"{ENV_VAR} unset; skipping cache push.")
        return 0
    if not (workdir / "manifest.json").exists():
        print("Nothing to push (manifest.json missing).", file=sys.stderr)
        return 1
    try:
        repo = clone_or_pull(remote)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1
    dst = repo / url_hash(url)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "url.txt").write_text(url + "\n")
    for name in ("manifest.json", "transcript.txt"):
        src = workdir / name
        if src.exists():
            shutil.copy2(src, dst / name)
    src_frames = workdir / "frames"
    if src_frames.exists():
        dst_frames = dst / "frames"
        if dst_frames.exists():
            shutil.rmtree(dst_frames)
        shutil.copytree(src_frames, dst_frames)
    run(["git", "add", url_hash(url)], cwd=repo)
    status = run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if not status:
        print("Cache already up to date; nothing to commit.")
        return 0
    run(["git", "commit", "-m", f"cache: {url_hash(url)}"], cwd=repo)
    proc = run(["git", "push"], cwd=repo)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return 1
    print(f"cache PUSH for {url} -> {dst}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--lookup", metavar="URL")
    g.add_argument("--push", metavar="URL")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()
    workdir = Path(args.workdir).expanduser().resolve()
    if args.lookup:
        return lookup(args.lookup, workdir)
    return push(args.push, workdir)


if __name__ == "__main__":
    sys.exit(main())
