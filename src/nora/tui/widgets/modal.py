"""Base modal component."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static


class BaseModal(ModalScreen):
    DEFAULT_CSS = """
    BaseModal { align: center middle; }
    BaseModal > Container {
        width: auto;
        height: auto;
        border: round $primary;
        background: $surface;
    }
    BaseModal .modal-content { padding: 1 2; }
    BaseModal .modal-status { background: $surface-lighten-1; padding: 0 1; }
    """

    BINDINGS = [("escape", "close", "Close"), ("ctrl+c", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Container():
            with Container(classes="modal-content"):
                yield from self.compose_content()
            yield Static(self.status_text(), classes="modal-status")

    def status_text(self) -> str:
        """Override to customize status bar text."""
        return "Esc / Ctrl+C to close"

    def compose_content(self) -> ComposeResult:
        """Override this to provide modal content."""
        yield from ()

    def action_close(self) -> None:
        self.dismiss()
