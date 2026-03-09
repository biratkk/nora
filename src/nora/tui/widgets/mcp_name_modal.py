"""Modal for entering MCP server name."""

from typing import Callable

from textual.app import ComposeResult
from textual.widgets import Input, Static

from nora.tui.widgets.modal import BaseModal


class McpNameModal(BaseModal):
    """Modal for entering a name for a new MCP server."""

    DEFAULT_CSS = """
    McpNameModal > Container { width: 60; }
    McpNameModal .title { text-style: bold; margin-bottom: 1; }
    McpNameModal .mcp-name-input { margin-bottom: 0; }
    McpNameModal .mcp-error { color: red; height: auto; min-height: 1; }
    """

    def __init__(self, scope: str, name_exists: Callable[[str, str], bool]) -> None:
        """Initialize the modal.

        Args:
            scope: "local" or "global" — for collision checking.
            name_exists: Callable that checks if a server name already exists.
        """
        super().__init__()
        self._scope = scope
        self._name_exists = name_exists

    def status_text(self) -> str:
        return "Enter to confirm  Esc to cancel"

    def compose_content(self) -> ComposeResult:
        yield Static("Enter a name for this MCP server:", classes="title")
        yield Input(
            placeholder="e.g. chrome-devtools",
            classes="mcp-name-input",
            id="mcp-name-input",
        )
        yield Static("", classes="mcp-error", id="mcp-name-error")

    def on_mount(self) -> None:
        self.query_one("#mcp-name-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "mcp-name-input":
            return
        event.stop()

        value = event.value.strip()
        error_label = self.query_one("#mcp-name-error", Static)

        if not value:
            error_label.update("Name cannot be empty")
            return
        if " " in value or "/" in value:
            error_label.update("Name cannot contain spaces or slashes")
            return
        if self._name_exists(value, self._scope):
            error_label.update(f"Name '{value}' already exists in {self._scope} scope")
            return

        self.dismiss(value)

    def action_close(self) -> None:
        self.dismiss(None)
