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
    from nora.acp.models.session import Session
    from nora.acp.models.message import AcpMessage
    from nora.services.settings_service import SettingsService
    from nora.services.session_service import SessionService
    from nora.services.run_service import RunService
    from nora.services.agent_service import AgentService
    
    settings_service = SettingsService.get_instance()
    session_service = SessionService()
    run_service = RunService()
    agent_service = AgentService()
    
    settings = settings_service.load()
    effective_profile = profile or settings.defaultProfile
    session = Session.create()

    if headless:
        if not prompt:
            Console().print("[red]Please provide a prompt for headless mode.[/red]")
            raise typer.Exit(1)
        
        agent = agent_service.create_agent([], effective_profile)
        agent(prompt)
        
        # Create and save a Run with ACP messages
        input_msg = AcpMessage.user(prompt)
        run = run_service.create("nora", [input_msg], session.id)
        run_service.start(run)
        
        # Extract agent response
        last_msg = agent.messages[-1] if agent.messages else {}
        response_text = ""
        for block in last_msg.get("content", []):
            if "text" in block:
                response_text += block["text"]
        
        output_msg = AcpMessage.agent(response_text) if response_text else AcpMessage.agent("")
        run_service.complete(run, [output_msg])
        run_service.save(run, list(agent.messages))
        
        session.generate_name(prompt)
        session_service.save(session)
        return

    if prompt:
        agent = agent_service.create_agent([], effective_profile)
        agent(prompt)
        
        # Create and save a Run with ACP messages
        input_msg = AcpMessage.user(prompt)
        run = run_service.create("nora", [input_msg], session.id)
        run_service.start(run)
        
        # Extract agent response
        last_msg = agent.messages[-1] if agent.messages else {}
        response_text = ""
        for block in last_msg.get("content", []):
            if "text" in block:
                response_text += block["text"]
        
        output_msg = AcpMessage.agent(response_text) if response_text else AcpMessage.agent("")
        run_service.complete(run, [output_msg])
        run_service.save(run, list(agent.messages))
        
        session.generate_name(prompt)
        session_service.save(session)

    from nora.tui import run_tui
    run_tui(session, effective_profile)


@app.command()
def acp(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile name"),
) -> None:
    """Start the ACP (Agent Communication Protocol) server.

    Exposes Nora as an ACP-compliant agent accessible via REST API.
    Other ACP clients can discover and interact with Nora at:

        GET  /ping                        - Health check
        GET  /agents                      - Discover available agents
        GET  /agents/{name}               - Get agent manifest
        POST /runs                        - Create a new run
        GET  /runs/{run_id}               - Get run status
        GET  /runs/{run_id}/events        - Stream run events (SSE)
        POST /runs/{run_id}               - Resume an awaiting run
        POST /runs/{run_id}/cancel        - Cancel a run
        GET  /sessions                    - List all sessions
        POST /sessions                    - Create a new session
        GET  /sessions/{session_id}       - Get session details
        GET  /sessions/{session_id}/runs  - List runs for a session

    Open index.html in a browser to view the dashboard UI.

    See: https://agentcommunicationprotocol.dev
    """
    import uvicorn
    from nora.acp.server import create_app

    console = Console()
    console.print(f"\n[bold cyan]🚀 Nora ACP Server[/bold cyan]")
    console.print(f"   Agent Communication Protocol v0.2.0")
    console.print(f"   Listening on [bold]http://{host}:{port}[/bold]")
    console.print(f"   Agent manifest: [bold]http://{host}:{port}/agents/nora[/bold]")
    console.print(f"   Health check:   [bold]http://{host}:{port}/ping[/bold]")
    console.print(f"   Dashboard:      [bold]open index.html in browser[/bold]")
    console.print()

    app = create_app(profile=profile)
    uvicorn.run(app, host=host, port=port, log_level="info")


@app.command()
def manifest() -> None:
    """Print Nora's ACP agent manifest as JSON."""
    from nora.acp.models.agent_manifest import get_nora_manifest

    console = Console()
    manifest = get_nora_manifest()
    console.print_json(manifest.model_dump_json(indent=2))


@app.command()
def migrate() -> None:
    """Migrate legacy thread files to ACP session format.

    Converts $CWD/.nora/threads/thread_*.json files to
    $CWD/.nora/sessions/<uuid>/ directory structure.
    """
    from nora.acp.migrate import migrate_threads

    console = Console()
    console.print("[bold]Migrating legacy threads to ACP sessions...[/bold]")
    stats = migrate_threads()
    console.print(f"  [green]✓[/green] Migrated: {stats['migrated']}")
    console.print(f"  [yellow]⚠[/yellow] Skipped:  {stats['skipped']}")
    console.print(f"  [red]✗[/red] Errors:   {stats['errors']}")
    if stats['migrated'] > 0:
        console.print(f"\n  Sessions stored in [bold].nora/sessions/[/bold]")
        console.print(f"  Original threads preserved in [bold].nora/threads/[/bold]")


def main() -> None:
    """Main entry point."""
    from nora.services.settings_service import SettingsService
    SettingsService.get_instance().initialize()
    app()
