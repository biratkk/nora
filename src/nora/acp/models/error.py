"""ACP Error model.

Aligned with ACP v0.2.0 OpenAPI spec.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """ACP error codes."""

    SERVER_ERROR = "server_error"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"


class AcpError(BaseModel):
    """ACP error response."""

    code: ErrorCode = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    data: Optional[dict[str, Any]] = Field(default=None, description="Additional error data")
