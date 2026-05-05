"""Audit log panel — shows pending self-improvement proposals."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from core.scan_parser import list_scans, parse_scan_file
from ui import theme


SCANNED_DIR = Path(__file__).resolve().parent.parent.parent / "scanned"


class AuditLogPanel(Vertical):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "audit-panel"

    def compose(self) -> ComposeResult:
        yield Static(f"[{theme.ACCENT} b]▎ SELF-IMPROVEMENT AUDIT — Pending Proposals[/]", classes="title")
        yield Static("", id="audit-body")

    def on_mount(self) -> None:
        self.refresh_audit()

    def refresh_audit(self) -> None:
        scans = list_scans(SCANNED_DIR)[:5]
        if not scans:
            self.query_one("#audit-body", Static).update(
                f"[{theme.TEXT_MUTED}]No audit findings yet. Run a scan to populate this panel.[/]"
            )
            return

        all_issues = []
        all_proposals = []
        for scan in scans:
            try:
                parsed = parse_scan_file(Path(scan["path"]))
                audit = parsed.get("audit", {})
                for issue in audit.get("issues", []):
                    all_issues.append((scan["meta"].get("symbol", "?"), issue))
                for prop in audit.get("proposals", []):
                    all_proposals.append((scan["meta"].get("symbol", "?"), prop))
            except Exception:
                continue

        lines = []
        if all_issues:
            lines.append(f"[{theme.RED} b]ISSUES ({len(all_issues)}):[/]")
            for sym, issue in all_issues[:6]:
                lines.append(f"  [{theme.AMBER}]●[/] [{theme.TEXT_MUTED}]{sym}:[/] [{theme.TEXT}]{issue[:120]}[/]")
        if all_proposals:
            lines.append(f"\n[{theme.GREEN} b]PROPOSED FIXES ({len(all_proposals)}):[/]")
            for sym, prop in all_proposals[:6]:
                lines.append(f"  [{theme.GREEN}]→[/] [{theme.TEXT_MUTED}]{sym}:[/] [{theme.TEXT}]{prop[:120]}[/]")
        if not lines:
            lines.append(f"[{theme.TEXT_MUTED}]No pending audit issues across recent scans.[/]")
        else:
            lines.append(f"\n[{theme.TEXT_MUTED}]Tip: Review in Claude Code with /scan to apply fixes via the consent gate.[/]")

        self.query_one("#audit-body", Static).update("\n".join(lines))
