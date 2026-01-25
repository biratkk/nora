"""TUI command execution."""

from textual.widgets import Static
from textual.containers import VerticalScroll

from nora.storage import list_threads


def exec_threads(chat: VerticalScroll) -> None:
    threads = list_threads()
    if not threads:
        chat.mount(Static("[dim]No threads found.[/dim]"))
    else:
        lines = ["[bold]Threads:[/bold]"]
        for t in threads:
            lines.append(f"  {t.id} - {t.name} ({t.updated[:16]})")
        chat.mount(Static("\n".join(lines)))
    chat.scroll_end()
