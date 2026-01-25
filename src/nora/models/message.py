"""Message model."""

from typing import Literal, Optional
from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["user", "assistant", "tool_call"]
    content: Optional[str] = None
    tool: Optional[str] = None
    parameters: Optional[dict] = None
    result: Optional[str] = None
