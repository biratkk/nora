"""Settings management - backward compatibility shim."""

from pathlib import Path

# Re-export from new locations
from nora.config.prompts import (
    BASE_PROMPT,
    DEFAULT_VIBE_PROMPT,
    DEFAULT_PLAN_PROMPT,
    DEFAULT_ACT_PROMPT,
    SUBAGENT_PROMPT,
)
from nora.models.settings import Settings
from nora.services.settings_service import SettingsService
from nora.repositories.settings_repository import SettingsRepository

# Path constants for backward compat
NORA_DIR = Path.home() / ".nora"
SETTINGS_FILE = NORA_DIR / "settings.json"
MODES_DIR = NORA_DIR / "modes"

# Singleton services
_settings_service = SettingsService.get_instance()


def init_settings() -> None:
    """Initialize settings directory structure."""
    _settings_service.initialize()


def load_settings() -> Settings:
    """Load settings from disk."""
    return _settings_service.load()


def save_settings(settings: Settings) -> None:
    """Save settings to disk."""
    _settings_service.save(settings)


def load_mode_prompt(mode: str) -> str | None:
    """Load a mode-specific system prompt."""
    return _settings_service.get_mode_prompt(mode)
