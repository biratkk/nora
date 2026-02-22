"""ACP stdio transport — newline-delimited JSON-RPC 2.0 over stdin/stdout.

Reads JSON-RPC messages from stdin (one per line), dispatches them to the
protocol handler, and writes responses/notifications to stdout.

Supports bidirectional communication: the agent can send requests to the
client (fs/read_text_file, terminal/create, session/request_permission, etc.)
and receive responses back.

All log output goes to stderr to keep stdout clean for protocol messages.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Optional

from nora.acp.jsonrpc import (
    INVALID_REQUEST,
    PARSE_ERROR,
    make_error,
)
from nora.acp.jsonrpc_client import JsonRpcClient
from nora.acp.protocol import ProtocolHandler

logger = logging.getLogger("nora.acp.stdio")


def _write_message(msg: dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout as a single line."""
    line = json.dumps(msg, separators=(",", ":"), default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    # Log outgoing messages at trace level (debug is too noisy for every chunk)
    method = msg.get("method", "")
    if method:
        logger.debug("→ notification: %s", method)
    elif "result" in msg:
        logger.debug("→ response: id=%s", msg.get("id"))
    elif "error" in msg:
        logger.debug("→ error: id=%s code=%s", msg.get("id"), msg.get("error", {}).get("code"))


def _log(text: str) -> None:
    """Write a log message to stderr."""
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def _is_response(data: dict[str, Any]) -> bool:
    """Check if a message is a JSON-RPC response (not a request/notification).

    A response has 'id' and either 'result' or 'error', but no 'method'.
    """
    return "id" in data and "method" not in data and ("result" in data or "error" in data)


async def _process_line(
    handler: ProtocolHandler,
    jsonrpc_client: JsonRpcClient,
    line: str,
) -> None:
    """Parse and dispatch a single JSON-RPC message line.

    Routes responses to the JsonRpcClient (for Agent→Client request
    correlation) and requests/notifications to the ProtocolHandler.
    """
    line = line.strip()
    if not line:
        return

    # Parse JSON
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON-RPC message: %s", e)
        _write_message(make_error(None, PARSE_ERROR, f"Parse error: {e}"))
        return

    if not isinstance(data, dict):
        logger.warning("Invalid JSON-RPC message: not a JSON object")
        _write_message(make_error(None, INVALID_REQUEST, "Request must be a JSON object"))
        return

    # Route: response from client → JsonRpcClient pending requests
    if _is_response(data):
        handled = jsonrpc_client.handle_response(data)
        if not handled:
            logger.warning("Unmatched response id=%s", data.get("id"))
        else:
            logger.debug("← response: id=%s", data.get("id"))
        return

    # Route: request or notification from client → ProtocolHandler
    method = data.get("method")
    if not method:
        logger.warning("Missing 'method' field in message: id=%s", data.get("id"))
        _write_message(make_error(
            data.get("id"), INVALID_REQUEST, "Missing 'method' field"
        ))
        return

    params = data.get("params")

    # Request (has id) vs Notification (no id)
    if "id" in data:
        logger.debug("← request: %s (id=%s)", method, data["id"])
        response = await handler.handle_request(data["id"], method, params)
        _write_message(response)
    else:
        logger.debug("← notification: %s", method)
        await handler.handle_notification(method, params)


async def _run_loop(profile: Optional[str] = None) -> None:
    """Main async loop: read lines from stdin, dispatch, respond on stdout."""
    # Create the JSON-RPC client for Agent→Client requests
    jsonrpc_client = JsonRpcClient(send_message=_write_message)

    handler = ProtocolHandler(
        send_notification=_write_message,
        client=jsonrpc_client,
        profile=profile,
    )

    logger.info("Nora ACP stdio transport ready")
    _log("Nora ACP stdio transport ready")

    loop = asyncio.get_event_loop()

    # Read stdin in a thread to avoid blocking the event loop
    reader = asyncio.StreamReader()

    def _feed_stdin() -> None:
        """Read stdin in a background thread, feed to StreamReader."""
        try:
            for line in sys.stdin:
                loop.call_soon_threadsafe(reader.feed_data, line.encode())
        except Exception as e:
            logger.debug("stdin reader ended: %s", e)
        finally:
            loop.call_soon_threadsafe(reader.feed_eof)
            logger.debug("stdin EOF — feed complete")

    # Start stdin reader thread
    import threading
    stdin_thread = threading.Thread(target=_feed_stdin, daemon=True)
    stdin_thread.start()

    # Process messages
    # Each line is processed as a separate task so the event loop stays
    # responsive.  This allows session/cancel notifications to arrive
    # while a long-running session/prompt request is in flight.
    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                logger.info("stdin closed — shutting down")
                break  # EOF
            line = line_bytes.decode("utf-8")
            asyncio.create_task(_process_line(handler, jsonrpc_client, line))
        except Exception as e:
            logger.error("Error processing message: %s", e, exc_info=True)


def run_stdio(profile: Optional[str] = None) -> None:
    """Entry point for stdio transport. Blocks until stdin closes."""
    # Configure logging to stderr so stdout stays clean for JSON-RPC
    _configure_logging()
    logger.info("Starting stdio transport (profile=%s)", profile)
    asyncio.run(_run_loop(profile))


def _configure_logging() -> None:
    """Set up logging for ACP — all output goes to stderr.
    
    Respects NORA_LOG_LEVEL environment variable (default: INFO).
    """
    import os
    level_name = os.environ.get("NORA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Configure the nora.acp logger hierarchy
    acp_logger = logging.getLogger("nora.acp")
    acp_logger.setLevel(level)

    # Only add handler if none exist (avoid duplicates on re-entry)
    if not acp_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        acp_logger.addHandler(handler)

    # Prevent propagation to root logger (which might write to stdout)
    acp_logger.propagate = False
