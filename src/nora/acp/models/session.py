"""ACP Session model.

Sessions maintain state across multiple Runs in ACP.
Replaces Nora's Thread model.

Sessions are mode-agnostic — the interaction mode (vibe/plan/act) is a
per-Run concern, set via `Run.agent_mode`. This allows switching modes
between runs within the same conversational context.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionMetadata(BaseModel):
    """Nora-specific session extensions (not in ACP core spec)."""

    name: str = Field(default="", description="Human-readable session name")
    plan_id: Optional[str] = Field(default=None, description="Associated plan ID (set when a plan run completes)")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")


class Session(BaseModel):
    """An ACP Session representing a conversation context.

    Sessions group related Runs together, allowing the agent to maintain
    conversational history across multiple interactions. Each session has
    a UUID and Nora-specific metadata for name/plan tracking.

    The interaction mode (vibe/plan/edit) is set per-Run, not per-Session,
    so you can plan and then act within the same session.
    """

    id: UUID = Field(default_factory=uuid4, description="Session identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    metadata: SessionMetadata = Field(default_factory=SessionMetadata, description="Nora-specific extensions")

    @classmethod
    def create(cls) -> "Session":
        """Create a new session."""
        return cls()

    def generate_name(self, first_user_text: str) -> str:
        """Generate a name from the first user message content."""
        content = first_user_text[:40]
        name = content + ("..." if len(first_user_text) > 40 else "")
        self.metadata.name = name
        return name

    @property
    def name(self) -> str:
        """Get display name."""
        return self.metadata.name or f"Session {str(self.id)[:8]}"
