"""Main CLI commands."""

from typing import Optional

import typer
from rich.console import Console

from nora.cli.config import config_app

app = typer.Typer(help="Nora - AI assistant powered by Claude")
app.add_typer(config_app, name="config")
console = Console


@app.command()
def chat(
    prompt: Optional[str] = typer.Argument(None, help="Your prompt"),
    headless: bool = typer.Option(False, "--headless", help="One-shot mode without TUI"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile name"),
) -> None:
    """Chat with Nora AI assistant."""
    from nora.models.thread import Thread
    from nora.models.message import Message
    from nora.services.settings_service import SettingsService
    from nora.services.thread_service import ThreadService
    from nora.services.agent_service import AgentService
    
    settings_service = SettingsService.get_instance()
    thread_service = ThreadService()
    agent_service = AgentService()
    
    settings = settings_service.load()
    effective_profile = profile or settings.defaultProfile
    thread = Thread.create()

    if headless:
        if not prompt:
            Console().print("[red]Please provide a prompt for headless mode.[/red]")
            raise typer.Exit(1)
        
        agent = agent_service.create_agent([], effective_profile)
        agent(prompt)
        
        thread_service.add_user_message(thread, prompt)
        thread_service.add_assistant_message(
            thread, 
            str(agent.messages[-1].get("content", ""))
        )
        thread_service.save(thread)
        return

    if prompt:
        agent = agent_service.create_agent([], effective_profile)
        agent(prompt)
        
        thread_service.add_user_message(thread, prompt)
        thread_service.add_assistant_message(
            thread, 
            str(agent.messages[-1].get("content", ""))
        )
        thread_service.save(thread)

    from nora.tui import run_tui
    run_tui(thread, effective_profile)


def main() -> None:
    """Main entry point."""
    from nora.services.settings_service import SettingsService
    SettingsService.get_instance().initialize()
    app()
