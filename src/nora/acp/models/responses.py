"""ACP response and request models for API endpoints.

Thin wrappers providing typed responses for FastAPI's OpenAPI schema generation.
Domain models (Run, Session, AgentManifest) live in their own modules.
"""

from typing import Optional

from pydantic import BaseModel, Field

from nora.acp.models.agent_manifest import AgentManifest
from nora.acp.models.run import Run, RunEvent
from nora.acp.models.session import Session


# --- Ping ---


class PingResponse(BaseModel):
    """Health check response. Empty object indicates the server is alive."""

    pass


# --- Agents ---


class ListAgentsResponse(BaseModel):
    """Paginated list of available agents."""

    agents: list[AgentManifest] = Field(
        default_factory=list,
        description="List of agent manifests",
    )


# --- Runs ---


class ListRunEventsResponse(BaseModel):
    """List of events emitted during a run."""

    events: list[RunEvent] = Field(
        default_factory=list,
        description="Ordered list of run events",
    )


# --- Sessions ---


class SessionCreateRequest(BaseModel):
    """Request body for POST /sessions.

    The name is optional — omitting it creates a session with an
    auto-generated name. The interaction mode (vibe/plan/act) is set
    per-Run via `RunCreateRequest.agent_mode`, not on the session.
    """

    name: Optional[str] = Field(
        default=None,
        description="Human-readable session name. Auto-generated from first message if omitted.",
    )


class ListSessionsResponse(BaseModel):
    """List of all sessions."""

    sessions: list[Session] = Field(
        default_factory=list,
        description="List of sessions, most recent first",
    )


class ListSessionRunsResponse(BaseModel):
    """List of runs belonging to a session."""

    runs: list[Run] = Field(
        default_factory=list,
        description="Ordered list of runs in the session",
    )
