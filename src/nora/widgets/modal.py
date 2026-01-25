"""Base modal component."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static


class BaseModal(ModalScreen):
    """
    Base class for modal dialogs with consistent styling.
    
    Provides a standard layout with content area and status bar.
    Subclasses should override compose_content() and optionally status_text().
    """
    
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

    BINDINGS = [
        ("escape", "close", "Close"),
        ("ctrl+c", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container():
            with Container(classes="modal-content"):
                yield from self.compose_content()
            yield Static(self.status_text(), classes="modal-status")

    def status_text(self) -> str:
        """
        Get the status bar text.
        
        Override to customize status bar content.
        
        Returns:
            Status bar text.
        """
        return "Esc / Ctrl+C to close"

    def compose_content(self) -> ComposeResult:
        """
        Compose the modal content.
        
        Override this method to provide modal-specific content.
        
        Yields:
            Content widgets.
        """
        yield from ()

    def action_close(self) -> None:
        """Close the modal."""
        self.dismiss()
