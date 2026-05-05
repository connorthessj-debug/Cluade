"""Top strip showing macro regime + key FRED indicators."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual.reactive import reactive

from core.macro_monitor import classify_regime
from ui import theme


class MacroPanel(Static):
    """Always-visible macro regime banner with key indicators."""

    DEFAULT_CSS = ""

    regime: reactive[str] = reactive("UNKNOWN")
    indicators: reactive[dict] = reactive({})

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "macro-panel"

    def on_mount(self) -> None:
        self.render_content()

    def update_data(self, fred_data: dict) -> None:
        ri = fred_data.get("regime_indicators", {}) if fred_data else {}
        self.indicators = ri
        self.regime = classify_regime(ri)
        self.render_content()

    def render_content(self) -> None:
        ri = self.indicators or {}
        regime = self.regime or "UNKNOWN"
        regime_clr = theme.regime_color(regime)

        def fmt(val, suffix="", default="—"):
            if val is None:
                return default
            try:
                return f"{float(val):.2f}{suffix}"
            except (ValueError, TypeError):
                return str(val)

        spread = ri.get("yield_spread_10y2y_bps")
        cpi = ri.get("cpi_yoy_pct")
        hy = ri.get("hy_spread_bps")
        vix = ri.get("vix")
        fed_funds = ri.get("fed_funds_rate_pct")
        ten_yr = ri.get("ten_year_yield_pct")
        breakeven = ri.get("breakeven_inflation_pct")

        line1 = f"[{theme.ACCENT} b]MACRO REGIME[/{theme.ACCENT} b]   [{regime_clr} b]{regime:<14}[/{regime_clr} b]   "
        line1 += f"[{theme.TEXT_MUTED}]Growth:[/] [{theme.TEXT}]{ri.get('growth_signal', '—')}[/]   "
        line1 += f"[{theme.TEXT_MUTED}]Inflation:[/] [{theme.TEXT}]{ri.get('inflation_signal', '—')}[/]"

        line2 = (
            f"[{theme.TEXT_MUTED}]10Y[/] [{theme.TEXT}]{fmt(ten_yr, '%')}[/]  "
            f"[{theme.TEXT_MUTED}]10Y-2Y[/] [{theme.TEXT}]{fmt(spread, 'bps')}[/]  "
            f"[{theme.TEXT_MUTED}]CPI YoY[/] [{theme.TEXT}]{fmt(cpi, '%')}[/]  "
            f"[{theme.TEXT_MUTED}]5YBE[/] [{theme.TEXT}]{fmt(breakeven, '%')}[/]  "
            f"[{theme.TEXT_MUTED}]HY[/] [{theme.TEXT}]{fmt(hy, 'bps')}[/]  "
            f"[{theme.TEXT_MUTED}]VIX[/] [{theme.TEXT}]{fmt(vix)}[/]  "
            f"[{theme.TEXT_MUTED}]FedFunds[/] [{theme.TEXT}]{fmt(fed_funds, '%')}[/]"
        )

        self.update(f"{line1}\n{line2}")
