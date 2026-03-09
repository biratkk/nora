"""Models package.

Provides both legacy Nora models and new ACP-aligned models.
Legacy imports (Thread, Message) continue to work for backward compatibility.
New code should prefer ACP models from nora.acp.models.
"""

# Legacy models (backward compat)
from nora.models.message import Message, MessageRole
from nora.models.thread import Thread, Mode
from nora.models.plugin import Plugin, validate_plugin_name
from nora.models.plan import Plan
from nora.models.settings import Settings
from nora.models.autocomplete import AutocompleteItem
from nora.models.trust_policy import TrustPolicyFile, Policy
from nora.models.mcp_config import McpServerConfig, McpConfigFile

# ACP models (new)
from nora.acp.models import (
    AcpMessage,
    MessagePart,
    Run,
    RunStatus,
    Session,
    SessionMetadata,
    AcpError,
)

__all__ = [
    # Legacy
    "Message",
    "MessageRole",
    "Thread",
    "Mode",
    "Plugin",
    "validate_plugin_name",
    "Plan",
    "Settings",
    "AutocompleteItem",
    "TrustPolicyFile",
    "Policy",
    # ACP
    "AcpMessage",
    "MessagePart",
    "Run",
    "RunStatus",
    "Session",
    "SessionMetadata",
    "AcpError",
    # MCP
    "McpServerConfig",
    "McpConfigFile",
]
