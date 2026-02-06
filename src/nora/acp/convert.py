"""Conversion utilities between ACP messages and Strands agent format.

Bridges the gap between ACP's standard message format and the internal
Strands SDK message format (which uses toolUse/toolResult blocks).
"""

import json
from typing import Any, Optional

from nora.acp.models.message import (
    AcpMessage,
    MessagePart,
    TrajectoryMetadata,
    NanoShellMetadata,
)


def strands_to_acp_messages(strands_msgs: list[dict[str, Any]]) -> list[AcpMessage]:
    """Convert Strands SDK messages to ACP messages.

    Strands messages use:
    - {"role": "user", "content": [{"text": "..."}, {"toolResult": {...}}]}
    - {"role": "assistant", "content": [{"text": "..."}, {"toolUse": {...}}]}

    ACP messages use:
    - role "user" / "agent" with MessageParts
    - Tool calls become TrajectoryMetadata on agent message parts
    """
    acp_messages: list[AcpMessage] = []

    for msg in strands_msgs:
        role = msg.get("role", "")
        content_blocks = msg.get("content", [])

        if role == "user":
            parts = _convert_user_content(content_blocks)
            if parts:
                acp_messages.append(AcpMessage(role="user", parts=parts))

        elif role == "assistant":
            parts = _convert_assistant_content(content_blocks)
            if parts:
                acp_messages.append(AcpMessage(role="agent", parts=parts))

    return acp_messages


def _convert_user_content(content_blocks: list[dict]) -> list[MessagePart]:
    """Convert Strands user content blocks to ACP MessageParts."""
    parts: list[MessagePart] = []

    for block in content_blocks:
        if "text" in block:
            parts.append(MessagePart(content=block["text"]))
        elif "toolResult" in block:
            # Tool results from user messages — these are Strands internal
            # We skip them in ACP since tool calls are on the agent side
            pass

    return parts


def _convert_assistant_content(content_blocks: list[dict]) -> list[MessagePart]:
    """Convert Strands assistant content blocks to ACP MessageParts."""
    parts: list[MessagePart] = []

    for block in content_blocks:
        if "text" in block:
            parts.append(MessagePart(content=block["text"]))
        elif "toolUse" in block:
            tu = block["toolUse"]
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {})
            parts.append(
                MessagePart(
                    content_type="application/json",
                    content=json.dumps(tool_input),
                    metadata=TrajectoryMetadata(
                        tool_name=tool_name,
                        tool_input=tool_input,
                    ),
                )
            )

    return parts


def acp_to_strands_messages(acp_msgs: list[AcpMessage]) -> list[dict[str, Any]]:
    """Convert ACP messages to Strands SDK format.

    This produces simplified text-only messages suitable for agent initialization.
    For full fidelity (including toolUse/toolResult), use the .strands.json sidecar.
    """
    strands_messages: list[dict[str, Any]] = []

    for msg in acp_msgs:
        # Skip shell messages
        if msg.is_shell():
            continue

        if msg.role == "user":
            text = msg.get_text()
            if text:
                strands_messages.append({
                    "role": "user",
                    "content": [{"text": text}],
                })

        elif msg.role.startswith("agent"):
            text = msg.get_text()
            if text:
                strands_messages.append({
                    "role": "assistant",
                    "content": [{"text": text}],
                })

    return strands_messages


def legacy_messages_to_acp(
    messages: list[dict[str, Any]],
) -> list[AcpMessage]:
    """Convert legacy Nora Message dicts to ACP messages.

    Used for migration from old thread format. Legacy messages have:
    - {"role": "user"|"assistant"|"tool_call"|"shell", "content": "...", ...}
    """
    acp_messages: list[AcpMessage] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")

        if role == "user":
            if content:
                acp_messages.append(AcpMessage.user(content))

        elif role == "assistant":
            if content:
                acp_messages.append(AcpMessage.agent(content))

        elif role == "tool_call":
            tool = msg.get("tool", "")
            parameters = msg.get("parameters", {})
            result = msg.get("result")
            acp_messages.append(
                AcpMessage.tool_trajectory(
                    tool_name=tool,
                    tool_input=parameters,
                    tool_output=result or "",
                )
            )

        elif role == "shell":
            command = content or ""
            output = msg.get("output", "")
            acp_messages.append(AcpMessage.shell(command, output))

    return acp_messages
