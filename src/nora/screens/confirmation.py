"""Tool confirmation modal."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ToolConfirmModal(ModalScreen[str]):
    """
    Modal for confirming tool execution.
    
    Shows tool name and parameters, allows approve/deny.
    """

    DEFAULT_CSS = """
    ToolConfirmModal {
        align: center middle;
    }
    ToolConfirmModal > Container {
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    ToolConfirmModal .title {
        text-style: bold;
        margin-bottom: 1;
    }
    ToolConfirmModal .detail {
        margin-bottom: 1;
        max-height: 10;
        overflow-y: auto;
    }
    ToolConfirmModal > Container > Horizontal {
        width: 100%;
        height: auto;
        align: center middle;
    }
    ToolConfirmModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, tool_name: str, reason: dict) -> None:
        """
        Initialize the confirmation modal.
        
        Args:
            tool_name: Name of the tool.
            reason: Dictionary with tool details (path, preview, old, new).
        """
        super().__init__()
        self.tool_name = tool_name
        self.reason = reason

    def compose(self) -> ComposeResult:
        """Compose the modal content."""
        with Container():
            yield Static(f"[bold]Tool: {self.tool_name}[/bold]", classes="title")
            
            if "path" in self.reason:
                yield Static(f"Path: {self.reason['path']}", classes="detail")
            if "preview" in self.reason:
                yield Static(f"Content:\n{self.reason['preview']}", classes="detail")
            if "old" in self.reason:
                yield Static(f"Replace:\n{self.reason['old']}", classes="detail")
            if "new" in self.reason:
                yield Static(f"With:\n{self.reason['new']}", classes="detail")
            
            with Horizontal():
                yield Button("Approve", id="approve", variant="success")
                yield Button("Deny", id="deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss("y" if event.button.id == "approve" else "n")
