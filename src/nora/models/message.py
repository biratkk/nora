"""Message model for chat conversations."""

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "tool_call"]


class Message(BaseModel):
    """
    Represents a single message in a conversation thread.
    
    Messages can be user input, assistant responses, or tool call records.
    Tool calls store the tool name, parameters, and result for replay/display.
    """
    
    role: MessageRole = Field(..., description="The role of the message sender")
    content: Optional[str] = Field(default=None, description="Text content of the message")
    tool: Optional[str] = Field(default=None, description="Name of the tool called (for tool_call role)")
    parameters: Optional[dict[str, Any]] = Field(default=None, description="Parameters passed to the tool")
    result: Optional[str] = Field(default=None, description="Result returned from tool execution")
    
    def is_displayable(self) -> bool:
        """
        Check if message has content that can be displayed in chat.
        
        Returns:
            True if message is not a tool_call and has content.
        """
        return self.role != "tool_call" and self.content is not None
    
    def to_agent_format(self) -> dict[str, Any]:
        """
        Convert message to the format expected by Strands agent.
        
        Returns:
            Dictionary with role and content fields for agent consumption.
        """
        return {
            "role": self.role,
            "content": [{"text": self.content}]
        }
