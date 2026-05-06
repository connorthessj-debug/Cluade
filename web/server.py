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
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
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

SCAN_TTL  = 900    # 15 min — market data changes slowly
MACRO_TTL = 3600   # 1 hour — FRED series update daily
NEWS_TTL  = 300    # 5 min — headlines turn over

_cache: dict[str, dict] = {}
_backtest_jobs: dict[str, dict] = {}   # job_id → {status, result, error}

def _cache_get(key: str) -> dict | None:
    entry = _cache.get(key)
    if entry and time.monotonic() < entry["exp"]:
        return entry["data"]
    return None

def _cache_set(key: str, data: dict, ttl: int) -> None:
    _cache[key] = {"data": data, "exp": time.monotonic() + ttl}

app = FastAPI(title="trading-ops mobile", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_prewarm_macro())
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


async def _prewarm_macro() -> None:
    """Fetch FRED macro data in the background at startup so first user request is fast."""
    if not os.environ.get("FRED_API_KEY"):
        return
    try:
        data = await _run_script("fetch_fred.py", timeout=45)
        if "error" not in data:
            _cache_set("macro", data, MACRO_TTL)
    except Exception:
        pass


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
    cached = _cache_get("macro")
    if cached:
        return cached
    data = await _run_script("fetch_fred.py", timeout=45)
    if "error" in data:
        return data
    regime_indicators = data.get("regime_indicators", {}) or {}
    derived = data.get("derived_regime", {}) or {}
    result = {
        "regime": derived.get("regime", "UNKNOWN"),
        "growth_signal": derived.get("growth_signal", "?"),
        "inflation_signal": derived.get("inflation_signal", "?"),
        "indicators": regime_indicators,
        "fetched_at": data.get("fetched_at"),
    }
    _cache_set("macro", result, MACRO_TTL)
    return result


@app.get("/api/news")
async def api_news(query: str = "markets", _user: str = Depends(auth_required)) -> dict:
    cache_key = f"news:{query}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    data = await _run_script("fetch_news.py", query, timeout=30)
    if "error" not in data:
        _cache_set(cache_key, data, NEWS_TTL)
    return data


@app.post("/api/scan")
async def api_scan(payload: dict, _user: str = Depends(auth_required)) -> dict:
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")

    force_refresh = bool(payload.get("refresh"))
    cache_key = f"scan:{symbol}"

    if not force_refresh:
        cached = _cache_get(cache_key)
        if cached:
            return {**cached, "_cached": True}

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
    _cache_set(cache_key, data, SCAN_TTL)
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


# ── backtest ──────────────────────────────────────────────────────────────────

VALID_BT_INTERVALS  = {"1d", "1h", "15m", "5m", "1m"}
VALID_BT_STRATEGIES = {"sma_rsi", "breakout", "mean_reversion"}


def _wfa_worker(symbol: str, n_trials: int, train_days: int, test_days: int,
                step_days: int, allow_short: bool,
                interval: str = "1d", strategy: str = "sma_rsi") -> dict:
    """Runs in a separate process so it doesn't block the event loop."""
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.wfa_optimizer import run_wfa
    return run_wfa(symbol, n_trials=n_trials, train_days=train_days,
                   test_days=test_days, step_days=step_days, allow_short=allow_short,
                   interval=interval, strategy=strategy)


async def _run_backtest_job(job_id: str, symbol: str, n_trials: int,
                            train_days: int, test_days: int, step_days: int,
                            allow_short: bool,
                            interval: str = "1d", strategy: str = "sma_rsi") -> None:
    _backtest_jobs[job_id]["status"] = "running"
    try:
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(
                pool, _wfa_worker,
                symbol, n_trials, train_days, test_days, step_days, allow_short,
                interval, strategy,
            )
        _backtest_jobs[job_id]["status"] = "done"
        _backtest_jobs[job_id]["result"] = result
    except Exception as e:
        _backtest_jobs[job_id]["status"] = "error"
        _backtest_jobs[job_id]["error"] = str(e)


@app.post("/api/backtest")
async def api_backtest_start(payload: dict, _user: str = Depends(auth_required)) -> dict:
    """Start a WFA backtest job. Returns job_id to poll."""
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    if asset_class_mod.detect(symbol) not in ("equity", "index", "crypto"):
        raise HTTPException(status_code=400, detail="backtest supports equity/index/crypto only")

    n_trials   = min(int(payload.get("n_trials",   40)), 100)
    train_days = min(int(payload.get("train_days", 252)), 504)
    test_days  = min(int(payload.get("test_days",   63)), 126)
    step_days  = min(int(payload.get("step_days",   21)),  63)
    allow_short = bool(payload.get("allow_short", True))

    interval = str(payload.get("interval", "1d"))
    if interval not in VALID_BT_INTERVALS:
        interval = "1d"

    strategy = str(payload.get("strategy", "sma_rsi"))
    if strategy not in VALID_BT_STRATEGIES:
        strategy = "sma_rsi"

    job_id = str(uuid.uuid4())[:8]
    _backtest_jobs[job_id] = {
        "status": "queued", "symbol": symbol,
        "interval": interval, "strategy": strategy,
        "result": None, "error": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    asyncio.create_task(_run_backtest_job(
        job_id, symbol, n_trials, train_days, test_days, step_days, allow_short,
        interval, strategy,
    ))

    est_windows = len(range(0, 1260 - train_days - test_days, step_days))
    return {"job_id": job_id, "symbol": symbol, "status": "queued",
            "message": f"WFA started: {n_trials} trials × ~{est_windows} windows ({interval} {strategy})"}


@app.get("/api/backtest/{job_id}")
async def api_backtest_status(job_id: str, _user: str = Depends(auth_required)) -> dict:
    job = _backtest_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "symbol": job.get("symbol"),
        "started_at": job.get("started_at"),
        "result": job.get("result"),
        "error": job.get("error"),
    }


