"""Config CLI subcommands."""

from typing import Optional

import typer
from rich.console import Console

from nora.services.settings_service import SettingsService

config_app = typer.Typer(help="Manage Nora configuration")
console = Console()


@config_app.command("get")
def config_get() -> None:
    """Print current settings."""
    settings = SettingsService.get_instance().load()
    for key, value in settings.model_dump(exclude_none=True).items():
        print(f"{key}={value}")


@config_app.command("set")
def config_set(
    default_profile: Optional[str] = typer.Option(
        None, 
        "--defaultProfile", 
        help="Default AWS profile"
    ),
) -> None:
    """Update settings."""
    service = SettingsService.get_instance()
    
    if default_profile is not None:
        service.update(defaultProfile=default_profile)
    
    console.print("[green]Settings updated.[/green]")
