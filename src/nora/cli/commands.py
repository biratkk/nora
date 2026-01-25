"""Main CLI commands."""

from typing import Optional
import typer
from rich.console import Console

from nora.core import init_settings, load_settings, create_agent
from nora.models import Thread, Message
from nora.storage import save_thread
from nora.tui import run_tui
from nora.cli.config import config_app

app = typer.Typer(help="Nora - AI assistant powered by Claude Sonnet 4.5")
app.add_typer(config_app, name="config")
console = Console()


@app.command()
def chat(
    prompt: Optional[str] = typer.Argument(None, help="Your prompt"),
    headless: bool = typer.Option(False, "--headless", help="One-shot mode without TUI"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile name"),
):
    """Chat with Nora AI assistant."""
    effective_profile = profile or load_settings().defaultProfile
    thread = Thread.create()

    if headless:
        if not prompt:
            console.print("[red]Please provide a prompt for headless mode.[/red]")
            raise typer.Exit(1)
        agent = create_agent([], effective_profile)
        agent(prompt)
        thread.messages = [
            Message(role="user", content=prompt),
            Message(role="assistant", content=str(agent.messages[-1].get("content", ""))),
        ]
        save_thread(thread)
        return

    if prompt:
        agent = create_agent([], effective_profile)
        agent(prompt)
        thread.messages = [
            Message(role="user", content=prompt),
            Message(role="assistant", content=str(agent.messages[-1].get("content", ""))),
        ]
        save_thread(thread)

    run_tui(thread, effective_profile)


def main():
    init_settings()
    app()
