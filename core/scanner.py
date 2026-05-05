"""Async wrapper around compute_signals.py — non-blocking scan execution."""

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCANNED_DIR = REPO_ROOT / "scanned"

SCAN_TIMEOUT_SECONDS = 180


async def run_scan(symbol: str, asset_class: str) -> dict:
    """Run compute_signals.py as a subprocess. Returns parsed JSON or error dict."""
    script_path = SCRIPTS_DIR / "compute_signals.py"
    if not script_path.exists():
        return {"error": f"compute_signals.py not found at {script_path}"}

    env = os.environ.copy()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            symbol,
            asset_class,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=SCAN_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"error": f"Scan timed out after {SCAN_TIMEOUT_SECONDS}s"}

        if proc.returncode != 0 and not stdout.strip():
            return {
                "error": f"compute_signals.py exited {proc.returncode}",
                "stderr": stderr.decode("utf-8", errors="replace")[:500],
            }

        try:
            return json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}", "raw": stdout[:500].decode("utf-8", errors="replace")}

    except Exception as e:
        return {"error": str(e)}


async def run_macro_scan() -> dict:
    """Run a macro-only scan (just FRED data + regime classification)."""
    return await run_scan("MACRO", "macro")


async def run_fetch_script(script_name: str, *args) -> dict:
    """Run a single fetch_*.py script directly. For background polling."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"{script_name} not found"}

    env = os.environ.copy()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        return json.loads(stdout.decode("utf-8", errors="replace"))
    except asyncio.TimeoutError:
        return {"error": f"{script_name} timed out"}
    except json.JSONDecodeError:
        return {"error": f"{script_name} returned invalid JSON"}
    except Exception as e:
        return {"error": str(e)}


def save_scan_markdown(symbol: str, markdown: str) -> Path:
    """Write a verdict markdown file to scanned/. Returns path."""
    import datetime
    SCANNED_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"{date_str}_{symbol.upper()}.md"
    path = SCANNED_DIR / filename
    counter = 2
    while path.exists():
        path = SCANNED_DIR / f"{date_str}_{symbol.upper()}_{counter}.md"
        counter += 1
    path.write_text(markdown, encoding="utf-8")
    return path
