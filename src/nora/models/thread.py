"""Thread model."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from nora.models.message import Message

Mode = Literal["vibe", "plan", "act"]


class Thread(BaseModel):
    id: str
    name: str = ""
    created: str = ""
    updated: str = ""
    messages: list[Message] = Field(default_factory=list)
    mode: Mode = "vibe"
    plan_id: str | None = None

    def _generate_name(self) -> str:
        for msg in self.messages:
            if msg.role == "user" and msg.content:
                return msg.content[:40] + ("..." if len(msg.content) > 40 else "")
        return f"Thread {self.id}"

    @classmethod
    def create(cls) -> "Thread":
        tid = datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(id=tid, created=tid)
