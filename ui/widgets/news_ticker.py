"""Bottom strip — scrolling news headlines."""

from textual.widgets import Static
from textual.reactive import reactive

from ui import theme


class NewsTicker(Static):
    """Single-line scrolling marquee of recent headlines."""

    DEFAULT_CSS = ""

    headlines: reactive[list] = reactive([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "news-ticker"
        self._scroll_pos = 0
        self._marquee_text = ""
        self._timer = None

    def on_mount(self) -> None:
        self.update_label("LOADING NEWS…")
        self._timer = self.set_interval(0.4, self._tick)

    def update_data(self, news_data: dict) -> None:
        if not news_data or news_data.get("error"):
            self.update_label("[NEWS UNAVAILABLE]")
            return
        headlines = news_data.get("headlines", [])
        if not headlines:
            self.update_label("[NO HEADLINES]")
            return
        sentiment = news_data.get("sentiment_summary", {})
        label = sentiment.get("label", "MIXED")
        clr = theme.signal_color(label)
        parts = []
        for h in headlines[:8]:
            title = h.get("title", "")
            source = (h.get("source", "") or "").split(",")[0]
            parts.append(f"{source.upper()}: {title}" if source else title)
        marquee = "   •   ".join(parts) + "   •   "
        self._marquee_text = marquee
        self._scroll_pos = 0
        self._sentiment_clr = clr
        self._sentiment_label = label

    def _tick(self) -> None:
        if not self._marquee_text:
            return
        width = max(self.size.width - 20, 60)
        if self._scroll_pos >= len(self._marquee_text):
            self._scroll_pos = 0
        view = (self._marquee_text + self._marquee_text)[
            self._scroll_pos : self._scroll_pos + width
        ]
        self._scroll_pos += 1
        clr = getattr(self, "_sentiment_clr", theme.AMBER)
        label = getattr(self, "_sentiment_label", "—")
        self.update_label(f"[{clr} b]{label:<8}[/] [{theme.TEXT}]{view}[/]")

    def update_label(self, text: str) -> None:
        prefix = f"[{theme.ACCENT} b]▎ NEWS[/]  "
        self.update(prefix + text)
