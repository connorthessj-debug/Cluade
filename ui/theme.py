"""Bloomberg Terminal palette + helper functions for color-coded rendering."""

# Base palette
BG_DEEP = "#0a0f1e"
BG_PANEL = "#0d1526"
BG_HOVER = "#162040"
BORDER = "#1e3a5f"
ACCENT = "#f59e0b"
GREEN = "#22c55e"
RED = "#ef4444"
DIM = "#4b5563"
TEXT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
AMBER = "#fbbf24"
BLUE = "#3b82f6"

# Regime colors
REGIME_COLORS = {
    "GOLDILOCKS": GREEN,
    "REFLATION": ACCENT,
    "STAGFLATION": RED,
    "RISK-OFF": BLUE,
    "TRANSITIONING": AMBER,
    "UNKNOWN": DIM,
}


def signal_color(signal: str) -> str:
    """Return hex color for a BULL/BEAR/NEUTRAL signal label."""
    s = (signal or "").upper()
    if "BULL" in s:
        return GREEN
    if "BEAR" in s:
        return RED
    if "INSUFFICIENT" in s or "UNKNOWN" in s:
        return DIM
    return AMBER


def score_color(score) -> str:
    """Return hex color for a numeric score."""
    try:
        n = int(score)
    except (ValueError, TypeError):
        return DIM
    if n > 0:
        return GREEN
    if n < 0:
        return RED
    return AMBER


def conviction_color(conviction: str) -> str:
    """Return hex color for a conviction label."""
    c = (conviction or "").upper()
    if "HIGH LONG" in c:
        return GREEN
    if "MOD" in c and "LONG" in c:
        return GREEN
    if "MILD LONG" in c:
        return GREEN
    if "HIGH SHORT" in c:
        return RED
    if "MOD" in c and "SHORT" in c:
        return RED
    if "MILD SHORT" in c:
        return RED
    if "NO TRADE" in c or "NEUTRAL" in c:
        return AMBER
    return DIM


def regime_color(regime: str) -> str:
    return REGIME_COLORS.get((regime or "UNKNOWN").upper(), DIM)


def color_text(text: str, color: str) -> str:
    """Wrap text in Rich markup with a hex color."""
    if not text:
        return ""
    return f"[{color}]{text}[/{color}]"


def bold(text: str) -> str:
    return f"[b]{text}[/b]"
