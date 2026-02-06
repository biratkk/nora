"""Service for ACP Run lifecycle management.

Manages the creation, execution tracking, and persistence of ACP Runs.
Each user prompt → agent response cycle in Nora maps to one Run.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from nora.acp.models.error import AcpError, ErrorCode
from nora.acp.models.message import AcpMessage
from nora.acp.models.run import Run, RunStatus
from nora.repositories.run_repository import RunRepository


class RunService:
    """Manages ACP Run lifecycle."""

    def __init__(self, run_repo: Optional[RunRepository] = None) -> None:
        self._run_repo = run_repo or RunRepository()

    def create(
        self,
        agent_name: str,
        input_messages: list[AcpMessage],
        session_id: UUID,
    ) -> Run:
        """Create a new Run in CREATED state."""
        return Run.create(
            agent_name=agent_name,
            input_messages=input_messages,
            session_id=session_id,
        )

    def start(self, run: Run) -> None:
        """Transition run to IN_PROGRESS."""
        run.start()

    def complete(self, run: Run, output: list[AcpMessage]) -> None:
        """Transition run to COMPLETED with output messages."""
        run.complete(output)

    def fail(self, run: Run, message: str, code: ErrorCode = ErrorCode.SERVER_ERROR) -> None:
        """Transition run to FAILED with error."""
        run.fail(AcpError(code=code, message=message))

    def cancel(self, run: Run) -> None:
        """Request cancellation of a run."""
        run.request_cancel()

    def confirm_cancel(self, run: Run) -> None:
        """Confirm cancellation of a run."""
        run.confirm_cancel()

    def save(
        self,
        run: Run,
        strands_messages: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Save a run and optionally its Strands sidecar messages."""
        self._run_repo.save(run, strands_messages)

    def load(self, session_id: UUID, run_id: UUID) -> Optional[Run]:
        """Load a run from disk."""
        return self._run_repo.load(session_id, run_id)

    def list_for_session(self, session_id: UUID) -> list[Run]:
        """List all runs for a session in chronological order."""
        return self._run_repo.list_for_session(session_id)

    def load_strands_messages(self, session_id: UUID, run_id: UUID) -> Optional[list[dict]]:
        """Load Strands-native messages for a specific run."""
        return self._run_repo.load_strands_messages(session_id, run_id)
