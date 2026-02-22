"""Plugin management tools for Nora."""

from strands import tool
from strands.types.tools import ToolContext

from nora.models.plugin import Plugin, validate_plugin_name
from nora.services.plugin_service import PluginService


# Shared service instance for all plugin tools
_plugin_service = PluginService()


@tool(name="ReadPlugin")
def read_plugin(name: str) -> str:
    """Read a plugin's full content by name.

    Args:
        name: The plugin name (e.g. "frontend-design")
    """
    plugin = _plugin_service.load(name)
    if plugin is None:
        return f"Plugin '{name}' not found."
    return plugin.to_markdown()


@tool(name="WritePlugin", context=True)
def write_plugin(
    tool_context: ToolContext,
    name: str,
    instructions: str,
) -> str:
    """Create a new plugin. Description and keywords are auto-generated.

    IMPORTANT: Before calling this tool, ensure the user has fully clarified:
    1. The plugin's purpose and what behavior it should add
    2. The complete instructions they want included

    Do NOT create a plugin based on a vague request. Ask follow-up questions until
    the user's intent is clear and confirmed. Only call this tool once you have
    everything needed to write the final instructions.

    Notes:
    - Keywords are auto-generated as comma-separated single words (e.g. "animation, typography, layout"),
      not multi-word phrases. They are used for search/discovery only and do not control when
      the plugin is active.

    Args:
        name: Unique plugin name (no spaces or slashes)
        instructions: The plugin instructions to inject when activated
    """
    is_valid, error = validate_plugin_name(name)
    if not is_valid:
        return f"Invalid plugin name: {error}"

    if _plugin_service.load(name) is not None:
        return f"Plugin '{name}' already exists. Use EditPlugin to update it."

    # Get AWS profile from invocation state for the metadata LLM call
    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    profile = invocation_state.get("profile")

    description, keywords = PluginService.generate_metadata(name, instructions, profile)

    plugin = Plugin(
        name=name,
        description=description,
        keywords=keywords,
        instructions=instructions,
    )
    path = _plugin_service.save(plugin)
    return f"Plugin '{name}' created at {path.name}"


@tool(name="EditPlugin", context=True)
def edit_plugin(
    tool_context: ToolContext,
    name: str,
    instructions: str | None = None,
) -> str:
    """Edit an existing plugin. Only provided fields are updated.

    If instructions change, description and keywords are regenerated automatically.

    Args:
        name: The plugin name to edit
        instructions: New instructions (omit to keep current)
    """
    existing = _plugin_service.load(name)
    if existing is None:
        return f"Plugin '{name}' not found."

    if instructions is None:
        return "Nothing to update — provide at least one field to change."

    new_instructions = instructions
    new_description = existing.description
    new_keywords = existing.keywords

    # Regenerate metadata only when instructions actually changed
    if instructions != existing.instructions:
        invocation_state = getattr(tool_context, "invocation_state", {}) or {}
        profile = invocation_state.get("profile")
        new_description, new_keywords = PluginService.generate_metadata(
            name, new_instructions, profile
        )

    updated = Plugin(
        name=name,
        description=new_description,
        keywords=new_keywords,
        instructions=new_instructions,
    )
    _plugin_service.save(updated)

    changed: list[str] = []
    if instructions != existing.instructions:
        changed.append("instructions (metadata regenerated)")
    return f"Plugin '{name}' updated: {', '.join(changed)}"


@tool(name="DeletePlugin")
def delete_plugin(name: str) -> str:
    """Delete a plugin by name.

    Args:
        name: The plugin name to delete
    """
    deleted = _plugin_service.delete(name)
    if deleted:
        return f"Plugin '{name}' deleted."
    return f"Plugin '{name}' not found."


@tool(name="SearchPlugin")
def search_plugin(keyword: str) -> str:
    """Search plugins by keyword using fuzzy matching.

    Args:
        keyword: Keyword to search for across all plugin keywords
    """
    results = _plugin_service.search_by_keyword(keyword)
    if not results:
        return f"No plugins found matching '{keyword}'"

    lines = [f"Found {len(results)} matching plugin(s):", ""]
    for plugin, score in results:
        desc = plugin.description or "(no description)"
        lines.append(f"- {plugin.name} (score: {score}): {desc}")
    return "\n".join(lines)
