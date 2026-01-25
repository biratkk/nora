"""Plugin model for extensible agent capabilities."""

from typing import List, Tuple
from pydantic import BaseModel, Field, field_validator
import yaml


def validate_plugin_name(name: str) -> Tuple[bool, str]:
    """
    Validate plugin name format.
    
    Args:
        name: Plugin name to validate.
        
    Returns:
        Tuple of (is_valid, error_message). Error message is empty if valid.
    """
    if not name:
        return False, "Name cannot be empty"
    if " " in name:
        return False, "Name cannot contain spaces"
    if "/" in name:
        return False, "Name cannot contain /"
    if "\\" in name:
        return False, "Name cannot contain \\"
    return True, ""


class Plugin(BaseModel):
    """
    Represents a plugin with metadata and instructions.
    
    Plugins extend agent capabilities through keyword-triggered instructions.
    They are stored as markdown files with YAML frontmatter.
    """
    
    name: str = Field(..., description="Unique plugin identifier (no spaces or slashes)")
    description: str = Field(default="", description="Brief description of plugin purpose")
    keywords: List[str] = Field(default_factory=list, description="Keywords for fuzzy matching")
    instructions: str = Field(default="", description="Instructions injected into agent context")
    load_on_startup: bool = Field(default=False, description="Whether to load plugin automatically")
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate plugin name format.
        
        Args:
            v: The name value to validate.
            
        Returns:
            The validated name.
            
        Raises:
            ValueError: If name contains invalid characters.
        """
        if not v:
            raise ValueError("Name cannot be empty")
        if " " in v:
            raise ValueError("Name cannot contain spaces")
        if "/" in v or "\\" in v:
            raise ValueError("Name cannot contain slashes")
        return v
    
    def to_markdown(self) -> str:
        """
        Convert plugin to markdown format with YAML frontmatter.
        
        Returns:
            Markdown string with frontmatter metadata and instructions body.
        """
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "keywords": ", ".join(self.keywords),
            "load_on_startup": "yes" if self.load_on_startup else "no"
        }
        yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
        return f"---\n{yaml_str}\n---\n{self.instructions}\n"
    
    def to_context_block(self) -> str:
        """
        Format plugin as XML context block for agent injection.
        
        Returns:
            XML-formatted string with plugin details.
        """
        return f"<PluginDetails name='{self.name}'>\n{self.instructions}\n</PluginDetails>"
