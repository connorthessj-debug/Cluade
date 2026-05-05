"""FastAPI mobile web server for trading-ops.

Wraps the existing scripts (compute_signals.py, fetch_fred.py, fetch_news.py)
and exposes a mobile-friendly UI accessible from anywhere via cloud deploy.

Run locally:
    python3 -m uvicorn web.server:app --host 0.0.0.0 --port 8000

Cloud deploy: see render.yaml / Dockerfile.

Auth: HTTP Basic. Set ACCESS_PASSWORD env var. If unset, auth is disabled
(only do this on a private network).
"""

import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import asset_class as asset_class_mod
from core.scanner import run_scan, save_scan_markdown
from core.scan_parser import list_scans, parse_scan_file

WEB_DIR = Path(__file__).resolve().parent
SCANNED_DIR = REPO_ROOT / "scanned"
SCRIPTS_DIR = REPO_ROOT / "scripts"

app = FastAPI(title="trading-ops mobile", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

security = HTTPBasic(auto_error=False)


def auth_required(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    """HTTP Basic auth gate. Skipped if ACCESS_PASSWORD env var is unset."""
    expected = os.environ.get("ACCESS_PASSWORD", "")
    if not expected:
        return "anonymous"
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    expected_user = os.environ.get("ACCESS_USER", "trader")
    user_ok = secrets.compare_digest(credentials.username.encode(), expected_user.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), expected.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def _run_script(script: str, *args: str, timeout: float = 60.0) -> dict:
    """Run a script via subprocess and parse stdout JSON."""
    env = os.environ.copy()
    cmd = [sys.executable, str(SCRIPTS_DIR / script), *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": f"{script} timed out after {timeout}s"}

    if proc.returncode != 0 and not stdout.strip():
        return {"error": f"{script} exited {proc.returncode}: {stderr.decode()[:400]}"}
    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        return {"error": f"bad JSON from {script}: {e}"}


def _render_markdown(symbol: str, asset_class: str, data: dict) -> str:
    """Render compute_signals.py output as a verdict markdown file."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    signals = data.get("signals", {}) or {}
    scores = data.get("scores", {}) or {}
    total = data.get("total_score", 0)
    conviction = data.get("conviction", "UNKNOWN")
    metrics = data.get("key_metrics", {}) or {}

    lines = [
        f"# SCAN: {symbol} — {now}",
        f"**Asset Class:** {asset_class}",
        "",
        "## Signals",
        "| Dimension | Score | Signal | Rationale |",
        "|-----------|-------|--------|-----------|",
    ]
    for dim, sig in signals.items():
        score = scores.get(dim, 0)
        score_str = f"+{score}" if isinstance(score, (int, float)) and score > 0 else str(score)
        lines.append(f"| {dim} | {score_str} | {sig} | — |")
    lines.append(f"| **COMPOSITE** | **{total}** | **{conviction}** | mobile scan |")
    lines.append("")

    vp = metrics.get("volume_profile") or {}
    if vp:
        lines.append("## Price Ladder")
        lines.append("```")
        cur = metrics.get("current_price")
        for label, val in [
            ("52W High", metrics.get("week52_high")),
            ("VAH", vp.get("vah")),
            ("POC", vp.get("poc")),
            ("VAL", vp.get("val")),
            ("52W Low", metrics.get("week52_low")),
        ]:
            if val is not None:
                lines.append(f"  {label:>10}  {val}")
        if cur is not None:
            lines.append(f"  CURRENT: {cur}")
        lines.append("```")
        lines.append("")

    lines.append("## Trade Structure")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Conviction | {conviction} |")
    lines.append(f"| Composite Score | {total} |")
    if metrics.get("current_price") is not None:
        lines.append(f"| Current Price | {metrics['current_price']} |")
    lines.append("")

    lines.append("## Self-Improvement Audit")
    lines.append("### Issues Found")
    lines.append("- No issues found this scan (mobile auto-scan).")
    lines.append("")
    lines.append("### Proposed Improvements")
    lines.append("- No improvements proposed.")
    lines.append("")
    lines.append("**AWAITING USER CONSENT before editing any guide/ or docs/ files.**")
    return "\n".join(lines)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _user: str = Depends(auth_required)) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/manifest.json")
async def manifest() -> JSONResponse:
    return JSONResponse({
        "name": "trading-ops",
        "short_name": "trading-ops",
        "description": "AI Bloomberg Terminal — mobile",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0f1e",
        "theme_color": "#f59e0b",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "fred_key_set": bool(os.environ.get("FRED_API_KEY")),
        "auth_enabled": bool(os.environ.get("ACCESS_PASSWORD")),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/macro")
async def api_macro(_user: str = Depends(auth_required)) -> dict:
    if not os.environ.get("FRED_API_KEY"):
        return {"error": "FRED_API_KEY not set on server", "regime": "UNKNOWN"}
    data = await _run_script("fetch_fred.py", timeout=45)
    if "error" in data:
        return data
    regime_indicators = data.get("regime_indicators", {}) or {}
    derived = data.get("derived_regime", {}) or {}
    return {
        "regime": derived.get("regime", "UNKNOWN"),
        "growth_signal": derived.get("growth_signal", "?"),
        "inflation_signal": derived.get("inflation_signal", "?"),
        "indicators": regime_indicators,
        "fetched_at": data.get("fetched_at"),
    }


@app.get("/api/news")
async def api_news(query: str = "markets", _user: str = Depends(auth_required)) -> dict:
    data = await _run_script("fetch_news.py", query, timeout=30)
    return data


@app.post("/api/scan")
async def api_scan(payload: dict, _user: str = Depends(auth_required)) -> dict:
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")

    if symbol == "MACRO":
        ac = "macro"
    else:
        ac = asset_class_mod.detect(symbol)

    try:
        data = await run_scan(symbol, ac)
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "asset_class": ac}

    if data.get("error"):
        return {"error": data["error"], "symbol": symbol, "asset_class": ac}

    try:
        markdown = _render_markdown(symbol, ac, data)
        save_path = save_scan_markdown(symbol, markdown)
        data["_saved_filename"] = save_path.name
    except Exception:
        pass

    data["symbol"] = symbol
    data["asset_class"] = ac
    return data


@app.get("/api/history")
async def api_history(_user: str = Depends(auth_required)) -> dict:
    items = []
    scans = list_scans(SCANNED_DIR)
    for scan in scans[:50]:
        items.append({
            "filename": scan.get("filename", ""),
            "symbol": scan.get("symbol", "?"),
            "date": scan.get("date", "") or "",
            "asset_class": scan.get("asset_class", "?"),
            "conviction": scan.get("conviction", "?"),
        })
    return {"scans": items}


@app.get("/api/history/{filename}")
async def api_history_detail(filename: str, _user: str = Depends(auth_required)) -> dict:
    safe = Path(filename).name
    path = SCANNED_DIR / safe
    if not path.exists() or path.suffix != ".md":
        raise HTTPException(status_code=404, detail="not found")
    parsed = parse_scan_file(path)
    return {
        "filename": safe,
        "markdown": parsed.get("raw", ""),
        "signals": parsed.get("signals", []),
        "price_ladder": parsed.get("price_ladder", ""),
        "trade": parsed.get("trade", {}),
        "conviction": parsed.get("conviction", "?"),
        "asset_class": parsed.get("asset_class", "?"),
        "audit": parsed.get("audit", {}),
    }
