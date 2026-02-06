"""Service for ACP Session management.

Provides high-level operations for creating, loading, and manipulating
ACP sessions. Replaces ThreadService for new ACP-based storage.
"""

from typing import Optional
from uuid import UUID

from nora.acp.models.session import Session
from nora.acp.models.run import Run
from nora.acp.models.message import AcpMessage
from nora.repositories.session_repository import SessionRepository
from nora.repositories.run_repository import RunRepository


class SessionService:
    """Manages ACP session lifecycle and operations."""

    def __init__(
        self,
        session_repo: Optional[SessionRepository] = None,
        run_repo: Optional[RunRepository] = None,
    ) -> None:
        self._session_repo = session_repo or SessionRepository()
        self._run_repo = run_repo or RunRepository()

    def create(self) -> Session:
        """Create a new session."""
        return Session.create()

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        self._session_repo.save(session)

    def load(self, session_id: UUID) -> Optional[Session]:
        """Load a session by ID."""
        return self._session_repo.load(session_id)

    def list_all(self) -> list[Session]:
        """List all sessions, most recent first."""
        return self._session_repo.list_all()

    def exists(self, session_id: UUID) -> bool:
        """Check if a session exists."""
        return self._session_repo.exists(session_id)

    def delete(self, session_id: UUID) -> bool:
        """Delete a session and all its runs."""
        return self._session_repo.delete(session_id)

    def get_history(self, session: Session) -> list[AcpMessage]:
        """Get full message history for a session by concatenating all runs.

        Messages are returned in chronological order: run1.input + run1.output +
        run2.input + run2.output + ...
        """
        runs = self._run_repo.list_for_session(session.id)
        messages: list[AcpMessage] = []
        for run in runs:
            messages.extend(run.input)
            messages.extend(run.output)
        return messages

    def get_strands_history(self, session: Session) -> list[dict]:
        """Load all Strands-native messages for a session.

        Used to initialize a Strands agent with full conversation context.
        """
        return self._run_repo.load_all_strands_messages(session.id)

    def get_runs(self, session: Session) -> list[Run]:
        """Get all runs for a session in chronological order."""
        return self._run_repo.list_for_session(session.id)

    def get_last_assistant_text(self, session: Session) -> Optional[str]:
        """Get the text content of the last agent message in the session."""
        runs = self._run_repo.list_for_session(session.id)
        for run in reversed(runs):
            for msg in reversed(run.output):
                if msg.role.startswith("agent"):
                    text = msg.get_text()
                    if text:
                        return text
        return None

    def generate_name(self, session: Session) -> str:
        """Generate a session name from the first user message."""
        runs = self._run_repo.list_for_session(session.id)
        for run in runs:
            for msg in run.input:
                if msg.role == "user":
                    text = msg.get_text()
                    if text:
                        return session.generate_name(text)
        return session.name
