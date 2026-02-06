"""ACP Agent Manifest model.

Aligned with ACP v0.2.0 OpenAPI spec.
See: https://agentcommunicationprotocol.dev/core-concepts/agent-manifest
"""

from typing import Optional

from pydantic import BaseModel, Field


class Capability(BaseModel):
    """A structured capability description."""

    name: str = Field(..., description="Capability identifier")
    description: str = Field(default="", description="Human-readable description")


class AgentStatus(BaseModel):
    """Dynamic runtime metrics for an agent."""

    avg_run_tokens: Optional[float] = Field(default=None, description="Average tokens per run")
    avg_run_time_seconds: Optional[float] = Field(default=None, description="Average run duration in seconds")
    success_rate: Optional[float] = Field(default=None, description="Success percentage (0-100)")


class ManifestMetadata(BaseModel):
    """Static discovery and classification metadata for an agent."""

    annotations: Optional[dict[str, str]] = None
    documentation: Optional[str] = None
    license: Optional[str] = None
    programming_language: Optional[str] = None
    natural_languages: Optional[list[str]] = None
    framework: Optional[str] = None
    capabilities: Optional[list[Capability]] = None
    domains: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class AgentManifest(BaseModel):
    """ACP Agent Manifest describing an agent's identity and capabilities.

    The manifest is returned by GET /agents and GET /agents/{name}.
    """

    name: str = Field(..., description="Agent identifier (DNS label format, 1-63 chars)")
    description: str = Field(..., description="Human-readable description")
    input_content_types: list[str] = Field(..., description="Supported input MIME types")
    output_content_types: list[str] = Field(..., description="Supported output MIME types")
    metadata: Optional[ManifestMetadata] = Field(default=None, description="Discovery metadata")
    status: Optional[AgentStatus] = Field(default=None, description="Runtime metrics")


def get_nora_manifest() -> AgentManifest:
    """Return Nora's ACP agent manifest."""
    return AgentManifest(
        name="nora",
        description="AI-powered CLI coding assistant using Strands Agents SDK with AWS Bedrock",
        input_content_types=["text/plain"],
        output_content_types=["text/plain", "application/json"],
        metadata=ManifestMetadata(
            framework="strands-agents",
            programming_language="Python",
            tags=["Chat", "Code"],
            capabilities=[
                Capability(name="file-operations", description="Read, write, and edit files"),
                Capability(name="shell-execution", description="Execute shell commands with trust policies"),
                Capability(name="web-fetch", description="Fetch web page content"),
                Capability(name="subagent", description="Spawn read-only research subagents"),
                Capability(name="code-search", description="Search for patterns across files"),
            ],
            domains=["software-development"],
        ),
    )
