"""Parse scanned/*.md files back into structured dicts for the UI."""

import re
from pathlib import Path
from datetime import datetime

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([A-Z0-9]+)(?:_\d+)?\.md$")


def parse_filename(filename: str) -> dict:
    """Extract date and symbol from a scan filename."""
    m = FILENAME_RE.match(filename)
    if not m:
        return {"date": None, "symbol": filename.replace(".md", "")}
    return {"date": m.group(1), "symbol": m.group(2)}


def list_scans(scanned_dir: Path) -> list[dict]:
    """List all scan files in scanned/, newest first."""
    if not scanned_dir.exists():
        return []
    scans = []
    for path in scanned_dir.glob("*.md"):
        if path.name.startswith("."):
            continue
        meta = parse_filename(path.name)
        meta["path"] = str(path)
        meta["filename"] = path.name
        try:
            meta["preview"] = path.read_text(encoding="utf-8")[:2000]
            meta["conviction"] = extract_conviction(meta["preview"])
            meta["asset_class"] = extract_asset_class(meta["preview"])
        except Exception:
            meta["preview"] = ""
            meta["conviction"] = "?"
            meta["asset_class"] = "?"
        scans.append(meta)
    scans.sort(key=lambda x: (x.get("date") or "", x.get("filename") or ""), reverse=True)
    return scans


def extract_conviction(text: str) -> str:
    """Pull the conviction label from a verdict's signals table."""
    m = re.search(r"\*\*COMPOSITE\*\*\s*\|\s*\*\*([^*|]+)\*\*\s*\|\s*\*\*([^*|]+)\*\*", text)
    if m:
        return m.group(2).strip()
    m = re.search(r"Conviction[:\s|]+([A-Z\s\-—]+)", text)
    if m:
        return m.group(1).strip().split("\n")[0][:30]
    return "?"


def extract_asset_class(text: str) -> str:
    m = re.search(r"\*\*Asset Class:\*\*\s*([a-zA-Z]+)", text)
    if m:
        return m.group(1).strip().lower()
    return "?"


def extract_audit_block(text: str) -> dict:
    """Pull issues + proposed fixes from the self-improvement audit section."""
    issues = []
    proposals = []

    issues_section = re.search(
        r"###\s*Issues Found\s*\n(.+?)(?=###|\Z)", text, re.S
    )
    if issues_section:
        for line in issues_section.group(1).splitlines():
            line = line.strip()
            if line.startswith("- [ ]") or line.startswith("- [x]"):
                cleaned = re.sub(r"^- \[[ x]\]\s*", "", line).strip()
                if cleaned and "no issues" not in cleaned.lower():
                    issues.append(cleaned)

    proposals_section = re.search(
        r"###\s*Proposed.*?Improvements?\s*\n(.+?)(?=###|---|\*\*AWAITING|\Z)",
        text,
        re.S | re.I,
    )
    if proposals_section:
        for line in proposals_section.group(1).splitlines():
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                cleaned = line.lstrip("-* ").strip()
                if cleaned and "no improvements" not in cleaned.lower():
                    proposals.append(cleaned)

    return {"issues": issues, "proposals": proposals}


def extract_signals_table(text: str) -> list[dict]:
    """Parse the signals table rows: dimension, score, signal, rationale."""
    rows = []
    section = re.search(r"##\s*Signals\s*\n(.+?)(?=##|\Z)", text, re.S)
    if not section:
        return rows
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "Dimension" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 3 and "COMPOSITE" not in parts[0].upper():
            rows.append({
                "dimension": parts[0],
                "score": parts[1] if len(parts) > 1 else "",
                "signal": parts[2] if len(parts) > 2 else "",
                "rationale": parts[3] if len(parts) > 3 else "",
            })
    return rows


def extract_price_ladder(text: str) -> str:
    """Pull the ASCII price ladder code block."""
    m = re.search(r"##\s*Price Ladder\s*\n+```\n(.+?)\n```", text, re.S)
    if m:
        return m.group(1)
    return ""


def extract_trade_table(text: str) -> dict:
    """Pull the trade structure key/value pairs."""
    out = {}
    section = re.search(r"##\s*Trade Structure\s*\n(.+?)(?=##|\Z)", text, re.S)
    if not section:
        section = re.search(r"##\s*Trade Table\s*\n(.+?)(?=##|\Z)", text, re.S)
    if not section:
        return out
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "Field" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def parse_scan_file(path: Path) -> dict:
    """Parse a complete scan file into a structured dict."""
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "filename": path.name,
        "raw": text,
        "meta": parse_filename(path.name),
        "asset_class": extract_asset_class(text),
        "conviction": extract_conviction(text),
        "signals": extract_signals_table(text),
        "price_ladder": extract_price_ladder(text),
        "trade": extract_trade_table(text),
        "audit": extract_audit_block(text),
    }
