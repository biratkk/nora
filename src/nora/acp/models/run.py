"""ACP Run model and related types.

Aligned with ACP v0.2.0 OpenAPI spec.
See: https://agentcommunicationprotocol.dev/core-concepts/agent-run-lifecycle
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from nora.acp.models.error import AcpError
from nora.acp.models.message import AcpMessage


# --- Nora agent mode ---

AgentMode = Literal["vibe", "plan", "act"]
"""The Nora interaction mode for a run.

- **vibe** — free-form conversation and coding (default).
- **plan** — research and produce a specification/plan (read-only tools).
- **act** — execute a plan step-by-step (full tool access).
"""


class RunStatus(str, Enum):
    """ACP run status values."""

    CREATED = "created"
    IN_PROGRESS = "in-progress"
    AWAITING = "awaiting"
    COMPLETED = "completed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state."""
        return self in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED)


class RunMode(str, Enum):
    """ACP run execution modes."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class RunCreateRequest(BaseModel):
    """Request body for POST /runs."""

    agent_name: str = Field(..., description="Target agent name")
    input: list[AcpMessage] = Field(..., min_length=1, description="Input messages")
    session_id: Optional[UUID] = Field(default=None, description="Existing session to continue")
    mode: RunMode = Field(default=RunMode.SYNC, description="Execution mode (sync, async, stream)")
    agent_mode: AgentMode = Field(
        default="vibe",
        description=(
            "Nora interaction mode for this run. "
            "'vibe' for free-form coding, 'plan' for research/specification, "
            "'act' for executing a plan."
        ),
    )


class RunResumeRequest(BaseModel):
    """Request body for POST /runs/{run_id} (resume)."""

    await_resume: dict[str, Any] = Field(..., description="Client response payload")
    mode: RunMode = Field(default=RunMode.SYNC, description="Execution mode")


class Run(BaseModel):
    """An ACP Run representing a single agent execution.

    Each user prompt → agent response cycle in Nora maps to one Run.
    Runs belong to Sessions and track their lifecycle status.

    The `agent_mode` field controls how Nora behaves during this run:
    - **vibe**: free-form conversation and coding (default)
    - **plan**: research-only, produces a specification
    - **act**: executes a plan with full tool access
    """

    run_id: UUID = Field(default_factory=uuid4, description="Unique run identifier")
    agent_name: str = Field(..., description="Agent that executed this run")
    agent_mode: AgentMode = Field(
        default="vibe",
        description="Nora interaction mode for this run (vibe, plan, act)",
    )
    status: RunStatus = Field(default=RunStatus.CREATED, description="Current run status")
    input: list[AcpMessage] = Field(default_factory=list, description="Input messages")
    output: list[AcpMessage] = Field(default_factory=list, description="Output messages")
    session_id: Optional[UUID] = Field(default=None, description="Session this run belongs to")
    await_request: Optional[dict[str, Any]] = Field(default=None, description="What is awaited from client")
    error: Optional[AcpError] = Field(default=None, description="Error details if failed")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    finished_at: Optional[datetime] = Field(default=None, description="Completion timestamp")

    @classmethod
    def create(
        cls,
        agent_name: str,
        input_messages: list[AcpMessage],
        session_id: Optional[UUID] = None,
        agent_mode: AgentMode = "vibe",
    ) -> "Run":
        """Create a new run in CREATED state."""
        return cls(
            agent_name=agent_name,
            input=input_messages,
            session_id=session_id,
            agent_mode=agent_mode,
        )

    def start(self) -> None:
        """Transition to IN_PROGRESS."""
        self.status = RunStatus.IN_PROGRESS

    def complete(self, output: list[AcpMessage]) -> None:
        """Transition to COMPLETED with output."""
        self.status = RunStatus.COMPLETED
        self.output = output
        self.finished_at = datetime.now()

    def fail(self, error: AcpError) -> None:
        """Transition to FAILED with error."""
        self.status = RunStatus.FAILED
        self.error = error
        self.finished_at = datetime.now()

    def request_cancel(self) -> None:
        """Transition to CANCELLING."""
        if not self.status.is_terminal:
            self.status = RunStatus.CANCELLING

    def confirm_cancel(self) -> None:
        """Transition to CANCELLED."""
        self.status = RunStatus.CANCELLED
        self.finished_at = datetime.now()

    def await_input(self, request: dict[str, Any]) -> None:
        """Transition to AWAITING."""
        self.status = RunStatus.AWAITING
        self.await_request = request


# --- SSE Event types ---

class RunEventType(str, Enum):
    """ACP Server-Sent Event types."""

    MESSAGE_CREATED = "message.created"
    MESSAGE_PART = "message.part"
    MESSAGE_COMPLETED = "message.completed"
    GENERIC = "generic"
    RUN_CREATED = "run.created"
    RUN_IN_PROGRESS = "run.in-progress"
    RUN_AWAITING = "run.awaiting"
    RUN_COMPLETED = "run.completed"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    ERROR = "error"


class RunEvent(BaseModel):
    """An event emitted during a run (for SSE streaming)."""

    type: RunEventType = Field(..., description="Event type")
    run_id: UUID = Field(..., description="Run this event belongs to")
    data: Optional[dict[str, Any]] = Field(default=None, description="Event payload")
