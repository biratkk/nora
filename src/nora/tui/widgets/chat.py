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


class ShellMessage(Container):
    """
    Displays a shell passthrough command and its output.

    Shows the command prefixed with ! and output below.
    """

    DEFAULT_CSS = """
    ShellMessage {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        border-left: solid red;
        background: #330000 10%;
    }
    ShellMessage .shell-command {
        height: auto;
        color: red;
    }
    ShellMessage .shell-output {
        height: auto;
        color: $text;
        padding-left: 1;
    }
    """

    def __init__(self, command: str, output: str) -> None:
        super().__init__()
        self.command = command
        self.output = output

    def compose(self) -> ComposeResult:
        yield Static(f"[red]! {self.command}[/red]", classes="shell-command")
        if self.output:
            yield Static(self.output, classes="shell-output")


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
    """Container for shell command with collapsible command details and output."""

    DEFAULT_CSS = """
    ShellBlock { height: auto; padding: 0 1; margin: 0 0 1 0; }
    ShellBlock .shell-header { height: 1; }
    ShellBlock .shell-nested { padding-left: 2; height: auto; }
    ShellBlock .shell-nested.collapsed { display: none; }
    ShellBlock .shell-command { height: 1; }
    ShellBlock .shell-output-line { height: 1; }
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
        self._output_lines: list[Static] = []

    def compose(self) -> ComposeResult:
        yield Static(self._format_header(), classes="shell-header", id="shell-header")
        classes = "shell-nested collapsed" if self.collapsed else "shell-nested"
        with Container(classes=classes, id="shell-nested"):
            command = f"{self.program} {' '.join(self.args)}" if self.args else self.program
            yield Static(f"[dim]├─ {command}[/dim]", classes="shell-command", id="shell-command")

    def _format_header(self) -> str:
        hint = " [dim]Ctrl+O to expand[/dim]" if self.collapsed else ""
        if self.failed:
            return f"[red]✗ Shell({self.reason})[/red]{hint}"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} Shell({self.reason})[/dim]{hint}"

    def set_output(self, output: str) -> None:
        """Set the command output, displayed as nested lines when expanded."""
        nested = self.query_one("#shell-nested", Container)
        for widget in self._output_lines:
            widget.remove()
        self._output_lines.clear()

        command = f"{self.program} {' '.join(self.args)}" if self.args else self.program

        if not output or not output.strip():
            self.query_one("#shell-command", Static).update(f"[dim]└─ {command}[/dim]")
            return

        self.query_one("#shell-command", Static).update(f"[dim]├─ {command}[/dim]")

        lines = output.strip().split("\n")
        max_lines = 20
        truncated = len(lines) > max_lines
        display_lines = lines[:max_lines]

        for i, line in enumerate(display_lines):
            is_last = (i == len(display_lines) - 1) and not truncated
            prefix = "└─" if is_last else "├─"
            widget = Static(f"{prefix} {line}", classes="shell-output-line", markup=False)
            self._output_lines.append(widget)
            nested.mount(widget)

        if truncated:
            remaining = len(lines) - max_lines
            widget = Static(f"[dim]└─ ... ({remaining} more lines)[/dim]", classes="shell-output-line")
            self._output_lines.append(widget)
            nested.mount(widget)

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
    SubagentBlock { height: auto; padding: 0 1; margin: 0 0 1 0; }
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
        self._content_buffer = ""
        self._content_widget: Static | None = None
        self._nested_items: list[tuple[Static, str]] = []

    def compose(self) -> ComposeResult:
        yield Static(self._format_header(), classes="subagent-header", id="subagent-header")
        classes = "subagent-nested collapsed" if self.collapsed else "subagent-nested"
        yield Container(classes=classes, id="subagent-nested")

    def _format_header(self) -> str:
        hint = " [dim]Ctrl+O to expand[/dim]" if self.collapsed else ""
        if self.failed:
            return f"[red]✗ Subagent({self.reason})[/red]{hint}"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} Subagent({self.reason})[/dim]{hint}"

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

        preview = self._content_buffer.replace("\n", " ").strip()
        if len(preview) > 100:
            preview = preview[:100] + "..."

        if self._content_widget is None:
            self._content_widget = Static(f"[dim]├─ {preview}[/dim]", classes="nested-content")
            self._nested_items.append((self._content_widget, preview))
            nested.mount(self._content_widget)
        else:
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
        self.query_one("#subagent-header", Static).update(self._format_header())


class ToolIndicator(Container):
    """Tool indicator with optional nested output lines."""

    DEFAULT_CSS = """
    ToolIndicator { height: auto; margin: 0 0 1 0; }
    ToolIndicator .tool-header { height: 1; }
    ToolIndicator .tool-nested { padding-left: 2; height: auto; }
    ToolIndicator .tool-nested.collapsed { display: none; }
    ToolIndicator .tool-output-line { height: 1; }
    """

    # Tools whose output should be shown in verbose mode
    VERBOSE_TOOLS = {"Search"}

    def __init__(self, tool: str, params: dict, finished: bool = False, collapsed: bool = True) -> None:
        super().__init__()
        self.tool = tool
        self.params = params
        self.finished = finished
        self.failed = False
        self.collapsed = collapsed
        self._output_lines: list[Static] = []

    def compose(self) -> ComposeResult:
        yield Static(self._format_header(), classes="tool-header", id="tool-header")
        if self.tool in self.VERBOSE_TOOLS:
            classes = "tool-nested collapsed" if self.collapsed else "tool-nested"
            yield Container(classes=classes, id="tool-nested")

    def _format_args(self) -> str:
        """Format the argument string based on tool type."""
        if self.tool == "Read":
            parts = [self.params.get("path", "")]
            if self.params.get("start_line") is not None:
                parts.append(f"startLine={self.params['start_line']}")
            if self.params.get("end_line") is not None:
                parts.append(f"endLine={self.params['end_line']}")
            return ", ".join(parts)
        if self.tool == "Search":
            pattern = self.params.get("pattern", "")
            path = self.params.get("path", ".")
            return f"{pattern}, {path}"
        if "path" in self.params:
            return self.params["path"]
        return ", ".join(str(v) for v in self.params.values())

    def _format_header(self) -> str:
        args = self._format_args()
        hint = ""
        if self.tool in self.VERBOSE_TOOLS and self._output_lines:
            hint = " [dim]Ctrl+O to expand[/dim]" if self.collapsed else ""
        if self.failed:
            return f"[red]✗ {self.tool}({args})[/red]{hint}"
        status = "✓" if self.finished else "⋯"
        return f"[dim]{status} {self.tool}({args})[/dim]{hint}"

    def set_output(self, output: str) -> None:
        """Set tool output, displayed as nested lines when expanded."""
        if self.tool not in self.VERBOSE_TOOLS:
            return
        nested = self.query_one("#tool-nested", Container)
        for widget in self._output_lines:
            widget.remove()
        self._output_lines.clear()

        if not output or not output.strip():
            return

        lines = output.strip().split("\n")
        max_lines = 20
        truncated = len(lines) > max_lines
        display_lines = lines[:max_lines]

        for i, line in enumerate(display_lines):
            is_last = (i == len(display_lines) - 1) and not truncated
            prefix = "└─" if is_last else "├─"
            widget = Static(f"{prefix} {line}", classes="tool-output-line", markup=False)
            self._output_lines.append(widget)
            nested.mount(widget)

        if truncated:
            remaining = len(lines) - max_lines
            widget = Static(f"[dim]└─ ... ({remaining} more lines)[/dim]", classes="tool-output-line")
            self._output_lines.append(widget)
            nested.mount(widget)

        self.query_one("#tool-header", Static).update(self._format_header())

    def toggle_collapsed(self) -> None:
        if self.tool not in self.VERBOSE_TOOLS:
            return
        self.collapsed = not self.collapsed
        nested = self.query_one("#tool-nested", Container)
        if self.collapsed:
            nested.add_class("collapsed")
        else:
            nested.remove_class("collapsed")
        self.query_one("#tool-header", Static).update(self._format_header())

    def mark_finished(self) -> None:
        self.finished = True
        self.query_one("#tool-header", Static).update(self._format_header())

    def mark_failed(self) -> None:
        self.failed = True
        self.finished = True
        self.query_one("#tool-header", Static).update(self._format_header())
