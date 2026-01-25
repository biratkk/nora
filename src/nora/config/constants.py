"""Application constants and configuration values."""

from typing import Final

# Application paths
NORA_DIR_NAME: Final[str] = ".nora"
SETTINGS_FILENAME: Final[str] = "settings.json"
MODES_DIR_NAME: Final[str] = "modes"
THREADS_DIR_NAME: Final[str] = "threads"
PLANS_DIR_NAME: Final[str] = "plans"
PLUGINS_DIR_NAME: Final[str] = "plugins"

# Default model
DEFAULT_MODEL_ID: Final[str] = "us.anthropic.claude-opus-4-5-20251101-v1:0"

# Available models with display names
AVAILABLE_MODELS: Final[dict[str, str]] = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude Sonnet 4.5",
    "us.anthropic.claude-opus-4-5-20251101-v1:0": "Claude Opus 4.5",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Claude Haiku 4.5",
    "us.qwen.qwen3-coder-480b-a35b-v1:0": "Qwen3 Coder 480B",
}

# TUI constants
MODE_COLORS: Final[dict[str, str]] = {
    "vibe": "cyan",
    "plan": "yellow",
    "act": "green",
}

MODE_CYCLE: Final[list[str]] = ["vibe", "plan", "act"]

# Autocomplete
COMMANDS: Final[list[str]] = ["/new", "/switch", "/model", "/add-plugin", "/exit"]
MAX_AUTOCOMPLETE_RESULTS: Final[int] = 10

# File handling
MAX_FILE_SIZE: Final[int] = 1024 * 1024  # 1MB

# Plugin matching
PLUGIN_MATCH_THRESHOLD: Final[int] = 80
