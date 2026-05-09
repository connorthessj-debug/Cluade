"""Main screen — Bloomberg Terminal layout with all panels."""

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from core import asset_class as asset_class_mod
from core.scanner import run_scan
from core.macro_monitor import get_macro_snapshot
from core.news_feed import get_news_snapshot
from ui import theme
from ui.widgets.macro_panel import MacroPanel
from ui.widgets.watchlist_panel import WatchlistPanel
from ui.widgets.scan_panel import ScanPanel
from ui.widgets.news_ticker import NewsTicker
from ui.widgets.scan_history_panel import ScanHistoryPanel
from ui.widgets.audit_log_panel import AuditLogPanel
from ui.screens.scan_detail_screen import ScanDetailScreen


class MainScreen(Screen):
    """Primary terminal layout."""

    BINDINGS = [
        Binding("ctrl+r", "refresh_macro", "Refresh Macro"),
        Binding("ctrl+n", "refresh_news", "Refresh News"),
        Binding("ctrl+l", "focus_input", "Focus Input"),
        Binding("ctrl+w", "focus_watchlist", "Watchlist"),
        Binding("ctrl+h", "focus_history", "History"),
        Binding("escape", "focus_input", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Grid(id="main-grid"):
            yield MacroPanel()
            yield WatchlistPanel()
            yield ScanPanel()
            yield ScanHistoryPanel()
            yield AuditLogPanel()
            yield NewsTicker()
            with Horizontal(id="scan-input-row"):
                yield Input(placeholder="Type a symbol (AAPL, BTCUSDT, EURUSD, SPX, MACRO) and press ENTER", id="scan-input")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one(Input).focus()
        self.set_interval(900, self._refresh_macro_async)
        self.set_interval(300, self._refresh_news_async)
        await self._refresh_macro_async()
        await self._refresh_news_async()

    async def _refresh_macro_async(self) -> None:
        data = await get_macro_snapshot()
        try:
            self.query_one(MacroPanel).update_data(data)
        except Exception:
            pass

    async def _refresh_news_async(self) -> None:
        data = await get_news_snapshot()
        try:
            self.query_one(NewsTicker).update_data(data)
        except Exception:
            pass

    def action_refresh_macro(self) -> None:
        self.run_worker(self._refresh_macro_async(), exclusive=True, group="macro")

    def action_refresh_news(self) -> None:
        self.run_worker(self._refresh_news_async(), exclusive=True, group="news")

    def action_focus_input(self) -> None:
        self.query_one("#scan-input", Input).focus()

    def action_focus_watchlist(self) -> None:
        self.query_one(WatchlistPanel).focus()

    def action_focus_history(self) -> None:
        self.query_one(ScanHistoryPanel).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        symbol = (event.value or "").strip().upper()
        if not symbol:
            return
        event.input.value = ""
        await self._trigger_scan(symbol)

    async def on_watchlist_panel_symbol_selected(self, event) -> None:
        await self._trigger_scan(event.symbol)

    async def on_scan_history_panel_history_selected(self, event) -> None:
        from pathlib import Path
        path = Path(event.path)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            await self.app.push_screen(ScanDetailScreen(path.name, text))

    async def _trigger_scan(self, symbol: str) -> None:
        if symbol == "MACRO":
            ac = "macro"
        else:
            ac = asset_class_mod.detect(symbol)

        scan_panel = self.query_one(ScanPanel)
        scan_panel.show_loading(symbol)
        self.run_worker(self._do_scan(symbol, ac), exclusive=True, group="scan")

    async def _do_scan(self, symbol: str, asset_class: str) -> None:
        scan_panel = self.query_one(ScanPanel)
        try:
            data = await run_scan(symbol, asset_class)
        except Exception as e:
            scan_panel.show_error(symbol, str(e))
            return

        if data.get("error"):
            scan_panel.show_error(symbol, data["error"])
            return

        scan_panel.render_scan(symbol, asset_class, data)

        try:
            wl = self.query_one(WatchlistPanel)
            wl.update_conviction(symbol, data.get("conviction", "?"), asset_class)
        except Exception:
            pass

        try:
            self.query_one(ScanHistoryPanel).refresh_list()
            self.query_one(AuditLogPanel).refresh_audit()
        except Exception:
            pass
