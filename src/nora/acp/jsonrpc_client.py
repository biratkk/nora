"""JSON-RPC client implementation — delegates operations to the ACP client.

Used in ACP mode (stdio/HTTP) where the agent sends JSON-RPC 2.0 requests
back to the client (IDE/editor) for filesystem, terminal, and permission
operations. The client responds with JSON-RPC 2.0 responses.
"""

import asyncio
import logging
from itertools import count
from typing import Any, Optional

from nora.acp.client_interface import (
    ClientInterface,
    PermissionOption,
    PermissionOutcome,
    TerminalExitResult,
    TerminalInfo,
    TerminalOutput,
)

logger = logging.getLogger("nora.acp.jsonrpc_client")


# Type alias for the function that sends a JSON-RPC message to the client
MessageSender = Any  # Callable[[dict[str, Any]], None]


class JsonRpcClient(ClientInterface):
    """Client that delegates all operations to the ACP client via JSON-RPC.

    Sends Agent→Client requests over the transport (stdio or HTTP) and
    waits for responses. Uses asyncio.Future for correlating request IDs
    to responses.
    """

    def __init__(self, send_message: MessageSender) -> None:
        """Initialize with a message sender function.

        Args:
            send_message: Callable that sends a JSON-RPC message dict to
                the client (writes to stdout for stdio, etc.).
        """
        self._send = send_message
        self._id_counter = count(start=10000)  # Start high to avoid collisions with client IDs
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}

    def handle_response(self, msg: dict[str, Any]) -> bool:
        """Handle an incoming JSON-RPC response from the client.

        Called by the transport layer when a message with an 'id' and
        'result'/'error' (but no 'method') is received.

        Args:
            msg: The JSON-RPC response dict.

        Returns:
            True if the message was handled (matched a pending request),
            False otherwise.
        """
        msg_id = msg.get("id")
        if msg_id is None:
            return False

        future = self._pending.pop(msg_id, None)
        if future is None:
            return False

        if "error" in msg:
            err = msg["error"]
            logger.warning(
                "Client error response: id=%s, code=%s, message=%s",
                msg_id, err.get("code"), err.get("message"),
            )
            future.set_exception(JsonRpcClientError(
                code=msg["error"].get("code", -1),
                message=msg["error"].get("message", "Unknown error"),
            ))
        else:
            logger.debug("Client response received: id=%s", msg_id)
            future.set_result(msg.get("result", {}))

        return True

    def cancel_pending(self) -> None:
        """Cancel all pending requests. Called during session cancellation."""
        count = len(self._pending)
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        if count:
            logger.info("Cancelled %d pending client requests", count)

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response.

        Args:
            method: JSON-RPC method name.
            params: Method parameters.

        Returns:
            The result from the JSON-RPC response.

        Raises:
            JsonRpcClientError: If the client responds with an error.
        """
        request_id = next(self._id_counter)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        logger.debug("Client request: %s (id=%s)", method, request_id)
        self._send(message)

        try:
            result = await future
            logger.debug("Client request complete: %s (id=%s)", method, request_id)
            return result
        except asyncio.CancelledError:
            logger.debug("Client request cancelled: %s (id=%s)", method, request_id)
            self._pending.pop(request_id, None)
            raise

    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------

    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Request the client to read a text file via fs/read_text_file."""
        logger.debug("fs/read_text_file: path=%s, line=%s, limit=%s", path, line, limit)
        params: dict[str, Any] = {
            "sessionId": session_id,
            "path": path,
        }
        if line is not None:
            params["line"] = line
        if limit is not None:
            params["limit"] = limit

        result = await self._request("fs/read_text_file", params)
        return result.get("content", "")

    async def write_text_file(
        self,
        session_id: str,
        path: str,
        content: str,
    ) -> None:
        """Request the client to write a text file via fs/write_text_file."""
        logger.debug("fs/write_text_file: path=%s, content_length=%d", path, len(content))
        await self._request("fs/write_text_file", {
            "sessionId": session_id,
            "path": path,
            "content": content,
        })

    # ------------------------------------------------------------------
    # Terminal
    # ------------------------------------------------------------------

    async def terminal_create(
        self,
        session_id: str,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        output_byte_limit: Optional[int] = None,
    ) -> TerminalInfo:
        """Request the client to create a terminal via terminal/create."""
        logger.info("terminal/create: command=%s, args=%s, cwd=%s", command, args, cwd)
        params: dict[str, Any] = {
            "sessionId": session_id,
            "command": command,
        }
        if args is not None:
            params["args"] = args
        if env is not None:
            params["env"] = env
        if cwd is not None:
            params["cwd"] = cwd
        if output_byte_limit is not None:
            params["outputByteLimit"] = output_byte_limit

        result = await self._request("terminal/create", params)
        return TerminalInfo(terminal_id=result["terminalId"])

    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalOutput:
        """Request terminal output via terminal/output."""
        result = await self._request("terminal/output", {
            "sessionId": session_id,
            "terminalId": terminal_id,
        })
        return TerminalOutput(
            output=result.get("output", ""),
            truncated=result.get("truncated", False),
            exit_status=result.get("exitStatus"),
        )

    async def terminal_wait_for_exit(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalExitResult:
        """Wait for terminal exit via terminal/wait_for_exit."""
        result = await self._request("terminal/wait_for_exit", {
            "sessionId": session_id,
            "terminalId": terminal_id,
        })
        return TerminalExitResult(
            exit_code=result.get("exitCode"),
            signal=result.get("signal"),
        )

    async def terminal_kill(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Kill terminal command via terminal/kill."""
        await self._request("terminal/kill", {
            "sessionId": session_id,
            "terminalId": terminal_id,
        })

    async def terminal_release(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Release terminal via terminal/release."""
        await self._request("terminal/release", {
            "sessionId": session_id,
            "terminalId": terminal_id,
        })

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    async def request_permission(
        self,
        session_id: str,
        message: str,
        options: list[PermissionOption],
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> PermissionOutcome:
        """Request permission from the client via session/request_permission."""
        option_ids = [opt.option_id for opt in options]
        logger.info("request_permission: message=%r, options=%s", message[:100], option_ids)

        params: dict[str, Any] = {
            "sessionId": session_id,
            "toolCall": {
                "toolCallId": tool_call_id or "unknown",
                "title": message,
                "kind": "execute" if tool_name in ("run_shell", "Shell") else "edit",
                "status": "pending",
            },
            "options": [opt.to_dict() for opt in options],
        }

        result = await self._request("session/request_permission", params)

        outcome_data = result.get("outcome", {})
        outcome = PermissionOutcome(
            outcome=outcome_data.get("outcome", "cancelled"),
            option_id=outcome_data.get("optionId"),
        )
        logger.info("Permission result: outcome=%s, option_id=%s", outcome.outcome, outcome.option_id)
        return outcome


class JsonRpcClientError(Exception):
    """Error returned by the ACP client in a JSON-RPC error response."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.error_message = message
