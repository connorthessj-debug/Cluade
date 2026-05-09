"""Full-screen viewer for a saved scan markdown file."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown


class ScanDetailScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back"),
    ]

    def __init__(self, title: str, markdown: str) -> None:
        super().__init__()
        self.title = title
        self._markdown = markdown

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="detail-body"):
            yield Markdown(self._markdown)
        yield Footer()
