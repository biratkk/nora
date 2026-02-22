"""JSON-RPC 2.0 message models for the Agent Client Protocol.

Provides typed models for requests, responses, notifications, and errors
per the JSON-RPC 2.0 specification used by agentclientprotocol.com.
"""

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


# --- Standard JSON-RPC 2.0 error codes ---

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Application error range: -32000 to -32099
SESSION_NOT_FOUND = -32000
SESSION_ALREADY_EXISTS = -32001
AGENT_ERROR = -32010


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request (expects a response)."""

    jsonrpc: str = "2.0"
    id: Union[int, str]
    method: str
    params: Optional[dict[str, Any]] = None


class JsonRpcNotification(BaseModel):
    """JSON-RPC 2.0 notification (no response expected)."""

    jsonrpc: str = "2.0"
    method: str
    params: Optional[dict[str, Any]] = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 success response."""

    jsonrpc: str = "2.0"
    id: Union[int, str]
    result: Any = None


class JsonRpcErrorResponse(BaseModel):
    """JSON-RPC 2.0 error response."""

    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    error: JsonRpcError


def make_response(request_id: Union[int, str], result: Any = None) -> dict[str, Any]:
    """Build a JSON-RPC success response dict."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(
    request_id: Optional[Union[int, str]],
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response dict."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    resp: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "error": error}
    return resp


def make_notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC notification dict (no id)."""
    return {"jsonrpc": "2.0", "method": method, "params": params}


def parse_message(data: dict[str, Any]) -> Union[JsonRpcRequest, JsonRpcNotification]:
    """Parse a raw dict into a typed JSON-RPC message.

    If the dict has an 'id' field, it's a request; otherwise a notification.
    """
    if "id" in data:
        return JsonRpcRequest(**data)
    return JsonRpcNotification(**data)
