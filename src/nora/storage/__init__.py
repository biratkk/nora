"""Storage package - backward compatibility shim."""

from nora.models.plan import Plan
from nora.models.plugin import Plugin, validate_plugin_name
from nora.repositories.plugin_repository import PluginRepository
from nora.services.plan_service import PlanService
from nora.services.plugin_service import PluginService
from nora.services.thread_service import ThreadService

# Services for backward compat
_thread_service = ThreadService()
_plan_service = PlanService()
_plugin_service = PluginService()
_plugin_repo = PluginRepository()


def save_thread(thread) -> None:
    """Save a thread to disk."""
    _thread_service.save(thread)


def load_thread(thread_id: str):
    """Load a thread by ID."""
    return _thread_service.load(thread_id)


def list_threads():
    """List all threads."""
    return _thread_service.list_all()


def save_plan(thread_id: str, content: str) -> Plan:
    """Save a plan to disk."""
    return _plan_service._repository.save(thread_id, content)


def load_plugins(startup_only: bool = True):
    """Load all plugins."""
    return _plugin_service.load_all(startup_only)


def save_plugin(plugin: Plugin):
    """Save a plugin to disk."""
    return _plugin_repo.save(plugin)


__all__ = [
    "save_thread",
    "load_thread",
    "list_threads",
    "save_plan",
    "Plan",
    "Plugin",
    "load_plugins",
    "save_plugin",
    "validate_plugin_name",
]
