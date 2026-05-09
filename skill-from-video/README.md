# skill-from-video

A Claude Code skill that watches a YouTube video and generates a new skill from it.

The pipeline does the data prep (download, frame extraction, manifest building); **Claude Code itself** does the synthesis using its native vision on the extracted JPEG frames. There are no external vision API calls.

## Install

Copy or symlink this directory into the personal scope:

```bash
cp -r ./skill-from-video ~/.claude/skills/skill-from-video
# or:
ln -s "$PWD/skill-from-video" ~/.claude/skills/skill-from-video
```

Available across all projects once installed.

## Required tools

| Tool | Install | Purpose |
| --- | --- | --- |
| `yt-dlp` | `pip install yt-dlp` | Video + caption download |
| `ffmpeg` / `ffprobe` | `brew install ffmpeg` or `apt-get install ffmpeg` | Frame extraction, audio extraction |
| `faster-whisper` | `pip install faster-whisper` | Local STT fallback when no captions exist |
| `youtube-transcript-api` | `pip install youtube-transcript-api` | Secondary transcript fallback (optional but recommended) |

Verify with:

```bash
python3 ~/.claude/skills/skill-from-video/scripts/download.py --check
```

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `SKILL_FROM_VIDEO_CACHE_REPO` | unset | If set to a git URL or local clone path, processed videos (frames + transcript + manifest) are pushed there and looked up before reprocessing. Keyed by SHA-256 of the URL. |
| `SKILL_FROM_VIDEO_WHISPER_MODEL` | `base` | faster-whisper model name. Use `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger = slower + more accurate. |

## Pipeline

1. **download.py** — fetch mp4 + transcript. Tries yt-dlp auto-subs, then `youtube-transcript-api`, then local Whisper STT.
2. **extract_frames.py** — ffmpeg scene detection, adaptive threshold (cap 200 frames, floor 10).
3. **build_manifest.py** — pair each frame with the ±5s transcript window.
4. **Synthesis** — Claude reads the manifest, views each frame, then writes a new SKILL.md.
5. **cache.py** — optional GitHub push/pull of the data prep artifacts.

See `SKILL.md` for the orchestration instructions Claude follows.

## Limits and behavior

- Handles 30s to 3+ hour videos. Frame cap protects long ones.
- Aborts only when **both** transcript fallback AND scene detection produce nothing.
- Always strips ANSI codes from transcript output.
- Cache pushes are idempotent.
