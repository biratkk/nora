"""Switch session modal with keyboard navigation and fuzzy search."""

from datetime import datetime
from typing import Optional

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Input
from textual.binding import Binding

from nora.acp.models.session import Session
from nora.services.session_service import SessionService
from nora.utils.fuzzy import fuzzy_filter


class SessionItem(Static):
    """A selectable session item."""
    
    DEFAULT_CSS = """
    SessionItem {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    SessionItem.selected { background: darkgreen; }
    """
    
    def __init__(self, session: Session) -> None:
        self.session = session
        date_str = session.created_at.strftime("%b %d, %Y %H:%M") if session.created_at else "Unknown"
        name = escape(session.name or str(session.id)[:8])
        super().__init__(f"[dim]{date_str}:[/dim] {name}")
    
    def on_click(self) -> None:
        self.screen.dismiss(self.session)


class SwitchModal(ModalScreen[Session | None]):
    """Modal for switching between sessions with fuzzy search."""
    
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
        self._session_service = SessionService()
        self.sessions: list[Session] = []
        self.filtered_sessions: list[Session] = []
        self.selected_index = 0
        self.search_query = ""
        self._search_text_cache: dict[str, str] = {}
    
    def compose(self) -> ComposeResult:
        with Container():
            with Container(classes="modal-content"):
                yield Static("Switch Session", classes="title")
                yield Input(placeholder="Type to filter...", classes="search-input", id="session-search")
                with VerticalScroll(id="session-list"):
                    self.sessions = self._session_service.list_all()
                    self.filtered_sessions = self.sessions.copy()
                    # Pre-cache search text for all sessions to avoid disk reads on every keystroke
                    self._search_text_cache = {
                        str(s.id): self._build_session_search_text(s)
                        for s in self.sessions
                    }
                    if not self.sessions:
                        yield Static("[dim]No sessions[/dim]")
                    else:
                        for i, s in enumerate(self.sessions):
                            item = SessionItem(s)
                            if i == 0:
                                item.add_class("selected")
                            yield item
            yield Static("Type to search  ↑/↓ navigate  Enter select  Esc close", classes="modal-status")

    def _build_session_search_text(self, session: Session) -> str:
        """Build searchable text for a session (name + id + run content). Reads from disk."""
        parts = [session.name or '', str(session.id)]
        
        try:
            history = self._session_service.get_history(session)
            for msg in history:
                text = msg.get_text()
                if text:
                    parts.append(text)
        except Exception:
            pass
        
        return ' '.join(parts)

    def _get_session_search_text(self, session: Session) -> str:
        """Get searchable text for a session, using cache."""
        session_key = str(session.id)
        if session_key in self._search_text_cache:
            return self._search_text_cache[session_key]
        # Fallback: build and cache (shouldn't normally happen)
        text = self._build_session_search_text(session)
        self._search_text_cache[session_key] = text
        return text

    def _filter_sessions(self) -> None:
        """Filter sessions based on current search query."""
        self.filtered_sessions = fuzzy_filter(
            self.search_query,
            self.sessions,
            self._get_session_search_text
        )
        self.selected_index = 0

    async def _refresh_session_list(self) -> None:
        """Re-render the session list after filtering."""
        scroll = self.query_one("#session-list", VerticalScroll)
        await scroll.remove_children()
        
        if not self.filtered_sessions:
            await scroll.mount(Static("No matches\n[dim]Press Enter to clear search[/dim]", classes="no-matches"))
        else:
            for i, session in enumerate(self.filtered_sessions):
                item = SessionItem(session)
                if i == self.selected_index:
                    item.add_class("selected")
                await scroll.mount(item)
    
    def _update_selection(self) -> None:
        """Update visual selection highlighting."""
        if not self.filtered_sessions:
            return
        
        items = list(self.query(SessionItem))
        for i, item in enumerate(items):
            if i == self.selected_index:
                item.add_class("selected")
                item.scroll_visible()
            else:
                item.remove_class("selected")

    def on_mount(self) -> None:
        """Focus search input when modal opens."""
        self.query_one("#session-search", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "session-search":
            self.search_query = event.value
            self._filter_sessions()
            await self._refresh_session_list()
    
    async def on_key(self, event) -> None:
        """Handle keyboard navigation."""
        if event.key in ("up", "ctrl+p"):
            if self.filtered_sessions:
                self.selected_index = (self.selected_index - 1) % len(self.filtered_sessions)
                self._update_selection()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self.filtered_sessions:
                self.selected_index = (self.selected_index + 1) % len(self.filtered_sessions)
                self._update_selection()
            event.prevent_default()
        elif event.key == "enter":
            if not self.filtered_sessions:
                # Clear search when no matches
                search_input = self.query_one("#session-search", Input)
                search_input.value = ""
                self.search_query = ""
                self._filter_sessions()
                await self._refresh_session_list()
            elif self.filtered_sessions and 0 <= self.selected_index < len(self.filtered_sessions):
                self.dismiss(self.filtered_sessions[self.selected_index])
            event.prevent_default()
    
    def action_close(self) -> None:
        self.dismiss(None)
