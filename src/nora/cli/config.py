"""Config CLI subcommands."""

from typing import Optional
import typer
from rich.console import Console

from nora.core import load_settings, save_settings

config_app = typer.Typer(help="Manage Nora configuration")
console = Console()


@config_app.command("get")
def config_get():
    """Print current settings."""
    settings = load_settings()
    for key, value in settings.model_dump(exclude_none=True).items():
        print(f"{key}={value}")


@config_app.command("set")
def config_set(
    default_profile: Optional[str] = typer.Option(None, "--defaultProfile", help="Default AWS profile"),
):
    """Update settings."""
    settings = load_settings()
    if default_profile is not None:
        settings.defaultProfile = default_profile
    save_settings(settings)
    console.print("[green]Settings updated.[/green]")
