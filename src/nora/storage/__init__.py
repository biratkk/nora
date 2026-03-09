"""Storage package - backward compatibility shim.

Legacy functions wrapping ThreadService are preserved for any external
consumers. New code should use SessionService / RunService directly.
"""

from nora.models.plan import Plan
from nora.models.plugin import Plugin, validate_plugin_name
from nora.repositories.plugin_repository import PluginRepository
from nora.services.plan_service import PlanService
from nora.services.plugin_service import PluginService
from nora.services.session_service import SessionService

# Services for backward compat
_session_service = SessionService()
_plan_service = PlanService()
_plugin_service = PluginService()
_plugin_repo = PluginRepository()


def list_sessions():
    """List all sessions."""
    return _session_service.list_all()


# Legacy aliases
def list_threads():
    """List all sessions (legacy alias)."""
    return list_sessions()


def save_plan(name: str, content: str) -> "Plan":
    """Save a plan to disk."""
    return _plan_service.create(name, content)


def load_plugins():
    """Load all plugins."""
    return _plugin_service.load_all()


def save_plugin(plugin: Plugin):
    """Save a plugin to disk."""
    return _plugin_repo.save(plugin)


__all__ = [
    "list_sessions",
    "list_threads",
    "save_plan",
    "Plan",
    "Plugin",
    "load_plugins",
    "save_plugin",
    "validate_plugin_name",
]
