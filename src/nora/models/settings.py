"""Application settings model."""

from typing import Optional
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """
    Application-wide settings persisted to disk.
    
    Settings are stored in ~/.nora/settings.json.
    """
    
    defaultProfile: Optional[str] = Field(
        default=None, 
        description="Default AWS profile for Bedrock API calls"
    )
