"""Custom input widget with markdown link handling."""

import re
from textual import events
from textual.message import Message
from textual.widgets import TextArea

LINK_PATTERN = re.compile(r'\[([^\]]+)\]\([^)]+\)')


class MarkdownInput(TextArea):
    DEFAULT_CSS = """
    MarkdownInput {
        height: auto;
        min-height: 1;
        max-height: 30;
    }
    """

    class ShellModeChanged(Message):
        """Posted when shell mode changes."""
        def __init__(self, shell_mode: bool) -> None:
            super().__init__()
            self.shell_mode = shell_mode

    def __init__(self, placeholder: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._placeholder = placeholder
        self._internal_value = ""
        self._shell_mode = False

    def on_mount(self) -> None:
        self.show_line_numbers = False

    @property
    def internal_value(self) -> str:
        return self._internal_value

    @property
    def is_shell_mode(self) -> bool:
        """Check if input starts with ! (shell passthrough mode)."""
        return self._internal_value.startswith("!")

    def _update_shell_mode_style(self) -> None:
        """Update visual style based on shell mode."""
        is_shell = self.is_shell_mode
        if is_shell and not self._shell_mode:
            self._shell_mode = True
            self.post_message(self.ShellModeChanged(True))
        elif not is_shell and self._shell_mode:
            self._shell_mode = False
            self.post_message(self.ShellModeChanged(False))

    def _internal_to_display(self, text: str) -> str:
        return LINK_PATTERN.sub(r'\1', text)

    def _cursor_to_internal(self, display_pos: int) -> int:
        internal_pos = 0
        display_idx = 0
        while display_idx < display_pos and internal_pos < len(self._internal_value):
            match = LINK_PATTERN.match(self._internal_value, internal_pos)
            if match:
                display_len = len(match.group(1))
                if display_idx + display_len <= display_pos:
                    display_idx += display_len
                    internal_pos = match.end()
                else:
                    internal_pos += (display_pos - display_idx)
                    display_idx = display_pos
            else:
                internal_pos += 1
                display_idx += 1
        return internal_pos

    def _internal_to_cursor(self, internal_pos: int) -> int:
        display_pos = 0
        idx = 0
        while idx < internal_pos:
            match = LINK_PATTERN.match(self._internal_value, idx)
            if match and match.end() <= internal_pos:
                display_pos += len(match.group(1))
                idx = match.end()
            elif match and idx < internal_pos <= match.end():
                display_pos += len(match.group(1))
                idx = match.end()
                break
            else:
                display_pos += 1
                idx += 1
        return display_pos

    def _find_link_before(self, internal_pos: int) -> tuple[int, int] | None:
        for match in LINK_PATTERN.finditer(self._internal_value):
            if match.end() == internal_pos:
                return match.start(), match.end()
        return None

    def set_internal(self, value: str, cursor: int | None = None) -> None:
        self._internal_value = value
        display = self._internal_to_display(value)
        self.text = display
        if cursor is not None:
            col = self._internal_to_cursor(cursor)
            self.cursor_location = (0, col)

    def clear(self) -> None:
        self._internal_value = ""
        self.text = ""

    def _sync_internal(self) -> None:
        old_display = self._internal_to_display(self._internal_value)
        new_display = self.text
        if old_display == new_display:
            return
        if not LINK_PATTERN.search(self._internal_value):
            self._internal_value = new_display
            return
        cursor = self.cursor_location[1]
        if len(new_display) > len(old_display):
            diff = len(new_display) - len(old_display)
            inserted = new_display[cursor - diff:cursor]
            # Convert the position BEFORE the inserted text
            insert_pos = self._cursor_to_internal(cursor - diff)
            self._internal_value = self._internal_value[:insert_pos] + inserted + self._internal_value[insert_pos:]
        elif len(new_display) < len(old_display):
            diff = len(old_display) - len(new_display)
            internal_cursor = self._cursor_to_internal(cursor)
            self._internal_value = self._internal_value[:internal_cursor] + self._internal_value[internal_cursor + diff:]

    def on_text_area_changed(self, event) -> None:
        if event.text_area == self:
            self._sync_internal()
            self._update_shell_mode_style()

    def on_key(self, event: events.Key) -> None:
        if event.key == "shift+tab":
            event.prevent_default()
            event.stop()
            self.app.action_cycle_mode()
        elif event.key == "ctrl+e":
            event.prevent_default()
            event.stop()
            self.app.action_execute_plan()
        elif event.key in ("ctrl+j", "shift+enter", "shift+return"):
            # Insert newline
            self.insert("\n")
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            ac = self.app.query_one("#autocomplete")
            if ac.has_class("visible"):
                event.prevent_default()
                return
            event.prevent_default()
            event.stop()
            self.post_message(self.Submitted(self, self._internal_value, self.is_shell_mode))
        elif event.key == "backspace":
            internal_pos = self._cursor_to_internal(self.cursor_location[1])
            link = self._find_link_before(internal_pos)
            if link:
                event.prevent_default()
                event.stop()
                start, end = link
                self._internal_value = self._internal_value[:start] + self._internal_value[end:]
                self.set_internal(self._internal_value, start)
                return

    class Submitted(Message):
        def __init__(self, input: "MarkdownInput", value: str, is_shell: bool = False) -> None:
            super().__init__()
            self.input = input
            self.value = value
            self.is_shell = is_shell
