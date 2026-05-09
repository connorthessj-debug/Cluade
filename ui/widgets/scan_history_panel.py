"""Right panel — list of past scans from scanned/."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, ListView, ListItem, Label

from core.scan_parser import list_scans
from ui import theme


SCANNED_DIR = Path(__file__).resolve().parent.parent.parent / "scanned"


class ScanHistoryPanel(Vertical):
    class HistorySelected(Message):
        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "history-panel"

    def compose(self) -> ComposeResult:
        yield Static(f"[{theme.ACCENT} b]▎ HISTORY[/]", classes="title")
        yield ListView(id="history-list")
        yield Static("", id="history-status", classes="dim")

    def on_mount(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        list_view = self.query_one("#history-list", ListView)
        list_view.clear()
        scans = list_scans(SCANNED_DIR)
        if not scans:
            self.query_one("#history-status", Static).update(
                f"[{theme.TEXT_MUTED}]No scans yet — type a symbol below to begin.[/]"
            )
            return
        for scan in scans[:30]:
            sym = scan["meta"].get("symbol", "?")
            date = scan["meta"].get("date", "")
            conv = scan.get("conviction", "?")
            ac = scan.get("asset_class", "?")
            clr = theme.conviction_color(conv)
            label = (
                f"[{theme.TEXT_MUTED}]{date[5:] if date else '—':>5}[/] "
                f"[{theme.ACCENT}]{sym:<8}[/]"
                f"[{theme.TEXT_MUTED}]{ac[:3]:<4}[/]"
                f"[{clr}]{conv[:14]}[/]"
            )
            list_view.append(ListItem(Label(label), id=f"hist-{sym}-{date}"))
        self.query_one("#history-status", Static).update(
            f"[{theme.TEXT_MUTED}]{len(scans)} total scans  ·  ENTER to open[/]"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not event.item or not event.item.id:
            return
        scans = list_scans(SCANNED_DIR)
        idx = self.query_one("#history-list", ListView).index
        if idx is None or idx >= len(scans):
            return
        path = scans[idx]["path"]
        self.post_message(self.HistorySelected(path))
