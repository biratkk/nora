"""Migration utility for converting legacy thread files to ACP sessions.

Converts $CWD/.nora/threads/thread_*.json to
$CWD/.nora/sessions/<uuid>/session.json + runs/<uuid>.json
"""

import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from nora.acp.convert import legacy_messages_to_acp
from nora.acp.models.message import AcpMessage
from nora.acp.models.run import Run, RunStatus
from nora.acp.models.session import Session, SessionMetadata
from nora.config.constants import NORA_DIR_NAME, SESSIONS_DIR_NAME, THREADS_DIR_NAME
from nora.repositories.run_repository import RunRepository
from nora.repositories.session_repository import SessionRepository

logger = logging.getLogger("nora.acp.migrate")


def migrate_threads(
    base_dir: Path | None = None,
) -> dict[str, int]:
    """Migrate all legacy thread files to ACP session format.

    Args:
        base_dir: Base .nora directory. Defaults to $CWD/.nora.

    Returns:
        Dict with counts: {"migrated": N, "skipped": N, "errors": N}
    """
    nora_dir = base_dir or (Path.cwd() / NORA_DIR_NAME)
    threads_dir = nora_dir / THREADS_DIR_NAME

    session_repo = SessionRepository(base_dir=nora_dir)
    run_repo = RunRepository(base_dir=nora_dir)

    stats = {"migrated": 0, "skipped": 0, "errors": 0}

    if not threads_dir.exists():
        return stats

    for thread_path in sorted(threads_dir.glob("thread_*.json")):
        try:
            thread_data = json.loads(thread_path.read_text())
            _migrate_single_thread(thread_data, session_repo, run_repo)
            stats["migrated"] += 1
            logger.debug("Migrated thread: %s", thread_path.name)
        except Exception as e:
            stats["errors"] += 1
            logger.error("Failed to migrate %s: %s", thread_path.name, e, exc_info=True)

    logger.info(
        "Migration complete: migrated=%d, skipped=%d, errors=%d",
        stats["migrated"], stats["skipped"], stats["errors"],
    )
    return stats


def _migrate_single_thread(
    thread_data: dict[str, Any],
    session_repo: SessionRepository,
    run_repo: RunRepository,
) -> Session:
    """Migrate a single thread dict to an ACP session with runs."""
    thread_id = thread_data.get("id", "")
    thread_name = thread_data.get("name", "")
    thread_mode = thread_data.get("mode", "vibe")
    # Normalize legacy "act" mode to "edit"
    if thread_mode == "act":
        thread_mode = "edit"
    thread_plan_id = thread_data.get("plan_id")
    thread_created = thread_data.get("created", "")
    messages = thread_data.get("messages", [])
    raw_messages = thread_data.get("raw_messages", [])

    # Create session (mode-agnostic — mode lives on runs now)
    session = Session(
        metadata=SessionMetadata(
            name=thread_name,
            plan_id=thread_plan_id,
            updated_at=None,
        ),
    )

    # Group messages into runs — each inherits the thread's mode
    runs = _group_messages_into_runs(messages, session.id, agent_mode=thread_mode)

    # Save session
    session_repo.save(session)

    # Save runs
    for run in runs:
        run_repo.save(run, strands_messages=None)

    # If we have raw_messages, save them as the strands sidecar for the last run
    if raw_messages and runs:
        last_run = runs[-1]
        run_repo.save(last_run, strands_messages=raw_messages)

    return session


def _group_messages_into_runs(
    messages: list[dict[str, Any]],
    session_id: Any,
    agent_mode: str = "vibe",
) -> list[Run]:
    """Group legacy messages into ACP runs.

    Strategy: each user message starts a new run. All subsequent
    assistant/tool_call/shell messages belong to that run's output
    until the next user message.

    All migrated runs inherit the thread's mode as their agent_mode.
    """
    runs: list[Run] = []
    current_input: list[AcpMessage] = []
    current_output: list[AcpMessage] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")

        if role == "user":
            # If we have a pending run, finalize it
            if current_input:
                run = Run(
                    agent_name="nora",
                    agent_mode=agent_mode,
                    status=RunStatus.COMPLETED,
                    input=current_input,
                    output=current_output,
                    session_id=session_id,
                )
                runs.append(run)

            # Start new run
            if content:
                current_input = [AcpMessage.user(content)]
            else:
                current_input = []
            current_output = []

        elif role == "assistant":
            if content:
                current_output.append(AcpMessage.agent(content))

        elif role == "tool_call":
            tool = msg.get("tool", "")
            parameters = msg.get("parameters", {})
            result = msg.get("result")
            current_output.append(
                AcpMessage.tool_trajectory(
                    tool_name=tool,
                    tool_input=parameters,
                    tool_output=result or "",
                )
            )

        elif role == "shell":
            command = content or ""
            output = msg.get("output", "")
            # Shell messages go to input (they're user-initiated)
            current_input.append(AcpMessage.shell(command, output))

    # Finalize last run
    if current_input:
        run = Run(
            agent_name="nora",
            agent_mode=agent_mode,
            status=RunStatus.COMPLETED,
            input=current_input,
            output=current_output,
            session_id=session_id,
        )
        runs.append(run)

    return runs
