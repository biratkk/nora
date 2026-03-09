"""Plan management tools for Nora."""

import logging
import re
from pathlib import Path

import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from strands.types.tools import ToolContext

from nora.config.constants import NORA_DIR_NAME, PLANS_DIR_NAME

logger = logging.getLogger(__name__)

_PLANS_DIR = Path.cwd() / NORA_DIR_NAME / PLANS_DIR_NAME
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z][a-z0-9]*){2}$")


def _plans_dir() -> Path:
    """Get the plans directory, creating it if needed."""
    _PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return _PLANS_DIR


def _plan_path(name: str) -> Path:
    """Resolve the file path for a plan name."""
    return _plans_dir() / f"{name}.md"


def _validate_plan_name(name: str) -> tuple[bool, str]:
    """Validate a plan name is exactly 3 lowercase hyphenated words.

    Returns:
        (is_valid, error_message)
    """
    if not _NAME_PATTERN.match(name):
        return False, (
            f"Invalid plan name '{name}'. "
            "Must be exactly 3 lowercase hyphenated words (e.g., 'auth-session-refactor')."
        )
    return True, ""


def generate_plan_name(content: str, profile: str | None = None) -> str:
    """Generate a 3-word hyphenated plan name from content using an LLM.

    Falls back to extracting words from content if the LLM call fails.

    Args:
        content: Plan content to summarize.
        profile: Optional AWS profile name.

    Returns:
        A name like 'auth-session-refactor'.
    """
    try:
        kwargs = {"model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"}
        if profile:
            kwargs["boto_session"] = boto3.Session(profile_name=profile)
        model = BedrockModel(**kwargs)

        prompt = (
            "Given this plan content, generate exactly 3 lowercase words that "
            "summarize the plan's purpose. Return ONLY the 3 words separated by "
            "hyphens, nothing else.\n\n"
            "Rules:\n"
            "- Exactly 3 words\n"
            "- All lowercase\n"
            "- Letters and numbers only (no special characters)\n"
            "- Separated by hyphens\n"
            "- Be specific and descriptive\n\n"
            "Examples: auth-session-refactor, dark-mode-toggle, api-rate-limiting\n\n"
            f"Plan content:\n{content[:2000]}"
        )

        agent = Agent(
            model=model,
            tools=[],
            system_prompt=(
                "You generate short identifiers for plans. "
                "Respond with exactly 3 hyphen-separated lowercase words. "
                "Nothing else."
            ),
        )

        result = agent(prompt)
        name = str(result).strip().lower()

        # Clean up any extra whitespace or punctuation
        name = re.sub(r"[^a-z0-9-]", "", name)

        if _NAME_PATTERN.match(name):
            return name

        logger.warning("LLM returned invalid plan name '%s', using fallback", name)
    except Exception:
        logger.warning("LLM plan name generation failed, using fallback", exc_info=True)

    return _fallback_plan_name(content)


def _fallback_plan_name(content: str) -> str:
    """Generate a plan name from content without LLM.

    Extracts the first 3 alphabetic words from the content.
    """
    clean = re.sub(r"[^a-z0-9\s]", "", content.lower())
    words = [w for w in clean.split() if w.isalpha() and len(w) > 1][:3]
    if len(words) < 3:
        words = (words + ["plan", "draft", "spec"])[:3]
    return "-".join(words)


@tool(name="CreatePlan", context=True)
def create_plan(tool_context: ToolContext, content: str) -> str:
    """Create a new plan. An auto-generated 3-word name is assigned.

    Plans are saved as markdown files in CWD/.nora/plans/<name>.md.
    The name is generated from the plan content by an LLM.

    Args:
        content: The full plan content in markdown (freeform)
    """
    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    profile = invocation_state.get("profile")

    name = generate_plan_name(content, profile)
    path = _plan_path(name)

    if path.exists():
        return (
            f"Plan name '{name}' already exists. "
            "Please call CreatePlan again — a different name will be generated."
        )

    path.write_text(content)
    return f"Plan '{name}' created at .nora/plans/{name}.md"


@tool(name="ReadPlan")
def read_plan(name: str) -> str:
    """Read a plan's full content by name.

    Args:
        name: The plan name (e.g., 'auth-session-refactor')
    """
    path = _plan_path(name)

    if path.exists():
        return path.read_text()

    # Try legacy timestamp-named plans (e.g., '20260212_110113-description')
    legacy_dir = _plans_dir()
    for legacy_path in legacy_dir.glob(f"{name}*.md"):
        return legacy_path.read_text()

    # Also try if name matches a legacy file stem exactly
    exact_path = legacy_dir / f"{name}.md"
    if exact_path.exists():
        return exact_path.read_text()

    return f"Plan '{name}' not found."


@tool(name="ExecutePlan", context=True)
def execute_plan(tool_context: ToolContext, name: str) -> str:
    """Execute a plan by switching to edit mode and implementing it.

    This interrupts the current conversation to switch to edit mode,
    then sends the plan for implementation. Use after creating or reading
    a plan when the user wants to execute it.

    Args:
        name: The plan name to execute (e.g., 'auth-session-refactor')
    """
    path = _plan_path(name)
    if not path.exists():
        return f"Plan '{name}' not found. Use ReadPlan to check available plans."

    return tool_context.interrupt("execute-plan", reason={"plan_name": name})
