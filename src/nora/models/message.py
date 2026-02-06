"""Message model for chat conversations."""

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "tool_call", "shell"]


class Message(BaseModel):
    """
    Represents a single message in a conversation thread.
    
    Messages can be user input, assistant responses, tool call records,
    or shell passthrough commands. Tool calls store the tool name, parameters,
    and result for replay/display. Shell messages store command and output.
    """
    
    role: MessageRole = Field(..., description="The role of the message sender")
    content: Optional[str] = Field(default=None, description="Text content of the message")
    tool: Optional[str] = Field(default=None, description="Name of the tool called (for tool_call role)")
    parameters: Optional[dict[str, Any]] = Field(default=None, description="Parameters passed to the tool")
    result: Optional[str] = Field(default=None, description="Result returned from tool execution")
    output: Optional[str] = Field(default=None, description="Output from shell command execution (for shell role)")
    
    def is_displayable(self) -> bool:
        """
        Check if message has content that can be displayed in chat.
        
        Returns:
            True if message is a shell command, or not a tool_call with content.
        """
        if self.role == "shell":
            return True
        return self.role != "tool_call" and self.content is not None
    
    def to_agent_format(self) -> dict[str, Any] | None:
        """
        Convert message to the format expected by Strands agent.
        
        Returns:
            Dictionary with role and content fields for agent consumption,
            or None for shell messages (should not be sent to agent).
        """
        if self.role == "shell":
            return None
        return {
            "role": self.role,
            "content": [{"text": self.content}]
        }
