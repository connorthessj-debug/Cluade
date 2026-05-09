---
name: skill-from-video
description: Generate a new Claude Code skill by watching a YouTube video. Use this skill whenever the user asks to "generate a skill from this video", "make a skill from [YouTube URL]", "create a skill from this tutorial", "turn this video into a skill", "build a skill from [video link]", "extract a skill from [URL]", "learn this skill from a video", "watch this YouTube video and make a skill", or supplies any YouTube/youtu.be URL alongside the words skill, tutorial, walkthrough, demo, workflow, or how-to. Fires on requests to convert recorded screen-shares, conference talks, dev streams, or product demos into reusable Claude skills. Trigger aggressively whenever a YouTube link appears with intent to capture, codify, replicate, or document the workflow shown.
---

# skill-from-video

Convert a YouTube video into a new Claude Code skill installed at `~/.claude/skills/<derived-name>/`.

You (Claude) do the synthesis step using your native vision on extracted frames — scripts handle data prep only. There are no external vision API calls.

## When to use

Fire on any of these (and similar) phrases:
- "generate a skill from this video"
- "make a skill from <YouTube URL>"
- "create a skill from this tutorial"
- "turn this video into a skill"
- "watch this and make a skill"
- "build a skill from <link>"
- Any YouTube/youtu.be URL paired with words like *skill, tutorial, walkthrough, demo, workflow, how-to, codify, replicate*.

If the request is ambiguous (e.g. user shares a video but doesn't say "skill"), ask once whether they want a skill generated.

## Pipeline

The pipeline lives in `scripts/` next to this file. Run the steps **in order** from this skill's directory.

### Step 0 — Preflight

```bash
python3 scripts/download.py --check
```

This verifies `yt-dlp` and `ffmpeg` are installed. If anything is missing, print the install instructions it reports and **stop**. Do not proceed with a partial pipeline.

### Step 1 — Cache lookup (skip pipeline on hit)

```bash
python3 scripts/cache.py --lookup "<URL>" --workdir <workdir>
```

If `SKILL_FROM_VIDEO_CACHE_REPO` is set and the URL is cached, this populates `<workdir>` with `manifest.json`, `frames/`, and `transcript.txt`. Skip to Step 5.

If no cache hit (or env var unset), continue to Step 2.

### Step 2 — Download

```bash
python3 scripts/download.py --url "<URL>" --workdir <workdir>
```

Outputs:
- `<workdir>/video.mp4`
- `<workdir>/audio.wav` (extracted; deleted after transcription)
- `<workdir>/transcript.txt` (timestamped, ANSI stripped)

Transcript fallback ladder (each tier runs only if the previous one fails):

1. **yt-dlp auto-subs** — fastest, free, uses YouTube's caption track.
2. **`youtube-transcript-api`** — pip fallback for the same caption track.
3. **`faster-whisper` (local STT)** — extracts audio with ffmpeg and transcribes locally. No API key required. Default model: `base` (override with `SKILL_FROM_VIDEO_WHISPER_MODEL`, e.g. `small`, `medium`, `large-v3`).

If all three fail, the script writes an empty transcript and prints a warning — Step 3 will still abort if there are also no detectable scene changes.

### Step 3 — Extract scene-change frames

```bash
python3 scripts/extract_frames.py --workdir <workdir>
```

Uses `ffmpeg` with `select='gt(scene,T)'`, starting at `T=0.30`. Iteratively raises `T` until ≤ 200 frames; lowers it until ≥ 10 frames on short clips. Saves `frames/0001.jpg`, `frames/0002.jpg`, ... and a `frames/timestamps.json` sidecar mapping frame → seconds.

If extraction yields zero frames AND transcript is empty, **abort with a clear error** — the video has nothing to learn from.

### Step 4 — Build manifest

```bash
python3 scripts/build_manifest.py --workdir <workdir>
```

Produces `<workdir>/manifest.json` — a list of objects:

```json
{ "frame_path": "frames/0001.jpg", "timestamp": 12.4, "transcript_window": "..." }
```

`transcript_window` is the transcript text within ±5 seconds of `timestamp`.

### Step 5 — Synthesize (you do this, not a script)

1. Read `<workdir>/manifest.json`.
2. For each entry, use the **Read** tool on `frame_path` to view the frame, then read its `transcript_window`.
3. Build a mental model of:
   - The overall task being demonstrated
   - Tech stack, tools, and libraries on screen
   - Ordered workflow steps
   - Commands shown verbatim (copy them exactly — including flags)
   - File paths, configs, URLs visible
4. Pick a kebab-case `<derived-name>` for the new skill (short, descriptive of the task).

### Step 6 — Generate the new skill

Create `~/.claude/skills/<derived-name>/SKILL.md` with:

- **YAML frontmatter** — `name` and a *pushy* `description` listing concrete trigger phrases for the new skill (mirror this skill's aggressive style).
- **Body** documenting the workflow with commands and code copied verbatim from the video. Include a "When to use" section and a step-by-step "Workflow" section.

Use the Write tool. Do not invent commands the video didn't show; if something was implied but not visible, mark it `# inferred` in a comment.

### Step 7 — Cache (optional)

```bash
python3 scripts/cache.py --push "<URL>" --workdir <workdir>
```

Idempotent. Pushes `manifest.json`, `frames/`, and `transcript.txt` to `$SKILL_FROM_VIDEO_CACHE_REPO` keyed by URL hash. No-op if the env var isn't set.

## Reporting

After generating the skill, report to the user:
- Path to the generated SKILL.md
- Frame count and final scene threshold used
- Approximate token cost (sum of frame Read calls + manifest read)
- One-line summary of the workflow you captured

## Quality bar

- **Verbatim commands**: copy from on-screen terminals exactly — preserve flags, quotes, paths.
- **Always produce a transcript**: if YouTube captions are unavailable, fall back to local Whisper STT (faster-whisper). Only abort on a video that has *both* no transcript path AND no detectable scene changes.
- **Don't reprocess cached URLs**: always check cache first when the env var is set.
- **Strip ANSI**: scripts already strip ANSI escape codes from transcripts; do not re-introduce them.
- **Pushy descriptions**: the generated skill's `description` must list specific trigger phrases — Claude tends to undertrigger skills, so be aggressive.

## Working directory convention

Use `mktemp -d` for `<workdir>` unless the user supplies one. Don't pollute the project directory with frames/transcript artifacts.
