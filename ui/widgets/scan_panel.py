"""Center panel — current scan verdict: signals, price ladder, trade table."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, DataTable, LoadingIndicator

from ui import theme


HEADER_HINT = (
    f"[{theme.ACCENT} b]▎ SCAN PANEL[/]   "
    f"[{theme.TEXT_MUTED}]Type a symbol below and press ENTER[/]"
)

WELCOME_BODY = (
    f"\n[{theme.TEXT_MUTED}]Examples:[/]\n"
    f"  [{theme.ACCENT}]AAPL[/]      equity scan (6-pillar fundamentals + volume profile)\n"
    f"  [{theme.ACCENT}]BTCUSDT[/]   crypto scan (F&G + funding + OI)\n"
    f"  [{theme.ACCENT}]SPX[/]       index scan (gamma + VIX + breadth)\n"
    f"  [{theme.ACCENT}]EURUSD[/]    forex scan (CFTC COT + rate differentials)\n\n"
    f"[{theme.TEXT_MUTED}]Or type[/] [{theme.ACCENT}]MACRO[/] [{theme.TEXT_MUTED}]for a regime quadrant scan.[/]"
)


class ScanPanel(Vertical):
    """Renders the active scan verdict."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "scan-panel"
        self._current_symbol = ""

    def compose(self) -> ComposeResult:
        yield Static(HEADER_HINT, classes="title", id="scan-header")
        yield Static(WELCOME_BODY, id="scan-welcome")
        yield Static("", id="scan-summary")
        yield DataTable(id="signals-table", show_cursor=False, zebra_stripes=True)
        yield Static("", id="key-metrics")
        yield Static("", id="price-ladder")
        yield Static("", id="trade-table")
        yield Static("", id="scan-status", classes="dim")

    def on_mount(self) -> None:
        signals_table = self.query_one("#signals-table", DataTable)
        signals_table.add_columns("Dimension", "Score", "Signal", "Rationale")
        signals_table.display = False

    def show_loading(self, symbol: str) -> None:
        self._current_symbol = symbol
        self.query_one("#scan-welcome", Static).display = False
        self.query_one("#scan-header", Static).update(
            f"[{theme.ACCENT} b]▎ SCAN PANEL[/]   "
            f"[{theme.AMBER}]Scanning {symbol}…[/]"
        )
        self.query_one("#scan-summary", Static).update(
            f"[{theme.AMBER}]Running compute_signals.py for {symbol}. "
            f"This typically takes 30-90 seconds.[/]"
        )
        self.query_one("#signals-table", DataTable).display = False
        self.query_one("#key-metrics", Static).update("")
        self.query_one("#price-ladder", Static).update("")
        self.query_one("#trade-table", Static).update("")
        self.query_one("#scan-status", Static).update(
            f"[{theme.TEXT_MUTED}]Fetching data from yfinance, FRED, EDGAR, options chains…[/]"
        )

    def show_error(self, symbol: str, error: str) -> None:
        self.query_one("#scan-header", Static).update(
            f"[{theme.ACCENT} b]▎ SCAN PANEL[/]   [{theme.RED}]{symbol} — ERROR[/]"
        )
        self.query_one("#scan-summary", Static).update(
            f"[{theme.RED}]Scan failed:[/] [{theme.TEXT}]{error}[/]"
        )
        self.query_one("#scan-status", Static).update(
            f"[{theme.TEXT_MUTED}]Check your network, FRED_API_KEY, and that scripts/requirements.txt is installed.[/]"
        )

    def render_scan(self, symbol: str, asset_class: str, scan_data: dict) -> None:
        """Populate every sub-widget from a compute_signals.py JSON payload."""
        self._current_symbol = symbol
        self.query_one("#scan-welcome", Static).display = False

        conv = scan_data.get("conviction", "—")
        score = scan_data.get("total_score", 0)
        regime = (scan_data.get("fred_regime") or {}).get("derived_regime", "?")
        score_clr = theme.score_color(score)
        conv_clr = theme.conviction_color(conv)

        self.query_one("#scan-header", Static).update(
            f"[{theme.ACCENT} b]▎ {symbol}[/]   "
            f"[{theme.TEXT_MUTED}]({asset_class})[/]   "
            f"[{theme.TEXT_MUTED}]Regime:[/] [{theme.regime_color(regime)} b]{regime}[/]"
        )

        self.query_one("#scan-summary", Static).update(
            f"[{theme.TEXT_MUTED}]Composite Score:[/] [{score_clr} b]{score:+d}[/]   "
            f"[{theme.TEXT_MUTED}]Conviction:[/] [{conv_clr} b]{conv}[/]"
        )

        signals_table = self.query_one("#signals-table", DataTable)
        signals_table.clear()
        signals_table.display = True

        signals = scan_data.get("signals", {})
        scores = scan_data.get("scores", {})
        for dim, sig in signals.items():
            sc = scores.get(dim, 0)
            sc_clr = theme.score_color(sc)
            sig_clr = theme.signal_color(sig)
            signals_table.add_row(
                f"[{theme.TEXT}]{dim.replace('_', ' ').title()}[/]",
                f"[{sc_clr} b]{sc:+d}[/]",
                f"[{sig_clr}]{sig}[/]",
                f"[{theme.TEXT_MUTED}]{self._rationale(scan_data, dim)}[/]",
            )

        self.query_one("#key-metrics", Static).update(self._render_metrics(scan_data, asset_class))
        self.query_one("#price-ladder", Static).update(self._render_price_ladder(scan_data, asset_class))
        self.query_one("#trade-table", Static).update(self._render_trade_table(scan_data, asset_class))

        news = scan_data.get("news_sentiment") or {}
        news_label = news.get("label", "—")
        news_clr = theme.signal_color(news_label)
        self.query_one("#scan-status", Static).update(
            f"[{theme.TEXT_MUTED}]News sentiment:[/] [{news_clr}]{news_label}[/]   "
            f"[{theme.TEXT_MUTED}]({news.get('positive_count', 0)} +  /  {news.get('negative_count', 0)} -)[/]"
        )

    @staticmethod
    def _rationale(scan_data: dict, dim: str) -> str:
        signals = scan_data.get("signals", {})
        return str(signals.get(dim, ""))[:60]

    def _render_metrics(self, scan_data: dict, asset_class: str) -> str:
        km = scan_data.get("key_metrics", {})
        if not km:
            return ""

        def fmt(v, prefix="", suffix="", default="—"):
            if v is None:
                return default
            try:
                f = float(v)
                if abs(f) > 1e9:
                    return f"{prefix}{f/1e9:.2f}B{suffix}"
                if abs(f) > 1e6:
                    return f"{prefix}{f/1e6:.2f}M{suffix}"
                return f"{prefix}{f:.2f}{suffix}"
            except (ValueError, TypeError):
                return str(v)

        if asset_class in ("equity", "index"):
            lines = [f"\n[{theme.ACCENT} b]▎ KEY METRICS[/]"]
            lines.append(
                f"  [{theme.TEXT_MUTED}]Price[/] [{theme.TEXT}]{fmt(km.get('price'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]52WH[/] [{theme.TEXT}]{fmt(km.get('week52_high'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]52WL[/] [{theme.TEXT}]{fmt(km.get('week52_low'), '$')}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]SMA50[/] [{theme.TEXT}]{fmt(km.get('sma_50'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]SMA200[/] [{theme.TEXT}]{fmt(km.get('sma_200'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]RSI14[/] [{theme.TEXT}]{fmt(km.get('rsi_14'))}[/]   "
                f"[{theme.TEXT_MUTED}]ATR14[/] [{theme.TEXT}]{fmt(km.get('atr_14'), '$')}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]POC[/] [{theme.AMBER}]{fmt(km.get('poc'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]VAH[/] [{theme.TEXT}]{fmt(km.get('vah'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]VAL[/] [{theme.TEXT}]{fmt(km.get('val'), '$')}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]FwdPE[/] [{theme.TEXT}]{fmt(km.get('pe_forward'))}[/]   "
                f"[{theme.TEXT_MUTED}]PEG[/] [{theme.TEXT}]{fmt(km.get('peg'))}[/]   "
                f"[{theme.TEXT_MUTED}]Short%[/] [{theme.TEXT}]{fmt(km.get('short_float_pct'))}[/]   "
                f"[{theme.TEXT_MUTED}]Inst%[/] [{theme.TEXT}]{fmt(km.get('inst_ownership_pct'))}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]P/C[/] [{theme.TEXT}]{fmt(km.get('pcr'))}[/]   "
                f"[{theme.TEXT_MUTED}]Net GEX[/] [{theme.TEXT}]{fmt(km.get('net_gex'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]Form4 (90d)[/] [{theme.TEXT}]{km.get('form4_count_90d', 0)}[/]"
            )
            return "\n".join(lines)
        elif asset_class == "crypto":
            lines = [f"\n[{theme.ACCENT} b]▎ KEY METRICS[/]"]
            lines.append(
                f"  [{theme.TEXT_MUTED}]Price[/] [{theme.TEXT}]{fmt(km.get('price_usd'), '$')}[/]   "
                f"[{theme.TEXT_MUTED}]MCap[/] [{theme.TEXT}]{fmt(km.get('market_cap_usd'), '$')}[/]"
            )
            fg_val = km.get("fear_greed_value")
            fg_label = km.get("fear_greed_label", "—")
            fg_clr = theme.GREEN if (fg_val is not None and fg_val < 25) else theme.RED if (fg_val is not None and fg_val > 75) else theme.AMBER
            lines.append(
                f"  [{theme.TEXT_MUTED}]Fear&Greed[/] [{fg_clr} b]{fg_val if fg_val is not None else '—'}[/] "
                f"[{theme.TEXT_MUTED}]({fg_label})[/]   "
                f"[{theme.TEXT_MUTED}]Funding[/] [{theme.TEXT}]{fmt(km.get('funding_rate_pct'), '', '%')}[/]   "
                f"[{theme.TEXT_MUTED}]OI 30d[/] [{theme.TEXT}]{fmt(km.get('oi_change_pct'), '', '%')}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]Price 30d[/] [{theme.TEXT}]{fmt(km.get('price_change_30d_pct'), '', '%')}[/]"
            )
            return "\n".join(lines)
        elif asset_class == "forex":
            lines = [f"\n[{theme.ACCENT} b]▎ KEY METRICS[/]"]
            lines.append(
                f"  [{theme.TEXT_MUTED}]COT Index 52W[/] [{theme.TEXT}]{fmt(km.get('cot_index_52w'))}[/]   "
                f"[{theme.TEXT_MUTED}]Positioning[/] [{theme.TEXT}]{km.get('cot_positioning', '—')}[/]"
            )
            lines.append(
                f"  [{theme.TEXT_MUTED}]US 10Y Yield[/] [{theme.TEXT}]{fmt(km.get('ten_year_usd_yield'), '', '%')}[/]"
            )
            return "\n".join(lines)
        return ""

    def _render_price_ladder(self, scan_data: dict, asset_class: str) -> str:
        if asset_class not in ("equity", "index"):
            return ""
        km = scan_data.get("key_metrics", {})
        price = km.get("price")
        poc = km.get("poc")
        vah = km.get("vah")
        val = km.get("val")
        hi = km.get("week52_high")
        lo = km.get("week52_low")
        sma50 = km.get("sma_50")
        sma200 = km.get("sma_200")
        hvns = km.get("hvns") or []

        if not (price and poc and vah and val):
            return f"\n[{theme.TEXT_MUTED}](insufficient level data for price ladder)[/]"

        levels = []
        levels.append((hi, "52W High", "░░░░░░░░░░", theme.TEXT_MUTED))
        for h in sorted([h for h in hvns if h and h > vah], reverse=True)[:2]:
            levels.append((h, "HVN", "███████░░░", theme.AMBER))
        levels.append((vah, "VAH", "████████░░", theme.GREEN))
        levels.append((poc, "POC", "██████████", theme.ACCENT))
        levels.append((val, "VAL", "████████░░", theme.RED))
        for h in sorted([h for h in hvns if h and h < val], reverse=True)[:2]:
            levels.append((h, "HVN", "███████░░░", theme.AMBER))
        if sma50:
            levels.append((sma50, "SMA50", "█████░░░░░", theme.BLUE))
        if sma200:
            levels.append((sma200, "SMA200", "█████░░░░░", theme.BLUE))
        levels.append((lo, "52W Low", "░░░░░░░░░░", theme.TEXT_MUTED))

        seen = set()
        unique = []
        for lvl in levels:
            if lvl[0] is None:
                continue
            key = round(lvl[0], 2)
            if key in seen:
                continue
            seen.add(key)
            unique.append(lvl)
        unique.sort(key=lambda x: x[0], reverse=True)

        out = [f"\n[{theme.ACCENT} b]▎ PRICE LADDER[/]", "```"]
        inserted_current = False
        for i, (p, label, bar, clr) in enumerate(unique):
            if not inserted_current and p < price:
                out.append(
                    f"  [{theme.AMBER} b]${price:>9.2f}  ◄ ◄ ◄ ◄ ◄  CURRENT[/]"
                )
                inserted_current = True
            out.append(f"  [{clr}]${p:>9.2f}  {bar}  {label}[/]")
        if not inserted_current:
            out.append(f"  [{theme.AMBER} b]${price:>9.2f}  ◄ ◄ ◄ ◄ ◄  CURRENT[/]")
        out.append("```")
        return "\n".join(out)

    def _render_trade_table(self, scan_data: dict, asset_class: str) -> str:
        if asset_class not in ("equity", "index"):
            return ""
        km = scan_data.get("key_metrics", {})
        score = scan_data.get("total_score", 0)
        price = km.get("price")
        poc = km.get("poc")
        vah = km.get("vah")
        val = km.get("val")
        atr = km.get("atr_14") or 0

        if not (price and poc and vah and val):
            return ""

        if score >= 1:
            direction = "LONG"
            entry = f"${val:.2f}–${poc:.2f}"
            stop = f"${max(0, val - 2 * atr):.2f}"
            t1 = f"${vah:.2f}"
            t2 = f"${km.get('week52_high', vah * 1.05):.2f}"
            entry_mid = (val + poc) / 2
            rr = (vah - entry_mid) / max(entry_mid - (val - 2 * atr), 0.01) if atr else None
        elif score <= -1:
            direction = "SHORT"
            entry = f"${poc:.2f}–${vah:.2f}"
            stop = f"${vah + 2 * atr:.2f}"
            t1 = f"${val:.2f}"
            t2 = f"${km.get('week52_low', val * 0.95):.2f}"
            entry_mid = (poc + vah) / 2
            rr = (entry_mid - val) / max((vah + 2 * atr) - entry_mid, 0.01) if atr else None
        else:
            return f"\n[{theme.ACCENT} b]▎ TRADE TABLE[/]\n  [{theme.AMBER}]NO TRADE — composite score is neutral.[/]"

        rr_str = f"1:{rr:.2f}" if rr else "—"
        rr_clr = theme.GREEN if (rr and rr >= 1.5) else theme.RED if rr else theme.DIM

        rows = [
            ("Direction", direction, theme.GREEN if direction == "LONG" else theme.RED),
            ("Entry", entry, theme.TEXT),
            ("Stop", stop, theme.RED),
            ("Target 1", t1, theme.GREEN),
            ("Target 2", t2, theme.GREEN),
            ("R:R", rr_str, rr_clr),
            ("Conviction", scan_data.get("conviction", ""), theme.conviction_color(scan_data.get("conviction", ""))),
        ]
        out = [f"\n[{theme.ACCENT} b]▎ TRADE TABLE[/]"]
        for label, val_, clr in rows:
            out.append(f"  [{theme.TEXT_MUTED}]{label:<12}[/] [{clr}]{val_}[/]")
        return "\n".join(out)
