"""Diff viewer modal for file changes."""

import difflib
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input
from textual.binding import Binding

MIN_CONTEXT = 2


class DiffModal(ModalScreen[str]):
    """
    Full-screen modal showing inline diff of file changes.
    
    Supports accept, reject, and suggestion input.
    """

    DEFAULT_CSS = """
    DiffModal { background: $surface; }
    DiffModal #diff-container { height: 1fr; margin: 1; border: round $primary; }
    DiffModal #diff-scroll { height: 1fr; padding: 0 1; align: center middle; }
    DiffModal #diff-content { height: auto; width: 100%; }
    DiffModal .line-del { background: #5c1c1c; }
    DiffModal .line-add { background: #1c5c1c; }
    DiffModal #status-bar { height: auto; background: $primary; width: 100%; layout: horizontal; }
    DiffModal #status-bar > Static { background: $primary; padding: 0 1; }
    DiffModal #status-left { width: 1fr; }
    DiffModal #status-right { width: auto; }
    DiffModal #input-container { height: auto; padding: 0 1; }
    DiffModal #suggestion-input { border: round $accent; background: transparent; }
    VerticalScroll { scrollbar-size: 0 0; }
    """

    BINDINGS = [
        Binding("ctrl+y", "accept", "Accept"),
        Binding("ctrl+n", "reject", "Reject"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, path: str, old_content: str, new_content: str, reason: str) -> None:
        """
        Initialize the diff modal.
        
        Args:
            path: File path being modified.
            old_content: Original file content.
            new_content: New file content.
            reason: One-line summary of the purpose of this change.
        """
        super().__init__()
        self.path = path
        self.old_content = old_content
        self.new_content = new_content
        self.reason = reason

    def compose(self) -> ComposeResult:
        """Compose the diff modal layout."""
        with Container(id="diff-container"):
            with VerticalScroll(id="diff-scroll"):
                yield Vertical(id="diff-content")
            with Horizontal(id="status-bar"):
                yield Static(f"[bold]{self.path}[/bold] · {self.reason}", id="status-left")
                yield Static("Ctrl+D/U: scroll | Ctrl+Y: accept | Ctrl+N: reject", id="status-right")
        with Container(id="input-container"):
            yield Input(placeholder="Suggest improvements...", id="suggestion-input")

    def on_mount(self) -> None:
        """Render diff after mount."""
        self.call_after_refresh(self._render_diff)

    def _render_diff(self) -> None:
        """Render the diff with context-aware line display."""
        old_lines = self.old_content.splitlines()
        new_lines = self.new_content.splitlines()
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        # Count changed lines
        changed_lines = 0
        for tag, i1, i2, j1, j2 in opcodes:
            if tag != "equal":
                changed_lines += (i2 - i1) + (j2 - j1)

        # Calculate available height and context
        scroll = self.query_one("#diff-scroll", VerticalScroll)
        available = scroll.size.height - 2
        extra = max(0, available - changed_lines)
        context = max(MIN_CONTEXT, extra // 2)

        pane = self.query_one("#diff-content", Vertical)
        
        for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
            if tag == "equal":
                length = i2 - i1
                if idx == 0:
                    start = max(0, length - context)
                    for k in range(start, length):
                        ln = i1 + k + 1
                        pane.mount(Static(f"{ln:4}   {old_lines[i1 + k]}"))
                elif idx == len(opcodes) - 1:
                    for k in range(min(context, length)):
                        ln = i1 + k + 1
                        pane.mount(Static(f"{ln:4}   {old_lines[i1 + k]}"))
                else:
                    if length <= context * 2:
                        for k in range(length):
                            ln = i1 + k + 1
                            pane.mount(Static(f"{ln:4}   {old_lines[i1 + k]}"))
                    else:
                        for k in range(context):
                            ln = i1 + k + 1
                            pane.mount(Static(f"{ln:4}   {old_lines[i1 + k]}"))
                        for k in range(length - context, length):
                            ln = i1 + k + 1
                            pane.mount(Static(f"{ln:4}   {old_lines[i1 + k]}"))
            elif tag == "replace":
                for k in range(i2 - i1):
                    ln = i1 + k + 1
                    pane.mount(Static(f"{ln:4} - {old_lines[i1 + k]}", classes="line-del"))
                for k in range(j2 - j1):
                    ln = j1 + k + 1
                    pane.mount(Static(f"{ln:4} + {new_lines[j1 + k]}", classes="line-add"))
            elif tag == "delete":
                for k in range(i2 - i1):
                    ln = i1 + k + 1
                    pane.mount(Static(f"{ln:4} - {old_lines[i1 + k]}", classes="line-del"))
            elif tag == "insert":
                for k in range(j2 - j1):
                    ln = j1 + k + 1
                    pane.mount(Static(f"{ln:4} + {new_lines[j1 + k]}", classes="line-add"))

        self.query_one("#suggestion-input", Input).focus()

    def on_key(self, event) -> None:
        """Handle scroll keys."""
        if event.key in ("ctrl+d", "ctrl+u"):
            delta = 10 if event.key == "ctrl+d" else -10
            self.query_one("#diff-scroll", VerticalScroll).scroll_relative(y=delta)
            event.prevent_default()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle suggestion input submission."""
        suggestion = event.value.strip()
        self.dismiss(suggestion if suggestion else "n")

    def action_accept(self) -> None:
        """Accept the changes."""
        self.dismiss("y")

    def action_reject(self) -> None:
        """Reject the changes."""
        self.dismiss("reject")

    def action_cancel(self) -> None:
        """Cancel without decision."""
        self.dismiss("n")
