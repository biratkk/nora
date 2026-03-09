"""Plan model for feature specifications."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """
    Represents a saved plan/specification.
    
    Plans are stored as markdown files named by a 3-word hyphenated identifier
    (e.g., 'auth-session-refactor'). Legacy plans may have timestamp-based IDs.
    """
    
    name: str = Field(..., description="Plan name (e.g., 'auth-session-refactor')")
    content: str = Field(..., description="Full plan content in markdown")
    
    # Legacy fields — kept for backward compatibility with old plans
    id: Optional[str] = Field(None, description="Legacy timestamp-based ID")
    description: Optional[str] = Field(None, description="Legacy short description")
    created: Optional[datetime] = Field(None, description="Creation timestamp")
    thread_id: Optional[str] = Field(None, description="Legacy source thread ID")
    
    def get_filename(self) -> str:
        """
        Generate filename for plan storage.
        
        Returns:
            Filename in format '{name}.md'.
        """
        return f"{self.name}.md"
