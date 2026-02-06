"""ACP Runner — bridges ACP Run execution to Strands agent.

Handles the conversion from ACP Run requests to Strands agent invocations
and back, including streaming support via events.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from nora.acp.convert import acp_to_strands_messages
from nora.acp.models.error import AcpError, ErrorCode
from nora.acp.models.message import AcpMessage, MessagePart, TrajectoryMetadata
from nora.acp.models.run import Run, RunEvent, RunEventType, RunStatus
from nora.acp.models.session import Session
from nora.repositories.run_repository import RunRepository
from nora.repositories.session_repository import SessionRepository
from nora.services.agent_service import AgentService, CancellationHook


class AcpRunner:
    """Executes ACP Runs using the Strands agent framework."""

    def __init__(
        self,
        agent_service: Optional[AgentService] = None,
        session_repo: Optional[SessionRepository] = None,
        run_repo: Optional[RunRepository] = None,
        profile: Optional[str] = None,
    ) -> None:
        self._agent_service = agent_service or AgentService()
        self._session_repo = session_repo or SessionRepository()
        self._run_repo = run_repo or RunRepository()
        self._profile = profile
        self._active_hooks: dict[UUID, CancellationHook] = {}

    def cancel_run(self, run_id: UUID) -> None:
        """Signal cancellation for an active run."""
        hook = self._active_hooks.get(run_id)
        if hook:
            hook.cancel()

    async def execute_sync(self, run: Run, session: Session) -> Run:
        """Execute a run synchronously — blocks until completion.

        Returns the completed Run with output messages.
        """
        # Collect all events, return final state
        async for _ in self.execute_stream(run, session):
            pass
        return run

    async def execute_stream(
        self, run: Run, session: Session
    ) -> AsyncGenerator[RunEvent, None]:
        """Execute a run with streaming events.

        Yields RunEvent objects as the agent processes. The run object
        is mutated in place with status transitions and output.
        """
        cancel_hook = CancellationHook()
        self._active_hooks[run.run_id] = cancel_hook

        try:
            # Emit run.created
            yield RunEvent(
                type=RunEventType.RUN_CREATED,
                run_id=run.run_id,
                data={"status": RunStatus.CREATED.value},
            )

            # Transition to in-progress
            run.start()
            yield RunEvent(
                type=RunEventType.RUN_IN_PROGRESS,
                run_id=run.run_id,
                data={"status": RunStatus.IN_PROGRESS.value},
            )

            # Load session history for context
            strands_history = self._run_repo.load_all_strands_messages(session.id)

            # Convert ACP input to text prompt
            prompt_parts = []
            for msg in run.input:
                prompt_parts.append(msg.get_text())
            prompt = "\n".join(p for p in prompt_parts if p)

            # Create agent with history
            agent = self._agent_service.create_agent(
                messages=strands_history,
                profile=self._profile,
                mode=session.mode,
                hooks=[cancel_hook],
            )

            # Collect streaming content
            output_chunks: list[str] = []
            tool_calls: list[AcpMessage] = []

            def on_stream(**kwargs: Any) -> None:
                if cancel_hook.cancelled:
                    return

                if "data" in kwargs:
                    chunk = kwargs["data"]
                    output_chunks.append(chunk)

                if "message" in kwargs:
                    msg = kwargs["message"]
                    if msg.get("role") == "assistant":
                        for block in msg.get("content", []):
                            if "toolUse" in block:
                                tu = block["toolUse"]
                                tool_calls.append(
                                    AcpMessage.tool_trajectory(
                                        tool_name=tu.get("name", ""),
                                        tool_input=tu.get("input", {}),
                                        tool_output="",
                                    )
                                )

            agent.callback_handler = on_stream

            # Run agent in executor to not block the event loop
            loop = asyncio.get_event_loop()

            def run_agent() -> Any:
                if cancel_hook.cancelled:
                    return None
                return agent(prompt)

            try:
                result = await loop.run_in_executor(None, run_agent)
            except Exception as e:
                if cancel_hook.cancelled:
                    run.confirm_cancel()
                    yield RunEvent(
                        type=RunEventType.RUN_CANCELLED,
                        run_id=run.run_id,
                    )
                    return
                run.fail(AcpError(code=ErrorCode.SERVER_ERROR, message=str(e)))
                yield RunEvent(
                    type=RunEventType.RUN_FAILED,
                    run_id=run.run_id,
                    data={"error": str(e)},
                )
                return

            if cancel_hook.cancelled or result is None:
                run.confirm_cancel()
                yield RunEvent(
                    type=RunEventType.RUN_CANCELLED,
                    run_id=run.run_id,
                )
                return

            # Build output messages
            output_messages: list[AcpMessage] = []

            # Add tool trajectory messages
            output_messages.extend(tool_calls)

            # Add final text output
            full_text = "".join(output_chunks)
            if full_text:
                output_messages.append(AcpMessage.agent(full_text))

            # Emit message events
            for msg in output_messages:
                yield RunEvent(
                    type=RunEventType.MESSAGE_CREATED,
                    run_id=run.run_id,
                    data={"role": msg.role},
                )
                for part in msg.parts:
                    yield RunEvent(
                        type=RunEventType.MESSAGE_PART,
                        run_id=run.run_id,
                        data={
                            "content_type": part.content_type,
                            "content": part.content,
                        },
                    )
                yield RunEvent(
                    type=RunEventType.MESSAGE_COMPLETED,
                    run_id=run.run_id,
                )

            # Complete the run
            run.complete(output_messages)

            # Save run + strands sidecar
            self._run_repo.save(run, list(agent.messages))

            # Update session
            session.metadata.updated_at = datetime.now()
            if not session.metadata.name or session.metadata.name.startswith("Session "):
                for msg in run.input:
                    text = msg.get_text()
                    if text:
                        session.generate_name(text)
                        break
            self._session_repo.save(session)

            yield RunEvent(
                type=RunEventType.RUN_COMPLETED,
                run_id=run.run_id,
                data={"status": RunStatus.COMPLETED.value},
            )

        finally:
            self._active_hooks.pop(run.run_id, None)
