"""Thread model for conversation management."""

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from nora.models.message import Message


Mode = Literal["vibe", "plan", "act"]


class Thread(BaseModel):
    """
    Represents a conversation thread containing messages.
    
    Threads track conversation history, mode, and optional plan association.
    Each thread has a unique ID based on creation timestamp.
    """
    
    id: str = Field(..., description="Unique thread identifier (timestamp-based)")
    name: str = Field(default="", description="Human-readable thread name")
    created: str = Field(default="", description="ISO timestamp of creation")
    updated: str = Field(default="", description="ISO timestamp of last update")
    messages: list[Message] = Field(default_factory=list, description="Conversation messages")
    raw_messages: list[dict[str, Any]] = Field(default_factory=list, description="Raw agent messages with full toolUse/toolResult structure")
    mode: Mode = Field(default="vibe", description="Current conversation mode")
    plan_id: Optional[str] = Field(default=None, description="Associated plan ID for act mode")

    def _generate_name(self) -> str:
        """
        Generate a name from the first user message content.
        
        Returns:
            Truncated first user message or default thread name.
        """
        for msg in self.messages:
            if msg.role == "user" and msg.content:
                content = msg.content[:40]
                return content + ("..." if len(msg.content) > 40 else "")
        return f"Thread {self.id}"

    def get_displayable_messages(self) -> list[Message]:
        """
        Get messages suitable for display in chat UI.
        
        Returns:
            List of messages excluding tool calls without content.
        """
        return [msg for msg in self.messages if msg.is_displayable()]

    def to_agent_messages(self) -> list[dict]:
        """
        Convert thread messages to agent-compatible format.
        
        Returns raw_messages if available (preserves toolUse/toolResult structure),
        otherwise falls back to simplified text-only format.
        Shell messages are excluded as they should not be sent to the agent.
        
        Returns:
            List of message dicts for Strands agent initialization.
        """
        if self.raw_messages:
            return self.raw_messages
        return [
            msg.to_agent_format() 
            for msg in self.messages 
            if msg.is_displayable() and msg.role != "shell"
        ]

    @classmethod
    def create(cls) -> "Thread":
        """
        Create a new thread with timestamp-based ID.
        
        Returns:
            New Thread instance with generated ID and creation timestamp.
        """
        tid = datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(id=tid, created=tid)
