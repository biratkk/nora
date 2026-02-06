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
        return self._validate_tool_pairing(all_messages)

    @staticmethod
    def _validate_tool_pairing(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate and repair toolUse/toolResult pairing in message history.

        Bedrock requires:
        1. Every toolUse in an assistant message must have a corresponding toolResult
           in the immediately following user message.
        2. Every toolResult must reference a toolUse from the preceding assistant message.

        This can get out of sync due to cancelled runs or save bugs. We fix both:
        - Orphaned toolResults (no matching toolUse) are dropped.
        - Dangling toolUse blocks (no matching toolResult) get a synthetic error
          toolResult injected before the next message.
        """
        if not messages:
            return messages

        pending_tool_use_ids: list[str] = []  # ordered list of unanswered toolUse IDs
        repaired: list[dict[str, Any]] = []

        def _flush_pending() -> None:
            """Inject synthetic toolResult for any unanswered toolUse blocks."""
            if not pending_tool_use_ids:
                return
            synthetic_results = [
                {
                    "toolResult": {
                        "toolUseId": tid,
                        "status": "error",
                        "content": [{"text": "Tool execution was interrupted."}],
                    }
                }
                for tid in pending_tool_use_ids
            ]
            repaired.append({"role": "user", "content": synthetic_results})
            pending_tool_use_ids.clear()

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", [])

            if role == "assistant":
                # Before adding a new assistant message, flush any pending toolUse
                # IDs from the previous assistant that were never answered.
                _flush_pending()

                # Register new toolUse IDs
                for block in content:
                    if isinstance(block, dict) and "toolUse" in block:
                        tool_use_id = block["toolUse"].get("toolUseId", "")
                        if tool_use_id:
                            pending_tool_use_ids.append(tool_use_id)
                repaired.append(msg)

            elif role == "user":
                has_tool_results = any(
                    isinstance(b, dict) and "toolResult" in b for b in content
                )

                if has_tool_results:
                    # Build a set of currently pending IDs for fast lookup
                    pending_set = set(pending_tool_use_ids)
                    filtered_content = []
                    for block in content:
                        if isinstance(block, dict) and "toolResult" in block:
                            tr_id = block["toolResult"].get("toolUseId", "")
                            if tr_id in pending_set:
                                pending_set.discard(tr_id)
                                pending_tool_use_ids.remove(tr_id)
                                filtered_content.append(block)
                            # else: orphaned toolResult, drop it
                        else:
                            filtered_content.append(block)

                    if not filtered_content:
                        # All content was orphaned; skip this message entirely
                        continue
                    msg = {**msg, "content": filtered_content}

                repaired.append(msg)
            else:
                _flush_pending()
                repaired.append(msg)

        # Flush any trailing unanswered toolUse blocks
        _flush_pending()

        return repaired

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