# ── siri / iOS Shortcuts endpoints ───────────────────────────────────────────
# These return plain text so Siri can speak the result and Shortcuts
# can display it in a notification or alert without any JSON parsing.

def _siri_conviction_summary(data: dict) -> str:
    symbol     = data.get("symbol", "?")
    ac         = data.get("asset_class", "")
    conviction = data.get("conviction", "?")
    total      = data.get("total_score", 0)
    signals    = data.get("signals", {}) or {}
    metrics    = data.get("key_metrics", {}) or {}
    price      = metrics.get("price") or metrics.get("price_usd")

    bull = [k for k, v in signals.items() if isinstance(v, str) and "BULL" in v.upper()]
    bear = [k for k, v in signals.items() if isinstance(v, str) and "BEAR" in v.upper()]

    lines = [
        f"{symbol} ({ac}) — {conviction}",
        f"Score: {'+' if total > 0 else ''}{total}",
    ]
    if price:
        lines.append(f"Price: {float(price):.2f}")
    if bull:
        lines.append(f"Bullish: {', '.join(bull)}")
    if bear:
        lines.append(f"Bearish: {', '.join(bear)}")
    return "\n".join(lines)


@app.get("/api/siri/scan/{symbol}", response_class=Response)
async def siri_scan(symbol: str, _user: str = Depends(auth_required)) -> Response:
    """Plain-text scan for iOS Shortcuts / Siri. Cached same as /api/scan."""
    symbol = symbol.strip().upper()
    ac = "macro" if symbol == "MACRO" else asset_class_mod.detect(symbol)

    cache_key = f"scan:{symbol}"
    data = _cache_get(cache_key)
    if not data:
        try:
            data = await run_scan(symbol, ac)
        except Exception as e:
            return Response(f"{symbol}: scan failed — {e}", media_type="text/plain")
        if not data.get("error"):
            data["symbol"] = symbol
            data["asset_class"] = ac
            _cache_set(cache_key, data, SCAN_TTL)

    if data.get("error"):
        return Response(f"{symbol}: {data['error']}", media_type="text/plain")
    return Response(_siri_conviction_summary(data), media_type="text/plain")


@app.get("/api/siri/macro", response_class=Response)
async def siri_macro(_user: str = Depends(auth_required)) -> Response:
    """Plain-text macro regime for iOS Shortcuts / Siri."""
    if not os.environ.get("FRED_API_KEY"):
        return Response("Macro: FRED API key not configured.", media_type="text/plain")
    cached = _cache_get("macro")
    if not cached:
        data = await _run_script("fetch_fred.py", timeout=45)
        if "error" in data:
            return Response(f"Macro error: {data['error']}", media_type="text/plain")
        derived = data.get("derived_regime", {}) or {}
        ind     = data.get("regime_indicators", {}) or {}
        cached = {
            "regime": derived.get("regime", "UNKNOWN"),
            "growth_signal": derived.get("growth_signal", "?"),
            "inflation_signal": derived.get("inflation_signal", "?"),
            "indicators": ind,
        }
        _cache_set("macro", cached, MACRO_TTL)

    ind = cached.get("indicators", {})
    lines = [
        f"Macro Regime: {cached.get('regime', '?')}",
        f"Growth: {cached.get('growth_signal', '?')}  |  Inflation: {cached.get('inflation_signal', '?')}",
    ]
    for label, key in [("10Y-2Y Spread", "yield_spread_10y_2y"), ("VIX", "vix"), ("CPI YoY", "cpi_yoy")]:
        v = ind.get(key)
        if v is not None:
            lines.append(f"{label}: {float(v):.2f}%")
    return Response("\n".join(lines), media_type="text/plain")


@app.get("/api/siri/watchlist", response_class=Response)
async def siri_watchlist(_user: str = Depends(auth_required)) -> Response:
    """Speak a summary of the most recent scan for each symbol in history."""
    scans = list_scans(SCANNED_DIR)[:8]
    if not scans:
        return Response("No saved scans yet.", media_type="text/plain")
    lines = []
    for s in scans:
        sym  = s.get("symbol", "?")
        conv = s.get("conviction", "?")
        date = s.get("date", "")
        lines.append(f"{sym}: {conv} ({date})")
    return Response("\n".join(lines), media_type="text/plain")
