"""Switch thread modal with keyboard navigation and fuzzy search."""

from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Input
from textual.binding import Binding

from nora.models.thread import Thread
from nora.storage import list_threads
from nora.tui.utils import fuzzy_filter


class ThreadItem(Static):
    """A selectable thread item."""
    
    DEFAULT_CSS = """
    ThreadItem {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    ThreadItem.selected { background: darkgreen; }
    """
    
    def __init__(self, thread: Thread) -> None:
        self.thread = thread
        date_str = datetime.fromisoformat(thread.created).strftime("%b %d, %Y %H:%M") if thread.created else "Unknown"
        name = escape(thread.name or thread.id)
        super().__init__(f"[dim]{date_str}:[/dim] {name}")
    
    def on_click(self) -> None:
        self.screen.dismiss(self.thread)


class SwitchModal(ModalScreen[Thread | None]):
    """Modal for switching between threads with fuzzy search."""
    
    DEFAULT_CSS = """
    SwitchModal { align: center middle; }
    SwitchModal > Container {
        width: 75%;
        height: 75%;
        border: round $primary;
        background: $surface;
    }
    SwitchModal .modal-content { padding: 1 2; height: 1fr; }
    SwitchModal .modal-status { background: $surface-lighten-1; padding: 0 1; }
    SwitchModal .title { text-style: bold; margin-bottom: 1; }
    SwitchModal .search-input { margin-bottom: 1; }
    SwitchModal VerticalScroll { height: 1fr; }
    SwitchModal .no-matches { color: $text-muted; text-align: center; padding: 2; }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+c", "close", "Close"),
    ]
    
    def __init__(self) -> None:
        super().__init__()
        self.threads: list[Thread] = []
        self.filtered_threads: list[Thread] = []
        self.selected_index = 0
        self.search_query = ""
    
    def compose(self) -> ComposeResult:
        with Container():
            with Container(classes="modal-content"):
                yield Static("Switch Thread", classes="title")
                yield Input(placeholder="Type to filter...", classes="search-input", id="thread-search")
                with VerticalScroll(id="thread-list"):
                    self.threads = list_threads()
                    self.filtered_threads = self.threads.copy()
                    if not self.threads:
                        yield Static("[dim]No threads[/dim]")
                    else:
                        for i, t in enumerate(self.threads):
                            item = ThreadItem(t)
                            if i == 0:
                                item.add_class("selected")
                            yield item
            yield Static("Type to search  ↑/↓ navigate  Enter select  Esc close", classes="modal-status")

    def _get_thread_search_text(self, thread: Thread) -> str:
        """Get searchable text for a thread (name + id + all message content)."""
        parts = [thread.name or '', thread.id]
        
        # Include all message content from the thread
        for msg in thread.messages:
            if msg.content:
                parts.append(msg.content)
            if msg.result:
                parts.append(msg.result)
            if msg.tool:
                parts.append(msg.tool)
        
        return ' '.join(parts)

    def _filter_threads(self) -> None:
        """Filter threads based on current search query."""
        self.filtered_threads = fuzzy_filter(
            self.search_query,
            self.threads,
            self._get_thread_search_text
        )
        self.selected_index = 0

    async def _refresh_thread_list(self) -> None:
        """Re-render the thread list after filtering."""
        scroll = self.query_one("#thread-list", VerticalScroll)
        await scroll.remove_children()
        
        if not self.filtered_threads:
            await scroll.mount(Static("No matches\n[dim]Press Enter to clear search[/dim]", classes="no-matches"))
        else:
            for i, thread in enumerate(self.filtered_threads):
                item = ThreadItem(thread)
                if i == self.selected_index:
                    item.add_class("selected")
                await scroll.mount(item)
    
    def _update_selection(self) -> None:
        """Update visual selection highlighting."""
        if not self.filtered_threads:
            return
        
        items = list(self.query(ThreadItem))
        for i, item in enumerate(items):
            if i == self.selected_index:
                item.add_class("selected")
                item.scroll_visible()
            else:
                item.remove_class("selected")

    def on_mount(self) -> None:
        """Focus search input when modal opens."""
        self.query_one("#thread-search", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "thread-search":
            self.search_query = event.value
            self._filter_threads()
            await self._refresh_thread_list()
    
    async def on_key(self, event) -> None:
        """Handle keyboard navigation."""
        if event.key in ("up", "ctrl+p"):
            if self.filtered_threads:
                self.selected_index = (self.selected_index - 1) % len(self.filtered_threads)
                self._update_selection()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self.filtered_threads:
                self.selected_index = (self.selected_index + 1) % len(self.filtered_threads)
                self._update_selection()
            event.prevent_default()
        elif event.key == "enter":
            if not self.filtered_threads:
                # Clear search when no matches
                search_input = self.query_one("#thread-search", Input)
                search_input.value = ""
                self.search_query = ""
                self._filter_threads()
                await self._refresh_thread_list()
            elif self.filtered_threads and 0 <= self.selected_index < len(self.filtered_threads):
                self.dismiss(self.filtered_threads[self.selected_index])
            event.prevent_default()
    
    def action_close(self) -> None:
        self.dismiss(None)
