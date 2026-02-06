"""TUI command execution."""

from textual.widgets import Static
from textual.containers import VerticalScroll

from nora.services.session_service import SessionService


def exec_sessions(chat: VerticalScroll) -> None:
    """List all sessions in the chat scroll area."""
    session_service = SessionService()
    sessions = session_service.list_all()
    if not sessions:
        chat.mount(Static("[dim]No sessions found.[/dim]"))
    else:
        lines = ["[bold]Sessions:[/bold]"]
        for s in sessions:
            updated = s.metadata.updated_at.strftime("%Y-%m-%d %H:%M") if s.metadata.updated_at else "Unknown"
            lines.append(f"  {str(s.id)[:8]} - {s.name} ({updated})")
        chat.mount(Static("\n".join(lines)))
    chat.scroll_end()


# Backward compat alias
exec_threads = exec_sessions
