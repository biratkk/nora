"""Tool selection modal for MCP server setup."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


class McpToolSelectionModal(ModalScreen[list[str]]):
    """Modal for selecting which MCP tools to enable.

    Displays all discovered tools with checkboxes. All are enabled by
    default. Returns a list of disabled tool names on dismiss.
    """

    DEFAULT_CSS = """
    McpToolSelectionModal { align: center middle; }
    McpToolSelectionModal > .modal-outer {
        width: 70%;
        max-height: 80%;
        border: round $primary;
        background: $surface;
    }
    McpToolSelectionModal .modal-content { padding: 1 2; height: 1fr; }
    McpToolSelectionModal .modal-status { background: $surface-lighten-1; padding: 0 1; }
    McpToolSelectionModal .title { text-style: bold; margin-bottom: 1; }
    McpToolSelectionModal VerticalScroll { height: 1fr; }
    McpToolSelectionModal .tool-row { height: auto; padding: 0 1; }
    McpToolSelectionModal .tool-row.selected { background: $primary 20%; }
    McpToolSelectionModal .tool-desc { color: $text-muted; padding: 0 0 0 4; height: auto; }
    """

    BINDINGS = [("escape", "close", "Save and Exit"), ("ctrl+c", "close", "Save and Exit")]

    def __init__(self, tools: list[dict]) -> None:
        super().__init__()
        self._tools = tools
        self._enabled: list[bool] = [True] * len(tools)
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        from textual.containers import Container

        with Container(classes="modal-outer"):
            with Container(classes="modal-content"):
                yield Static("Select tools to enable", classes="title")
                with VerticalScroll(id="tool-list"):
                    for i, tool in enumerate(self._tools):
                        check = "☑" if self._enabled[i] else "☐"
                        yield Static(
                            f"{check}  {tool['name']}",
                            classes="tool-row selected" if i == 0 else "tool-row",
                            id=f"tool-{i}",
                        )
                        if tool.get("description"):
                            yield Static(
                                tool["description"],
                                classes="tool-desc",
                                id=f"desc-{i}",
                            )
            yield Static(
                "[Esc/Ctrl+C] Save and Exit  ↑/↓ Navigate  Enter Toggle",
                classes="modal-status",
            )

    def _refresh_list(self) -> None:
        """Update visual state of all tool rows."""
        for i, tool in enumerate(self._tools):
            try:
                row = self.query_one(f"#tool-{i}", Static)
            except Exception:
                continue
            check = "☑" if self._enabled[i] else "☐"
            row.update(f"{check}  {tool['name']}")
            if i == self._selected_index:
                row.add_class("selected")
                row.scroll_visible()
            else:
                row.remove_class("selected")

    async def on_key(self, event) -> None:
        if not self._tools:
            return

        if event.key in ("up", "ctrl+p"):
            if self._selected_index > 0:
                self._selected_index -= 1
                self._refresh_list()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self._selected_index < len(self._tools) - 1:
                self._selected_index += 1
                self._refresh_list()
            event.prevent_default()
        elif event.key == "enter":
            self._enabled[self._selected_index] = not self._enabled[self._selected_index]
            self._refresh_list()
            event.prevent_default()

    def action_close(self) -> None:
        disabled = [
            self._tools[i]["name"]
            for i in range(len(self._tools))
            if not self._enabled[i]
        ]
        self.dismiss(disabled)
