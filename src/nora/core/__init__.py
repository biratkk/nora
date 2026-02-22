"""Core package - backward compatibility shim."""

from nora.config.constants import AVAILABLE_MODELS as MODEL_NAMES
from nora.config.constants import DEFAULT_MODEL_ID as MODEL_ID
from nora.config.prompts import (
    BASE_PROMPT,
    DEFAULT_EDIT_PROMPT,
    DEFAULT_PLAN_PROMPT,
    DEFAULT_VIBE_PROMPT,
    SUBAGENT_PROMPT,
)
from nora.models.settings import Settings
from nora.services.agent_service import AgentService, CancellationHook
from nora.services.settings_service import SettingsService

# Backward compat alias
DEFAULT_ACT_PROMPT = DEFAULT_EDIT_PROMPT

# Singleton services for backward compat
_settings_service = SettingsService.get_instance()
_agent_service = AgentService()


def init_settings() -> None:
    """Initialize settings directory structure."""
    _settings_service.initialize()


def load_settings() -> Settings:
    """Load settings from disk."""
    return _settings_service.load()


def save_settings(settings: Settings) -> None:
    """Save settings to disk."""
    _settings_service.save(settings)


def create_agent(messages, profile=None, mode="vibe", model_id=None, hooks=None):
    """Create an agent instance."""
    return _agent_service.create_agent(messages, profile, mode, model_id, hooks)


def get_model_name(model_id=None) -> str:
    """Get display name for a model."""
    return AgentService.get_model_name(model_id)


__all__ = [
    "Settings",
    "init_settings",
    "load_settings", 
    "save_settings",
    "create_agent",
    "MODEL_ID",
    "get_model_name",
    "CancellationHook",
    "MODEL_NAMES",
    "BASE_PROMPT",
    "DEFAULT_VIBE_PROMPT",
    "DEFAULT_PLAN_PROMPT",
    "DEFAULT_EDIT_PROMPT",
    "DEFAULT_ACT_PROMPT",
    "SUBAGENT_PROMPT",
]
