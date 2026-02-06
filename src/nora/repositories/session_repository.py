"""Repository for ACP Session persistence.

Sessions are stored as JSON files in $CWD/.nora/sessions/<uuid>/session.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from nora.acp.models.session import Session
from nora.config.constants import NORA_DIR_NAME, SESSIONS_DIR_NAME


class SessionRepository:
    """Handles persistence of ACP sessions to disk.

    Directory structure:
        $CWD/.nora/sessions/<uuid>/session.json
        $CWD/.nora/sessions/<uuid>/runs/<run_id>.json
        $CWD/.nora/sessions/<uuid>/runs/<run_id>.strands.json
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._sessions_dir = self._base_dir / SESSIONS_DIR_NAME

    @property
    def sessions_dir(self) -> Path:
        return self._sessions_dir

    def _ensure_dirs(self, session_id: UUID) -> Path:
        """Ensure session directory exists and return it."""
        self._base_dir.mkdir(exist_ok=True)
        self._sessions_dir.mkdir(exist_ok=True)
        session_dir = self._sessions_dir / str(session_id)
        session_dir.mkdir(exist_ok=True)
        runs_dir = session_dir / "runs"
        runs_dir.mkdir(exist_ok=True)
        return session_dir

    def _get_session_dir(self, session_id: UUID) -> Path:
        return self._sessions_dir / str(session_id)

    def _get_session_path(self, session_id: UUID) -> Path:
        return self._get_session_dir(session_id) / "session.json"

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        session.metadata.updated_at = datetime.now()
        if not session.metadata.name:
            session.metadata.name = f"Session {str(session.id)[:8]}"
        self._ensure_dirs(session.id)
        path = self._get_session_path(session.id)
        path.write_text(session.model_dump_json(indent=2))

    def load(self, session_id: UUID) -> Optional[Session]:
        """Load a session from disk. Returns None if not found."""
        path = self._get_session_path(session_id)
        if path.exists():
            return Session.model_validate_json(path.read_text())
        return None

    def list_all(self) -> list[Session]:
        """List all sessions, sorted by most recently updated first."""
        if not self._sessions_dir.exists():
            return []

        sessions: list[Session] = []
        for session_dir in self._sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            session_path = session_dir / "session.json"
            if session_path.exists():
                try:
                    sessions.append(Session.model_validate_json(session_path.read_text()))
                except Exception:
                    continue

        # Sort by updated_at descending (most recent first)
        sessions.sort(
            key=lambda s: s.metadata.updated_at or s.created_at,
            reverse=True,
        )
        return sessions

    def exists(self, session_id: UUID) -> bool:
        return self._get_session_path(session_id).exists()

    def delete(self, session_id: UUID) -> bool:
        """Delete a session and all its runs."""
        session_dir = self._get_session_dir(session_id)
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)
            return True
        return False
