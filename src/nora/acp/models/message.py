"""Nora internal Message and MessagePart models.

Used for internal persistence of conversation history (session runs).
This is NOT the ACP wire format — the JSON-RPC ACP protocol uses
ContentBlock (type/text) for prompts and session/update notifications.
"""

import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# --- Metadata types ---

class CitationMetadata(BaseModel):
    """Metadata for citation references in message parts."""

    kind: Literal["citation"] = "citation"
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class TrajectoryMetadata(BaseModel):
    """Metadata for tool call trajectory in message parts."""

    kind: Literal["trajectory"] = "trajectory"
    message: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_output: Optional[dict[str, Any]] = None


class NanoShellMetadata(BaseModel):
    """Nora-specific metadata for shell passthrough commands.

    This is a Nora extension not part of the ACP core spec.
    """

    kind: Literal["nora:shell"] = "nora:shell"
    exit_code: Optional[int] = None
    output: Optional[str] = None


# Discriminated union for metadata
PartMetadata = Annotated[
    Union[CitationMetadata, TrajectoryMetadata, NanoShellMetadata],
    Field(discriminator="kind"),
]


# --- MessagePart ---

class MessagePart(BaseModel):
    """A single part of an ACP message.

    Parts are the atomic content units within a message. Each part has a MIME
    type and either inline content or a URL reference. Parts with a `name`
    field are considered Artifacts (named outputs like files or citations).
    """

    content_type: str = Field(default="text/plain", description="MIME type of the content")
    content: Optional[str] = Field(default=None, description="Inline content (mutually exclusive with content_url)")
    content_url: Optional[str] = Field(default=None, description="URL reference to content (mutually exclusive with content)")
    content_encoding: Literal["plain", "base64"] = Field(default="plain", description="Encoding of inline content")
    name: Optional[str] = Field(default=None, description="If set, this part is an Artifact")
    metadata: Optional[PartMetadata] = Field(default=None, description="Optional metadata annotation")

    @model_validator(mode="after")
    def check_content_exclusivity(self) -> "MessagePart":
        """Validate that content and content_url are mutually exclusive."""
        if self.content is not None and self.content_url is not None:
            raise ValueError("content and content_url are mutually exclusive")
        if self.content is None and self.content_url is None:
            raise ValueError("either content or content_url must be provided")
        return self


# --- Message ---

# ACP role pattern: user | agent | agent/{name}
_ROLE_PATTERN = re.compile(r"^(user|agent(/[a-zA-Z0-9_\-]+)?)$")


class AcpMessage(BaseModel):
    """An ACP-compliant message.

    Messages are exchanged between clients and agents. Each message has a role
    identifying the sender and an ordered list of MessageParts carrying content.

    Named AcpMessage to avoid collision with the legacy nora.models.Message.
    """

    role: str = Field(..., description="Sender role: 'user', 'agent', or 'agent/{name}'")
    parts: list[MessagePart] = Field(..., min_length=1, description="Ordered message parts")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")

    @model_validator(mode="after")
    def check_role_pattern(self) -> "AcpMessage":
        """Validate role matches ACP pattern."""
        if not _ROLE_PATTERN.match(self.role):
            raise ValueError(
                f"role must match pattern '^(user|agent(/[a-zA-Z0-9_\\-]+)?)$', got '{self.role}'"
            )
        return self

    # --- Convenience constructors ---

    @classmethod
    def user(cls, text: str) -> "AcpMessage":
        """Create a simple user text message."""
        return cls(
            role="user",
            parts=[MessagePart(content=text)],
            created_at=datetime.now(),
        )

    @classmethod
    def agent(cls, text: str, agent_name: Optional[str] = None) -> "AcpMessage":
        """Create a simple agent text message."""
        role = f"agent/{agent_name}" if agent_name else "agent"
        return cls(
            role=role,
            parts=[MessagePart(content=text)],
            created_at=datetime.now(),
        )

    @classmethod
    def tool_trajectory(
        cls,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: Any,
        agent_name: Optional[str] = None,
    ) -> "AcpMessage":
        """Create an agent message recording a tool call via TrajectoryMetadata."""
        role = f"agent/{agent_name}" if agent_name else "agent"
        output_str = json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output
        return cls(
            role=role,
            parts=[
                MessagePart(
                    content_type="application/json",
                    content=output_str,
                    metadata=TrajectoryMetadata(
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_output={"result": tool_output} if isinstance(tool_output, str) else tool_output,
                    ),
                )
            ],
            created_at=datetime.now(),
        )

    @classmethod
    def shell(cls, command: str, output: str, exit_code: int = 0) -> "AcpMessage":
        """Create a Nora shell passthrough message (Nora extension)."""
        return cls(
            role="user",
            parts=[
                MessagePart(
                    content_type="application/x-nora-shell",
                    content=command,
                    metadata=NanoShellMetadata(
                        exit_code=exit_code,
                        output=output,
                    ),
                )
            ],
            created_at=datetime.now(),
        )

    # --- Query helpers ---

    def get_text(self) -> str:
        """Extract concatenated text/plain content from all parts."""
        texts = []
        for part in self.parts:
            if part.content_type == "text/plain" and part.content:
                texts.append(part.content)
        return "\n".join(texts)

    def is_shell(self) -> bool:
        """Check if this is a Nora shell passthrough message."""
        return any(p.content_type == "application/x-nora-shell" for p in self.parts)

    def has_trajectory(self) -> bool:
        """Check if this message contains tool trajectory metadata."""
        return any(
            isinstance(p.metadata, TrajectoryMetadata) for p in self.parts
        )

    def is_displayable(self) -> bool:
        """Check if this message should be displayed in the chat UI.

        Trajectory-only messages (pure tool calls) are not displayed as
        standalone chat bubbles. Shell messages are displayable.
        """
        if self.is_shell():
            return True
        # If ALL parts are trajectories, not displayable as a chat message
        if all(isinstance(p.metadata, TrajectoryMetadata) for p in self.parts):
            return False
        return True
