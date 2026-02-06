"""Repository for ACP Run persistence.

Runs are stored as JSON files within their parent session directory:
    $CWD/.nora/sessions/<session_id>/runs/<run_id>.json
    $CWD/.nora/sessions/<session_id>/runs/<run_id>.strands.json
"""

import json
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from nora.acp.models.run import Run
from nora.config.constants import NORA_DIR_NAME, SESSIONS_DIR_NAME


class RunRepository:
    """Handles persistence of ACP Runs within sessions.

    Each run is stored as two files:
    - <run_id>.json: ACP-compliant Run data (input/output messages, status)
    - <run_id>.strands.json: Strands-native raw_messages for agent re-initialization
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._sessions_dir = self._base_dir / SESSIONS_DIR_NAME

    def _get_runs_dir(self, session_id: UUID) -> Path:
        return self._sessions_dir / str(session_id) / "runs"

    def _get_run_path(self, session_id: UUID, run_id: UUID) -> Path:
        return self._get_runs_dir(session_id) / f"{run_id}.json"

    def _get_strands_path(self, session_id: UUID, run_id: UUID) -> Path:
        return self._get_runs_dir(session_id) / f"{run_id}.strands.json"

    def _ensure_dirs(self, session_id: UUID) -> None:
        runs_dir = self._get_runs_dir(session_id)
        runs_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run: Run, strands_messages: Optional[list[dict[str, Any]]] = None) -> None:
        """Save a run and optionally its Strands-native messages.

        Args:
            run: The ACP Run to persist.
            strands_messages: Optional Strands SDK raw messages for agent re-init.
        """
        if run.session_id is None:
            raise ValueError("Cannot save a run without a session_id")

        self._ensure_dirs(run.session_id)

        # Save ACP run
        path = self._get_run_path(run.session_id, run.run_id)
        path.write_text(run.model_dump_json(indent=2))

        # Save Strands sidecar if provided
        if strands_messages is not None:
            strands_path = self._get_strands_path(run.session_id, run.run_id)
            strands_path.write_text(json.dumps(strands_messages, indent=2, default=str))

    def load(self, session_id: UUID, run_id: UUID) -> Optional[Run]:
        """Load a run from disk."""
        path = self._get_run_path(session_id, run_id)
        if path.exists():
            return Run.model_validate_json(path.read_text())
        return None

    def load_strands_messages(self, session_id: UUID, run_id: UUID) -> Optional[list[dict[str, Any]]]:
        """Load Strands-native messages for a run."""
        path = self._get_strands_path(session_id, run_id)
        if path.exists():
            return json.loads(path.read_text())
        return None

    def list_for_session(self, session_id: UUID) -> list[Run]:
        """List all runs for a session, sorted by creation time (oldest first).

        This ordering allows history reconstruction by concatenating runs.
        """
        runs_dir = self._get_runs_dir(session_id)
        if not runs_dir.exists():
            return []

        runs: list[Run] = []
        for path in runs_dir.glob("*.json"):
            # Skip strands sidecar files
            if path.name.endswith(".strands.json"):
                continue
            try:
                runs.append(Run.model_validate_json(path.read_text()))
            except Exception:
                continue

        runs.sort(key=lambda r: r.created_at)
        return runs

    def load_all_strands_messages(self, session_id: UUID) -> list[dict[str, Any]]:
        """Load and concatenate all Strands messages for a session.

        Returns all raw_messages from all runs in chronological order,
        suitable for initializing a Strands agent with full session history.
        """
        runs = self.list_for_session(session_id)
        all_messages: list[dict[str, Any]] = []
        for run in runs:
            strands_msgs = self.load_strands_messages(session_id, run.run_id)
            if strands_msgs:
                all_messages.extend(strands_msgs)
        return all_messages

    def delete(self, session_id: UUID, run_id: UUID) -> bool:
        """Delete a run and its strands sidecar."""
        deleted = False
        for path in [
            self._get_run_path(session_id, run_id),
            self._get_strands_path(session_id, run_id),
        ]:
            if path.exists():
                path.unlink()
                deleted = True
        return deleted
