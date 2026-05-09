"""Watchlist sidebar — symbols + last-scan conviction badges."""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, ListView, ListItem, Label

from ui import theme


WATCHLIST_FILE = Path(__file__).resolve().parent.parent.parent / "watchlist.json"

DEFAULT_SYMBOLS = [
    {"symbol": "SPX", "asset_class": "index", "conviction": "?"},
    {"symbol": "AAPL", "asset_class": "equity", "conviction": "?"},
    {"symbol": "NVDA", "asset_class": "equity", "conviction": "?"},
    {"symbol": "TSLA", "asset_class": "equity", "conviction": "?"},
    {"symbol": "BTCUSDT", "asset_class": "crypto", "conviction": "?"},
    {"symbol": "ETHUSDT", "asset_class": "crypto", "conviction": "?"},
    {"symbol": "EURUSD", "asset_class": "forex", "conviction": "?"},
]


class WatchlistPanel(Vertical):
    """Sidebar showing tracked symbols with their last conviction."""

    class SymbolSelected(Message):
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "watchlist-panel"
        self.symbols: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static(f"[{theme.ACCENT} b]▎ WATCHLIST[/]", classes="title")
        yield ListView(id="watchlist-list")
        yield Static("", id="watchlist-help", classes="dim")

    def on_mount(self) -> None:
        self.symbols = self.load_watchlist()
        self.refresh_list()
        self.query_one("#watchlist-help", Static).update(
            f"[{theme.TEXT_MUTED}]↑↓ navigate · ENTER scan[/]"
        )

    def load_watchlist(self) -> list[dict]:
        if WATCHLIST_FILE.exists():
            try:
                return json.loads(WATCHLIST_FILE.read_text())
            except Exception:
                return list(DEFAULT_SYMBOLS)
        return list(DEFAULT_SYMBOLS)

    def save_watchlist(self) -> None:
        try:
            WATCHLIST_FILE.write_text(json.dumps(self.symbols, indent=2))
        except Exception:
            pass

    def refresh_list(self) -> None:
        list_view = self.query_one("#watchlist-list", ListView)
        list_view.clear()
        for entry in self.symbols:
            sym = entry["symbol"]
            conv = entry.get("conviction", "?") or "?"
            ac = entry.get("asset_class", "?")
            clr = theme.conviction_color(conv)
            ac_clr = theme.TEXT_MUTED
            label = (
                f"[{theme.ACCENT}]{sym:<10}[/]"
                f"[{ac_clr}]{ac[:3]:<5}[/]"
                f"[{clr}]{conv[:14]}[/]"
            )
            list_view.append(ListItem(Label(label), id=f"wl-{sym}"))

    def update_conviction(self, symbol: str, conviction: str, asset_class: str = None) -> None:
        for entry in self.symbols:
            if entry["symbol"].upper() == symbol.upper():
                entry["conviction"] = conviction
                if asset_class:
                    entry["asset_class"] = asset_class
                break
        else:
            self.symbols.append({
                "symbol": symbol.upper(),
                "asset_class": asset_class or "?",
                "conviction": conviction,
            })
        self.save_watchlist()
        self.refresh_list()

    def add_symbol(self, symbol: str, asset_class: str) -> None:
        sym = symbol.upper()
        for entry in self.symbols:
            if entry["symbol"] == sym:
                return
        self.symbols.append({"symbol": sym, "asset_class": asset_class, "conviction": "?"})
        self.save_watchlist()
        self.refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id and event.item.id.startswith("wl-"):
            symbol = event.item.id[3:]
            self.post_message(self.SymbolSelected(symbol))
