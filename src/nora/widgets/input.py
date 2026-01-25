"""Custom input widget with markdown link handling."""

import re
from textual import events
from textual.message import Message
from textual.widgets import TextArea

LINK_PATTERN = re.compile(r'\[([^\]]+)\]\([^)]+\)')


class MarkdownInput(TextArea):
    """
    Text input that handles markdown links transparently.
    
    Links like [filename](path/to/file) are displayed as just 'filename'
    but the full path is preserved in the internal value.
    """
    
    DEFAULT_CSS = """
    MarkdownInput {
        height: auto;
        min-height: 1;
        max-height: 30;
    }
    """
    
    class Submitted(Message):
        """Message sent when input is submitted."""
        
        def __init__(self, input: "MarkdownInput", value: str) -> None:
            """
            Initialize the submitted message.
            
            Args:
                input: The input widget.
                value: The submitted value (internal format with full paths).
            """
            super().__init__()
            self.input = input
            self.value = value

    def __init__(self, placeholder: str = "", **kwargs) -> None:
        """
        Initialize the markdown input.
        
        Args:
            placeholder: Placeholder text.
            **kwargs: Additional TextArea arguments.
        """
        super().__init__(**kwargs)
        self._placeholder = placeholder
        self._internal_value = ""

    def on_mount(self) -> None:
        """Configure the text area on mount."""
        self.show_line_numbers = False

    @property
    def internal_value(self) -> str:
        """Get the internal value with full markdown links."""
        return self._internal_value

    def _internal_to_display(self, text: str) -> str:
        """Convert internal format to display format."""
        return LINK_PATTERN.sub(r'\1', text)

    def _cursor_to_internal(self, display_pos: int) -> int:
        """Convert display cursor position to internal position."""
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
        """Convert internal position to display cursor position."""
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
        """Find link ending at the given position."""
        for match in LINK_PATTERN.finditer(self._internal_value):
            if match.end() == internal_pos:
                return match.start(), match.end()
        return None

    def set_internal(self, value: str, cursor: int | None = None) -> None:
        """
        Set the internal value and update display.
        
        Args:
            value: Internal value with full markdown links.
            cursor: Optional cursor position in internal coordinates.
        """
        self._internal_value = value
        display = self._internal_to_display(value)
        self.text = display
        
        if cursor is not None:
            col = self._internal_to_cursor(cursor)
            self.cursor_location = (0, col)

    def clear(self) -> None:
        """Clear the input."""
        self._internal_value = ""
        self.text = ""

    def _sync_internal(self) -> None:
        """Sync internal value with display text changes."""
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
            insert_pos = self._cursor_to_internal(cursor - diff)
            self._internal_value = self._internal_value[:insert_pos] + inserted + self._internal_value[insert_pos:]
        elif len(new_display) < len(old_display):
            diff = len(old_display) - len(new_display)
            internal_cursor = self._cursor_to_internal(cursor)
            self._internal_value = self._internal_value[:internal_cursor] + self._internal_value[internal_cursor + diff:]

    def on_text_area_changed(self, event) -> None:
        """Handle text changes."""
        if event.text_area == self:
            self._sync_internal()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for special actions."""
        if event.key == "shift+tab":
            event.prevent_default()
            event.stop()
            self.app.action_cycle_mode()
        elif event.key == "ctrl+e":
            event.prevent_default()
            event.stop()
            self.app.action_execute_plan()
        elif event.key in ("ctrl+j", "shift+enter", "shift+return"):
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
            self.post_message(self.Submitted(self, self._internal_value))
        elif event.key == "backspace":
            internal_pos = self._cursor_to_internal(self.cursor_location[1])
            link = self._find_link_before(internal_pos)
            if link:
                event.prevent_default()
                event.stop()
                start, end = link
                self._internal_value = self._internal_value[:start] + self._internal_value[end:]
                self.set_internal(self._internal_value, start)
