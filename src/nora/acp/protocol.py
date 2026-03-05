"""Agent Client Protocol handler — transport-agnostic JSON-RPC dispatch.

Dispatches JSON-RPC 2.0 methods (initialize, session/new, session/prompt,
session/load, session/cancel, session/set_config_option) to the appropriate
Nora internal logic.

Both the stdio and HTTP transports feed messages into this handler.
"""

import asyncio
import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from nora.acp.client_interface import ClientInterface
from nora.acp.jsonrpc import (
    AGENT_ERROR,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    SESSION_NOT_FOUND,
    make_error,
    make_notification,
    make_response,
)
from nora.acp.models.error import AcpError, ErrorCode
from nora.acp.models.message import AcpMessage
from nora.acp.models.run import AgentMode, Run
from nora.acp.models.session import Session, TokenUsage
from nora.repositories.run_repository import RunRepository
from nora.repositories.session_repository import SessionRepository
from nora.services.agent_service import AgentService, CancellationHook

logger = logging.getLogger("nora.acp.protocol")

# Protocol version supported by Nora
PROTOCOL_VERSION = 1

# Nora agent info
AGENT_INFO = {
    "name": "nora",
    "title": "Nora",
    "version": "0.1.0",
}

# Valid agent modes for config options
_VALID_MODES: list[AgentMode] = ["vibe", "plan", "edit"]

# Type alias for the notification sender callback
NotificationSender = Callable[[dict[str, Any]], None]


def _build_config_options(current_mode: AgentMode) -> list[dict[str, Any]]:
    """Build the ACP configOptions array with current mode selection."""
    return [
        {
            "id": "mode",
            "name": "Mode",
            "description": "Controls Nora's behavior: vibe (full access), plan (read-only research), edit (auto-approved changes)",
            "category": "mode",
            "type": "select",
            "currentValue": current_mode,
            "options": [
                {"value": "vibe", "name": "Vibe", "description": "Free-form conversation and coding with full tool access"},
                {"value": "plan", "name": "Plan", "description": "Research and produce specifications (read-only tools)"},
                {"value": "edit", "name": "Edit", "description": "Autonomous implementation with auto-approved file changes"},
            ],
        },
    ]


