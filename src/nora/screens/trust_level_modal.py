"""Trust level selection modal."""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.binding import Binding

from nora.services.trust_service import TrustLevel


class TrustLevelModal(ModalScreen[Optional[int]]):
    """
    Modal for selecting trust level scope.
    
    Shows different trust levels (1-N) for the command and
    allows user to select one by pressing the corresponding number.
    """

    DEFAULT_CSS = """
    TrustLevelModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    TrustLevelModal > Container {
        width: auto;
        min-width: 50;
        max-width: 80;
        height: auto;
        border: round $primary;
        background: black;
        padding: 1 2;
    }
    
    TrustLevelModal .title {
        text-style: bold;
        margin-bottom: 1;
        text-align: center;
    }
    
    TrustLevelModal .options {
        margin-top: 1;
    }
    
    TrustLevelModal .option {
        padding: 0 1;
    }
    
    TrustLevelModal .key {
        text-style: bold;
        color: $accent;
    }
    
    TrustLevelModal .hint {
        margin-top: 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, trust_levels: list[TrustLevel]) -> None:
        """
        Initialize the trust level modal.
        
        Args:
            trust_levels: List of trust level options.
        """
        super().__init__()
        self.trust_levels = trust_levels
        self._setup_bindings()
    
    def _setup_bindings(self) -> None:
        """Dynamically create bindings for each level."""
        # We'll handle key presses manually since we need dynamic bindings
        pass

    def compose(self) -> ComposeResult:
        """Compose the modal content."""
        with Container():
            yield Static("[bold]Select trust level:[/bold]", classes="title")
            
            with Vertical(classes="options"):
                for level in self.trust_levels:
                    yield Static(
                        f"[bold cyan][{level.level}][/bold cyan] {level.display}",
                        classes="option"
                    )
            
            yield Static("Press 1-9 to select, Esc to cancel", classes="hint")

    def on_key(self, event) -> None:
        """Handle key press for level selection."""
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            return
        
        # Check if it's a digit key
        if event.key.isdigit():
            level_num = int(event.key)
            if 1 <= level_num <= len(self.trust_levels):
                self.dismiss(level_num)
                event.prevent_default()
