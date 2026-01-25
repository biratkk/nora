"""Chat message widget."""

from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Markdown


class ChatMessage(Container):
    def __init__(self, role: str, content: str, timestamp: datetime | None = None) -> None:
        super().__init__()
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.add_class(f"message-{role}")

    def compose(self) -> ComposeResult:
        yield Markdown(self.content, classes="message-content")
        if self.role == "user":
            yield Static(self._format_time(), classes="message-time")

    def _format_time(self) -> str:
        delta = datetime.now() - self.timestamp
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "[dim]now[/dim]"
        elif mins < 60:
            return f"[dim]{mins}m ago[/dim]"
        else:
            return f"[dim]{mins // 60}h ago[/dim]"

    def update_content(self, content: str) -> None:
        self.content = content
        md = self.query("Markdown.message-content")
        if md:
            md.first().update(content)


class ToolCallBlock(Container):
    """Container for tool call indicators."""

    def __init__(self) -> None:
        super().__init__()
        self.add_class("message-tool")

    def compose(self) -> ComposeResult:
        return []

    def add_tool(self, tool: str, params: dict, finished: bool = False) -> "ToolIndicator":
        indicator = ToolIndicator(tool, params, finished)
        self.mount(indicator)
        return indicator


class ShellBlock(Container):
    """Container for shell command with collapsible command details."""

    DEFAULT_CSS = """
    ShellBlock { height: auto; padding: 0 1; margin: 1 0; }
    ShellBlock .shell-header { height: 1; }
    ShellBlock .shell-nested { padding-left: 2; height: auto; }
    ShellBlock .shell-nested.collapsed { display: none; }
    ShellBlock .shell-command { height: 1; }
    """

    def __init__(
        self, 
        program: str, 
        args: list[str], 
        reason: str, 
        collapsed: bool = True
    ) -> None:
        super().__init__()
        self.program = program
        self.args = args
        self.reason = reason
        self.finished = False
        self.failed = False
        self.collapsed = collapsed

    def compose(self) -> ComposeResult:
        yield Static(self._format_header(), classes="shell-header", id="shell-header")
        classes = "shell-nested collapsed" if self.collapsed else "shell-nested"
        with Container(classes=classes, id="shell-nested"):
            command = f"{self.program} {' '.join(self.args)}" if self.args else self.program
            yield Static(f"[dim]└─ {command}[/dim]", classes="shell-command")

    def _format_header(self) -> str:
        hint = " [dim]Ctrl+O to expand[/dim]" if self.collapsed else ""
        if self.failed:
            return f"[red]✗ Shell({self.reason})[/red]{hint}"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} Shell({self.reason})[/dim]{hint}"

    def mark_finished(self) -> None:
        self.finished = True
        self.query_one("#shell-header", Static).update(self._format_header())

    def mark_failed(self) -> None:
        self.failed = True
        self.finished = True
        self.query_one("#shell-header", Static).update(self._format_header())

    def toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        nested = self.query_one("#shell-nested", Container)
        if self.collapsed:
            nested.add_class("collapsed")
        else:
            nested.remove_class("collapsed")
        self.query_one("#shell-header", Static).update(self._format_header())


class SubagentBlock(Container):
    """Container for subagent with nested output."""

    DEFAULT_CSS = """
    SubagentBlock { height: auto; padding: 0 1; margin: 1 0; }
    SubagentBlock .subagent-header { height: 1; }
    SubagentBlock .subagent-nested { padding-left: 2; height: auto; }
    SubagentBlock .subagent-nested.collapsed { display: none; }
    SubagentBlock .nested-tool { height: 1; }
    SubagentBlock .nested-content { height: 1; color: $text-muted; }
    """

    def __init__(self, reason: str, collapsed: bool = True) -> None:
        super().__init__()
        self.reason = reason
        self.finished = False
        self.failed = False
        self.collapsed = collapsed
        self._content_buffer = ""  # Accumulate all content
        self._content_widget: Static | None = None
        self._nested_items: list[tuple[Static, str]] = []  # Track (widget, base_content) pairs

    def compose(self) -> ComposeResult:
        yield Static(self._format_header(), classes="subagent-header", id="subagent-header")
        classes = "subagent-nested collapsed" if self.collapsed else "subagent-nested"
        yield Container(classes=classes, id="subagent-nested")

    def _format_header(self) -> str:
        hint = " [dim]Ctrl+O to expand[/dim]" if self.collapsed else ""
        if self.failed:
            return f"[red]✗ {self.reason}[/red]{hint}"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} {self.reason}[/dim]{hint}"

    def add_nested_tool(self, tool: str, params: dict) -> None:
        nested = self.query_one("#subagent-nested", Container)
        if "path" in params:
            args = params["path"]
        else:
            args = ", ".join(str(v)[:30] for v in params.values())
        base_content = f"{tool}({args})"
        widget = Static(f"[dim]├─ {base_content}[/dim]", classes="nested-tool")
        self._nested_items.append((widget, base_content))
        nested.mount(widget)
        self._update_last_item_prefix()

    def add_nested_content(self, content: str) -> None:
        """Accumulate content into a single line display."""
        self._content_buffer += content
        nested = self.query_one("#subagent-nested", Container)
        
        # Format: single line, truncated, newlines replaced with spaces
        preview = self._content_buffer.replace("\n", " ").strip()
        if len(preview) > 100:
            preview = preview[:100] + "..."
        
        if self._content_widget is None:
            self._content_widget = Static(f"[dim]├─ {preview}[/dim]", classes="nested-content")
            self._nested_items.append((self._content_widget, preview))
            nested.mount(self._content_widget)
        else:
            # Update the tracked content for this widget
            for i, (widget, _) in enumerate(self._nested_items):
                if widget is self._content_widget:
                    self._nested_items[i] = (widget, preview)
                    break
            self._content_widget.update(f"[dim]├─ {preview}[/dim]")
        self._update_last_item_prefix()

    def _update_last_item_prefix(self) -> None:
        """Update all items so only the last one uses └─ prefix."""
        for i, (widget, base_content) in enumerate(self._nested_items):
            is_last = (i == len(self._nested_items) - 1)
            prefix = "└─" if is_last else "├─"
            widget.update(f"[dim]{prefix} {base_content}[/dim]")

    def mark_finished(self) -> None:
        self.finished = True
        self.query_one("#subagent-header", Static).update(self._format_header())

    def mark_failed(self) -> None:
        self.failed = True
        self.finished = True
        self.query_one("#subagent-header", Static).update(self._format_header())

    def toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        nested = self.query_one("#subagent-nested", Container)
        if self.collapsed:
            nested.add_class("collapsed")
        else:
            nested.remove_class("collapsed")
        # Update header to show/hide hint
        self.query_one("#subagent-header", Static).update(self._format_header())


class ToolIndicator(Static):
    """One-line tool indicator."""

    def __init__(self, tool: str, params: dict, finished: bool = False) -> None:
        self.tool = tool
        self.params = params
        self.finished = finished
        self.failed = False
        super().__init__(self._format())

    def _format(self) -> str:
        if "path" in self.params:
            args = self.params["path"]
        else:
            args = ", ".join(str(v) for v in self.params.values())
        if self.failed:
            return f"[red]✗ {self.tool}({args})[/red]"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} {self.tool}({args})[/dim]"

    def mark_finished(self) -> None:
        self.finished = True
        self.update(self._format())

    def mark_failed(self) -> None:
        self.failed = True
        self.finished = True
        self.update(self._format())
