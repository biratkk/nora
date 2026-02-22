"""ACP HTTP Server — JSON-RPC 2.0 over HTTP.

Accepts JSON-RPC 2.0 requests via POST and returns JSON-RPC responses.
Notifications from the agent (session/update) are streamed via SSE when
the request triggers a prompt turn, or buffered and returned inline.

Start with `nora acp --port 8000`.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from nora.acp.jsonrpc import (
    INVALID_REQUEST,
    PARSE_ERROR,
    make_error,
)
from nora.acp.local_client import LocalClient
from nora.acp.protocol import ProtocolHandler

logger = logging.getLogger("nora.acp.server")


def create_app(profile: Optional[str] = None) -> FastAPI:
    """Create the ACP FastAPI application with JSON-RPC 2.0 endpoint."""
    _configure_logging()

    app = FastAPI(
        title="Nora ACP Server",
        description="Agent Client Protocol (JSON-RPC 2.0) server for Nora",
        version="0.1.0",
    )

    logger.info("Creating ACP HTTP server (profile=%s)", profile)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/")
    async def jsonrpc_endpoint(request: Request) -> JSONResponse | EventSourceResponse:
        """Single JSON-RPC 2.0 endpoint.

        All ACP methods are dispatched through this endpoint.
        For session/prompt requests, responses may include streamed
        notifications via SSE if Accept: text/event-stream is set.
        """
        # Parse request body
        try:
            data = await request.json()
        except Exception:
            logger.warning("Failed to parse request JSON")
            return JSONResponse(
                content=make_error(None, PARSE_ERROR, "Invalid JSON"),
            )

        if not isinstance(data, dict):
            logger.warning("Invalid request: not a JSON object")
            return JSONResponse(
                content=make_error(None, INVALID_REQUEST, "Request must be a JSON object"),
            )

        method = data.get("method")
        if not method:
            logger.warning("Missing 'method' field in request")
            return JSONResponse(
                content=make_error(data.get("id"), INVALID_REQUEST, "Missing 'method' field"),
            )

        params = data.get("params")
        request_id = data.get("id")

        # Check if client wants SSE streaming
        accept = request.headers.get("accept", "")
        wants_stream = "text/event-stream" in accept and method == "session/prompt"

        logger.debug(
            "HTTP request: method=%s, id=%s, stream=%s",
            method, request_id, wants_stream,
        )

        if wants_stream and request_id is not None:
            # Stream mode: return SSE with notifications + final response
            return await _handle_streaming(profile, request_id, method, params)

        # Standard JSON-RPC: buffer notifications, return single response
        if request_id is not None:
            # Request — expects response
            notifications: list[dict[str, Any]] = []

            def collect_notification(msg: dict[str, Any]) -> None:
                notifications.append(msg)

            handler = ProtocolHandler(
                send_notification=collect_notification,
                client=LocalClient(),
                profile=profile,
            )
            response = await handler.handle_request(request_id, method, params)

            # If there were notifications, include them in a _meta field
            if notifications:
                if "result" in response and response["result"] is not None:
                    if isinstance(response["result"], dict):
                        response["result"]["_meta"] = {"notifications": notifications}

            return JSONResponse(content=response)
        else:
            # Notification — no response
            handler = ProtocolHandler(
                send_notification=lambda msg: None,
                client=LocalClient(),
                profile=profile,
            )
            await handler.handle_notification(method, params)
            return JSONResponse(content={}, status_code=204)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        """Health check endpoint (convenience, not part of JSON-RPC)."""
        return {"status": "ok", "protocol": "agent-client-protocol", "version": "0.1.0"}

    return app


async def _handle_streaming(
    profile: Optional[str],
    request_id: Any,
    method: str,
    params: Optional[dict[str, Any]],
) -> EventSourceResponse:
    """Handle a streaming request via SSE.

    Notifications are sent as SSE events, and the final JSON-RPC response
    is sent as the last event with event type 'response'.
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def send_notification(msg: dict[str, Any]) -> None:
        queue.put_nowait(msg)

    handler = ProtocolHandler(
        send_notification=send_notification,
        client=LocalClient(),
        profile=profile,
    )

    async def process() -> None:
        try:
            response = await handler.handle_request(request_id, method, params)
            # Send final response through queue
            queue.put_nowait({"_final_response": True, **response})
        except Exception as e:
            logger.error("SSE handler error: method=%s, error=%s", method, e, exc_info=True)
            error_resp = make_error(request_id, -32603, str(e))
            queue.put_nowait({"_final_response": True, **error_resp})
        finally:
            queue.put_nowait(None)  # sentinel

    async def event_generator():
        # Start processing in background
        task = asyncio.create_task(process())

        while True:
            msg = await queue.get()
            if msg is None:
                break

            is_final = msg.pop("_final_response", False)
            event_type = "notification" if not is_final else "response"

            yield {
                "event": event_type,
                "data": json.dumps(msg, default=str),
            }

        await task

    return EventSourceResponse(event_generator())


def _configure_logging() -> None:
    """Set up logging for ACP HTTP server.
    
    Respects NORA_LOG_LEVEL environment variable (default: INFO).
    """
    level_name = os.environ.get("NORA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    acp_logger = logging.getLogger("nora.acp")
    acp_logger.setLevel(level)

    if not acp_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        acp_logger.addHandler(handler)

    acp_logger.propagate = False
