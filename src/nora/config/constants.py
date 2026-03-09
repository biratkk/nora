"""Application constants and configuration values."""

from typing import Final

# Application paths
NORA_DIR_NAME: Final[str] = ".nora"
SETTINGS_FILENAME: Final[str] = "settings.json"
MODES_DIR_NAME: Final[str] = "modes"
THREADS_DIR_NAME: Final[str] = "threads"
SESSIONS_DIR_NAME: Final[str] = "sessions"
PLANS_DIR_NAME: Final[str] = "plans"
PLUGINS_DIR_NAME: Final[str] = "plugins"
MCPS_FILENAME: Final[str] = "mcps.json"

# Default model
DEFAULT_MODEL_ID: Final[str] = "us.anthropic.claude-opus-4-6-v1"

# Available models with display names
AVAILABLE_MODELS: Final[dict[str, str]] = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude Sonnet 4.5",
    "us.anthropic.claude-opus-4-5-20251101-v1:0": "Claude Opus 4.5",
    "us.anthropic.claude-opus-4-6-v1": "Claude Opus 4.6",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "Claude Haiku 4.5",
    "us.qwen.qwen3-coder-480b-a35b-v1:0": "Qwen3 Coder 480B",
}

# Context window sizes per model (in tokens)
CONTEXT_WINDOWS: Final[dict[str, int]] = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": 200_000,
    "us.anthropic.claude-opus-4-5-20251101-v1:0": 200_000,
    "us.anthropic.claude-opus-4-6-v1": 200_000,
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": 200_000,
    "us.qwen.qwen3-coder-480b-a35b-v1:0": 130_000,
}

# Default context window for unknown models
DEFAULT_CONTEXT_WINDOW: Final[int] = 200_000

# TUI constants
MODE_COLORS: Final[dict[str, str]] = {
    "vibe": "cyan",
    "plan": "yellow",
    "edit": "green",
}

MODE_CYCLE: Final[list[str]] = ["vibe", "plan", "edit"]

# Autocomplete
COMMANDS: Final[list[str]] = ["/new", "/switch", "/model", "/exit", "/add-local-mcp", "/add-global-mcp", "/mcp"]
MAX_AUTOCOMPLETE_RESULTS: Final[int] = 10

# File handling
MAX_FILE_SIZE: Final[int] = 1024 * 1024  # 1MB

# Plugin matching
PLUGIN_MATCH_THRESHOLD: Final[int] = 80
