"""MCP server configuration models."""

from typing import Optional

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """Single MCP server configuration entry."""

    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    disabled: bool = False
    disabledTools: list[str] = Field(default_factory=list)
    trustedTools: list[str] = Field(default_factory=list)


class McpConfigFile(BaseModel):
    """Root MCP configuration file."""

    mcpServers: dict[str, McpServerConfig] = Field(default_factory=dict)
