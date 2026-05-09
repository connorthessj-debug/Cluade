#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Installs the system + Python dependencies the skill-from-video skill needs,
# then symlinks the in-repo skill into ~/.claude/skills/ so it's discoverable.
#
# Idempotent: each step is a no-op if already done.

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

# 1. ffmpeg + ffprobe (apt provides both via the ffmpeg package)
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "Installing ffmpeg via apt..." >&2
  $SUDO apt-get update -qq
  $SUDO apt-get install -y --no-install-recommends ffmpeg
fi

# 2. Python deps (yt-dlp + transcript fallbacks + Whisper STT)
PIP="python3 -m pip"
echo "Installing/updating Python dependencies..." >&2
$PIP install --quiet --upgrade --disable-pip-version-check \
  yt-dlp youtube-transcript-api faster-whisper

# 3. Make the in-repo skill discoverable at user scope
SKILL_SRC="${CLAUDE_PROJECT_DIR:-$PWD}/skill-from-video"
SKILL_DST="$HOME/.claude/skills/skill-from-video"
if [ -d "$SKILL_SRC" ]; then
  mkdir -p "$HOME/.claude/skills"
  if [ -L "$SKILL_DST" ] || [ -e "$SKILL_DST" ]; then
    rm -rf "$SKILL_DST"
  fi
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "Linked $SKILL_DST -> $SKILL_SRC" >&2
fi

echo "skill-from-video session bootstrap complete." >&2