class ProtocolHandler:
    """Transport-agnostic Agent Client Protocol handler.

    Manages protocol state (initialization, active sessions) and dispatches
    JSON-RPC method calls to the appropriate handlers.

    The `send_notification` callback is provided by the transport layer
    (stdio or HTTP) and is used to push `session/update` notifications
    during prompt execution.

    The `client` parameter provides the ClientInterface for Agent→Client
    operations (filesystem, terminal, permissions).
    """

    def __init__(
        self,
        send_notification: NotificationSender,
        client: Optional[ClientInterface] = None,
        profile: Optional[str] = None,
    ) -> None:
        self._send = send_notification
        self._client = client
        self._profile = profile
        self._initialized = False
        self._client_capabilities: dict[str, Any] = {}
        self._client_info: dict[str, Any] = {}

        self._session_repo = SessionRepository()
        self._run_repo = RunRepository()
        self._agent_service = AgentService()

        # Active cancel hooks keyed by session_id
        self._cancel_hooks: dict[str, CancellationHook] = {}

        # Per-session mode tracking (defaults to "vibe")
        self._session_modes: dict[str, AgentMode] = {}

        # Handler dispatch table (built once, not per-request)
        self._handlers: dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "session/new": self._handle_session_new,
            "session/load": self._handle_session_load,
            "session/prompt": self._handle_session_prompt,
            "session/set_config_option": self._handle_set_config_option,
        }

        client_type = type(client).__name__ if client else "None"
        logger.info("ProtocolHandler initialized (client=%s, profile=%s)", client_type, profile)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def handle_request(
        self, request_id: Any, method: str, params: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Handle a JSON-RPC request (expects a response).

        Returns a JSON-RPC response dict (success or error).
        """
        params = params or {}

        handler = self._handlers.get(method)
        if handler is None:
            # Custom methods starting with _ → Method not found (per ACP spec)
            logger.warning("Unknown method: %s (request_id=%s)", method, request_id)
            return make_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

        try:
            logger.debug("Handling request: %s (request_id=%s)", method, request_id)
            result = await handler(request_id, params)
            logger.debug("Request complete: %s (request_id=%s)", method, request_id)
            return make_response(request_id, result)
        except _ProtocolError as e:
            logger.warning("Protocol error in %s: [%d] %s", method, e.code, e.message)
            return make_error(request_id, e.code, e.message, e.data)
        except Exception as e:
            logger.error("Unhandled error in %s: %s", method, e, exc_info=True)
            return make_error(request_id, INTERNAL_ERROR, f"Internal error: {e}")

    async def handle_notification(
        self, method: str, params: Optional[dict[str, Any]]
    ) -> None:
        """Handle a JSON-RPC notification (no response expected)."""
        params = params or {}

        if method == "session/cancel":
            await self._handle_session_cancel(params)
        else:
            logger.debug("Ignoring unknown notification: %s", method)
        # Unknown notifications are silently ignored (per ACP spec)

    # ------------------------------------------------------------------
    # Method Handlers
    # ------------------------------------------------------------------

    async def _handle_initialize(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle `initialize` — version & capability negotiation."""
        self._client_capabilities = params.get("clientCapabilities", {})
        self._client_info = params.get("clientInfo", {})
        self._initialized = True

        client_name = self._client_info.get("name", "unknown")
        client_version = self._client_info.get("version", "unknown")
        logger.info(
            "Protocol initialized — client=%s/%s, capabilities=%s",
            client_name, client_version, list(self._client_capabilities.keys()),
        )

        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": {
                "loadSession": True,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": False,
                },
            },
            "agentInfo": AGENT_INFO,
            "authMethods": [],
        }

    async def _handle_session_new(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle `session/new` — create a new session."""
        cwd = params.get("cwd")
        if cwd:
            os.chdir(cwd)
            logger.debug("Changed working directory to %s", cwd)

        session = Session.create()
        self._session_repo.save(session)

        session_id_str = str(session.id)

        # Initialize mode for this session
        self._session_modes[session_id_str] = "vibe"

        logger.info("Session created: %s (cwd=%s)", session_id_str, cwd or os.getcwd())

        return {
            "sessionId": session_id_str,
            "configOptions": _build_config_options("vibe"),
        }

    async def _handle_session_load(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle `session/load` — replay session history then respond."""
        session_id_str = params.get("sessionId")
        if not session_id_str:
            raise _ProtocolError(INVALID_PARAMS, "sessionId is required")

        cwd = params.get("cwd")
        if cwd:
            os.chdir(cwd)
            logger.debug("Changed working directory to %s", cwd)

        try:
            session_id = UUID(session_id_str)
        except ValueError:
            raise _ProtocolError(INVALID_PARAMS, f"Invalid sessionId: {session_id_str}")

        session = self._session_repo.load(session_id)
        if session is None:
            logger.warning("Session not found: %s", session_id_str)
            raise _ProtocolError(SESSION_NOT_FOUND, f"Session '{session_id_str}' not found")

        # Initialize mode tracking (default to vibe)
        if session_id_str not in self._session_modes:
            self._session_modes[session_id_str] = "vibe"

        # Replay conversation history as session/update notifications
        runs = self._run_repo.list_for_session(session_id)
        logger.info("Session loaded: %s (replaying %d runs)", session_id_str, len(runs))
        for run in runs:
            # Replay input messages (user)
            for msg in run.input:
                text = msg.get_text()
                if text:
                    self._send(make_notification("session/update", {
                        "sessionId": session_id_str,
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"type": "text", "text": text},
                        },
                    }))

            # Replay output messages (agent)
            for msg in run.output:
                text = msg.get_text()
                if text:
                    self._send(make_notification("session/update", {
                        "sessionId": session_id_str,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": text},
                        },
                    }))

        current_mode = self._session_modes.get(session_id_str, "vibe")
        return {
            "configOptions": _build_config_options(current_mode),
        }

    async def _handle_session_prompt(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle `session/prompt` — execute a prompt turn with streaming updates."""
        session_id_str = params.get("sessionId")
        if not session_id_str:
            raise _ProtocolError(INVALID_PARAMS, "sessionId is required")

        prompt_blocks = params.get("prompt", [])
        if not prompt_blocks:
            raise _ProtocolError(INVALID_PARAMS, "prompt is required and must not be empty")

        try:
            session_id = UUID(session_id_str)
        except ValueError:
            raise _ProtocolError(INVALID_PARAMS, f"Invalid sessionId: {session_id_str}")

        session = self._session_repo.load(session_id)
        if session is None:
            raise _ProtocolError(SESSION_NOT_FOUND, f"Session '{session_id_str}' not found")

        # Extract text from prompt content blocks
        prompt_text = ""
        for block in prompt_blocks:
            if block.get("type") == "text":
                prompt_text += block.get("text", "")

        if not prompt_text:
            raise _ProtocolError(INVALID_PARAMS, "No text content in prompt")

        # Get current mode for this session
        current_mode: AgentMode = self._session_modes.get(session_id_str, "vibe")

        # Create Run for internal tracking with the session's current mode
        input_msg = AcpMessage.user(prompt_text)
        run = Run.create(
            agent_name="nora",
            input_messages=[input_msg],
            session_id=session.id,
            agent_mode=current_mode,
        )
        run.start()

        logger.info(
            "Run started: session=%s, run=%s, mode=%s, prompt_length=%d",
            session_id_str, run.run_id, current_mode, len(prompt_text),
        )

        # Set up cancellation
        cancel_hook = CancellationHook()
        self._cancel_hooks[session_id_str] = cancel_hook

        try:
            stop_reason = await self._execute_prompt(
                session, run, prompt_text, session_id_str, cancel_hook
            )
        finally:
            self._cancel_hooks.pop(session_id_str, None)

        logger.info("Run complete: session=%s, run=%s, stop_reason=%s", session_id_str, run.run_id, stop_reason)
        return {"stopReason": stop_reason}

    async def _handle_set_config_option(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle `session/set_config_option` — change a config value."""
        session_id_str = params.get("sessionId")
        if not session_id_str:
            raise _ProtocolError(INVALID_PARAMS, "sessionId is required")

        option_id = params.get("id")
        value = params.get("value")

        if option_id == "mode":
            if value not in _VALID_MODES:
                raise _ProtocolError(
                    INVALID_PARAMS,
                    f"Invalid mode: {value}. Must be one of: {', '.join(_VALID_MODES)}",
                )
            old_mode = self._session_modes.get(session_id_str, "vibe")
            self._session_modes[session_id_str] = value
            logger.info("Mode changed: session=%s, %s → %s", session_id_str, old_mode, value)
        else:
            raise _ProtocolError(INVALID_PARAMS, f"Unknown config option: {option_id}")

        # Return full config options state (per ACP spec)
        current_mode = self._session_modes.get(session_id_str, "vibe")
        return {
            "configOptions": _build_config_options(current_mode),
        }

    async def _handle_session_cancel(self, params: dict[str, Any]) -> None:
        """Handle `session/cancel` notification — cancel in-progress prompt.

        Per ACP spec, also cancels any pending permission requests.
        """
        session_id_str = params.get("sessionId", "")
        logger.info("Cancel requested: session=%s", session_id_str)

        hook = self._cancel_hooks.get(session_id_str)
        if hook:
            hook.cancel()
            logger.debug("Cancel hook triggered for session=%s", session_id_str)
        else:
            logger.debug("No active cancel hook for session=%s", session_id_str)

        # Cancel pending client requests (permission dialogs, etc.)
        if self._client is not None:
            from nora.acp.jsonrpc_client import JsonRpcClient
            if isinstance(self._client, JsonRpcClient):
                self._client.cancel_pending()
                logger.debug("Cancelled pending client requests for session=%s", session_id_str)

    # ------------------------------------------------------------------
    # Prompt Execution
    # ------------------------------------------------------------------

    async def _execute_prompt(
        self,
        session: Session,
        run: Run,
        prompt_text: str,
        session_id_str: str,
        cancel_hook: CancellationHook,
    ) -> str:
        """Execute a prompt turn, emitting session/update notifications.

        Returns the stop reason string.
        """
        # Load session history
        strands_history = self._run_repo.load_all_strands_messages(session.id)

        # Create agent
        agent = self._agent_service.create_agent(
            messages=strands_history,
            profile=self._profile,
            mode=run.agent_mode,
            hooks=[cancel_hook],
        )
        messages_before_run = len(agent.messages)

        # Track output
        output_chunks: list[str] = []
        tool_call_counter = 0
        # Map strands toolUseId -> ACP toolCallId
        tool_use_to_call_id: dict[str, str] = {}

        def on_stream(**kwargs: Any) -> None:
            nonlocal tool_call_counter

            if cancel_hook.cancelled:
                return

            if "data" in kwargs:
                chunk = kwargs["data"]
                output_chunks.append(chunk)
                # Emit agent_message_chunk
                self._send(make_notification("session/update", {
                    "sessionId": session_id_str,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": chunk},
                    },
                }))

            if "message" in kwargs:
                msg = kwargs["message"]
                msg_role = msg.get("role", "unknown")
                block_count = len(msg.get("content", []))
                logger.debug("Stream message: role=%s, blocks=%d", msg_role, block_count)

                if msg.get("role") == "assistant":
                    for block in msg.get("content", []):
                        # Emit thinking/reasoning content
                        if "reasoningContent" in block:
                            rc = block["reasoningContent"]
                            reasoning_text = ""
                            if isinstance(rc, dict):
                                rt = rc.get("reasoningText", {})
                                if isinstance(rt, dict):
                                    reasoning_text = rt.get("text", "")
                                elif isinstance(rt, str):
                                    reasoning_text = rt
                            if reasoning_text:
                                self._send(make_notification("session/update", {
                                    "sessionId": session_id_str,
                                    "update": {
                                        "sessionUpdate": "thought_message_chunk",
                                        "content": {"type": "text", "text": reasoning_text},
                                    },
                                }))

                        elif "toolUse" in block:
                            tu = block["toolUse"]
                            tool_call_counter += 1
                            tool_call_id = f"call_{tool_call_counter:03d}"
                            tool_name = tu.get("name", "unknown")
                            tool_input = tu.get("input", {})
                            tool_use_id = tu.get("toolUseId")

                            logger.info(
                                "Tool call: %s (call_id=%s, tool_use_id=%s)",
                                tool_name, tool_call_id, tool_use_id,
                            )

                            # Track mapping for later result correlation
                            if tool_use_id:
                                tool_use_to_call_id[tool_use_id] = tool_call_id

                            # Build tool call content with locations for file operations
                            tool_content: list[dict[str, Any]] = []
                            locations: list[dict[str, Any]] = []

                            # Add file location for file operation tools
                            file_path = tool_input.get("path")
                            if file_path and tool_name in (
                                "read_file", "write_file", "edit_file",
                                "explore_dir", "search_files",
                            ):
                                loc: dict[str, Any] = {"path": str(
                                    (Path(file_path)).resolve()
                                    if not Path(file_path).is_absolute()
                                    else Path(file_path)
                                )}
                                start_line = tool_input.get("start_line")
                                if start_line is not None:
                                    loc["line"] = start_line
                                locations.append(loc)

                            # Emit tool_call with rawInput, locations
                            update: dict[str, Any] = {
                                "sessionUpdate": "tool_call",
                                "toolCallId": tool_call_id,
                                "title": tool_name,
                                "kind": _tool_kind(tool_name),
                                "status": "in_progress",
                            }
                            if tool_input:
                                update["rawInput"] = tool_input
                            if locations:
                                update["locations"] = locations
                            if tool_content:
                                update["content"] = tool_content

                            self._send(make_notification("session/update", {
                                "sessionId": session_id_str,
                                "update": update,
                            }))

                elif msg.get("role") == "user":
                    for block in msg.get("content", []):
                        if "toolResult" in block:
                            tr = block["toolResult"]
                            tool_use_id = tr.get("toolUseId")
                            tool_call_id = tool_use_to_call_id.get(
                                tool_use_id, f"call_{tool_call_counter:03d}"
                            ) if tool_use_id else f"call_{tool_call_counter:03d}"

                            # Extract output text from toolResult content
                            raw_output: dict[str, Any] = {}
                            result_content = tr.get("content", [])
                            if result_content:
                                output_texts = []
                                for cb in result_content:
                                    if isinstance(cb, dict) and "text" in cb:
                                        output_texts.append(cb["text"])
                                if output_texts:
                                    raw_output["text"] = "\n".join(output_texts)

                            status = "failed" if tr.get("status") == "error" else "completed"

                            logger.debug(
                                "Tool result: call_id=%s, status=%s",
                                tool_call_id, status,
                            )

                            # Emit tool_call_update with rawOutput
                            update = {
                                "sessionUpdate": "tool_call_update",
                                "toolCallId": tool_call_id,
                                "status": status,
                            }
                            if raw_output:
                                update["rawOutput"] = raw_output

                            self._send(make_notification("session/update", {
                                "sessionId": session_id_str,
                                "update": update,
                            }))

        agent.callback_handler = on_stream

        # Get the event loop before entering the executor thread
        loop = asyncio.get_event_loop()

        invocation_state: dict[str, Any] = {
            "agent_mode": run.agent_mode,
            "cancel_hook": cancel_hook,
            "session_id": session_id_str,
            "event_loop": loop,
        }

        # Provide client interface to tools if available
        if self._client is not None:
            invocation_state["client"] = self._client

        # Run agent in executor

        def run_agent() -> Any:
            if cancel_hook.cancelled:
                return None
            return agent(prompt_text, invocation_state=invocation_state)

        try:
            result = await loop.run_in_executor(None, run_agent)
        except Exception as e:
            if cancel_hook.cancelled:
                logger.info("Run cancelled during execution: session=%s", session_id_str)
                run.confirm_cancel()
                self._save_run(session, run, agent, messages_before_run, output_chunks, result=None)
                return "cancelled"
            logger.error("Agent execution failed: session=%s, error=%s", session_id_str, e, exc_info=True)
            run.fail(
                AcpError(code=ErrorCode.SERVER_ERROR, message=str(e))
            )
            raise _ProtocolError(AGENT_ERROR, f"Agent execution failed: {e}")

        if cancel_hook.cancelled or result is None:
            logger.info("Run cancelled (post-execution): session=%s", session_id_str)
            run.confirm_cancel()
            self._save_run(session, run, agent, messages_before_run, output_chunks, result=result)
            return "cancelled"

        # Complete the run
        output_messages: list[AcpMessage] = []
        full_text = "".join(output_chunks)
        if full_text:
            output_messages.append(AcpMessage.agent(full_text))
        run.complete(output_messages)

        logger.debug(
            "Run output: session=%s, chunks=%d, total_chars=%d",
            session_id_str, len(output_chunks), len(full_text),
        )

        # If this was a plan mode run, emit the output as a plan update
        if run.agent_mode == "plan" and full_text:
            logger.info("Emitting plan update: session=%s", session_id_str)
            self._send(make_notification("session/update", {
                "sessionId": session_id_str,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [
                        {
                            "content": full_text,
                            "priority": "high",
                            "status": "completed",
                        },
                    ],
                },
            }))

        self._save_run(session, run, agent, messages_before_run, output_chunks, result=result)
        return "end_turn"

    def _save_run(
        self,
        session: Session,
        run: Run,
        agent: Any,
        messages_before_run: int,
        output_chunks: list[str],
        result: Any = None,
    ) -> None:
        """Persist run data, update token usage, and save session."""
        new_messages = list(agent.messages[messages_before_run:])
        self._run_repo.save(run, new_messages)

        # Extract and persist token usage
        token_usage = self._extract_token_usage(result)
        if token_usage.input_tokens > 0:
            session.metadata.token_usage = token_usage

        session.metadata.updated_at = datetime.now()
        if not session.metadata.name or session.metadata.name.startswith("Session "):
            for msg in run.input:
                text = msg.get_text()
                if text:
                    session.generate_name(text)
                    break
        self._session_repo.save(session)

    @staticmethod
    def _extract_token_usage(result: Any) -> TokenUsage:
        """Extract token usage from a Strands AgentResult.

        Tries the last cycle of the latest invocation first (most accurate
        context size), falls back to accumulated_usage.

        Args:
            result: AgentResult from agent() call (can be None).

        Returns:
            TokenUsage with extracted values.
        """
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        if result is not None and hasattr(result, "metrics"):
            metrics = result.metrics
            inv = metrics.latest_agent_invocation
            if inv and inv.cycles:
                last_cycle = inv.cycles[-1]
                input_tokens = last_cycle.usage.get("inputTokens", 0)
                output_tokens = last_cycle.usage.get("outputTokens", 0)
                total_tokens = last_cycle.usage.get("totalTokens", 0)
            elif metrics.accumulated_usage:
                input_tokens = metrics.accumulated_usage.get("inputTokens", 0)
                output_tokens = metrics.accumulated_usage.get("outputTokens", 0)
                total_tokens = metrics.accumulated_usage.get("totalTokens", 0)

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Import Path here to avoid circular imports at module level
from pathlib import Path


# Map tool names to ACP ToolKind categories (module-level constant)
_TOOL_KINDS: dict[str, str] = {
    "read_file": "read",
    "explore_dir": "read",
    "search_files": "read",
    "read_plugin": "read",
    "search_plugin": "read",
    "write_file": "edit",
    "edit_file": "edit",
    "write_plugin": "edit",
    "edit_plugin": "edit",
    "delete_plugin": "delete",
    "run_shell": "execute",
    "fetch_url": "fetch",
    "run_subagent": "think",
    "ask_user": "other",
}


def _tool_kind(tool_name: str) -> str:
    """Map a Nora tool name to an Agent Client Protocol ToolKind."""
    return _TOOL_KINDS.get(tool_name, "other")


class _ProtocolError(Exception):
    """Internal error with JSON-RPC error code."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
