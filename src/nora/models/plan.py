"""Plan model for feature specifications."""

from datetime import datetime
from pydantic import BaseModel, Field


class Plan(BaseModel):
    """
    Represents a saved plan/specification from plan mode.
    
    Plans capture feature specifications that can be executed in edit mode.
    """
    
    id: str = Field(..., description="Unique plan identifier (timestamp-based)")
    description: str = Field(..., description="Short description derived from content")
    content: str = Field(..., description="Full plan content in markdown")
    created: datetime = Field(..., description="Creation timestamp")
    thread_id: str = Field(..., description="Source thread ID")
    
    def get_filename(self) -> str:
        """
        Generate filename for plan storage.
        
        Returns:
            Filename in format '{id}-{description}.md'.
        """
        return f"{self.id}-{self.description}.md"
