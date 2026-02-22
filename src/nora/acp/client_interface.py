"""Client interface for Agent Client Protocol Agent→Client callbacks.

Defines the abstract interface that tools use to access filesystem,
terminal, and permission operations. Implementations:
- LocalClient: direct filesystem/subprocess access (TUI/CLI mode)
- JsonRpcClient: delegates to the ACP client over JSON-RPC (ACP mode)
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class PermissionOutcome:
    """Result of a permission request."""

    def __init__(self, outcome: str, option_id: Optional[str] = None) -> None:
        self.outcome = outcome  # "selected" or "cancelled"
        self.option_id = option_id  # Only set when outcome == "selected"

    @property
    def is_selected(self) -> bool:
        return self.outcome == "selected"

    @property
    def is_cancelled(self) -> bool:
        return self.outcome == "cancelled"


class PermissionOption:
    """A single option in a permission request."""

    def __init__(
        self,
        option_id: str,
        kind: str,
        title: str,
        description: Optional[str] = None,
    ) -> None:
        self.option_id = option_id
        self.kind = kind  # "allow_once", "allow_always", "reject_once", "reject_always"
        self.title = title
        self.description = description

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "optionId": self.option_id,
            "kind": self.kind,
            "name": self.title,
        }
        return d


class TerminalInfo:
    """Information about a created terminal."""

    def __init__(self, terminal_id: str) -> None:
        self.terminal_id = terminal_id


class TerminalOutput:
    """Output from a terminal."""

    def __init__(
        self,
        output: str,
        truncated: bool = False,
        exit_status: Optional[int] = None,
    ) -> None:
        self.output = output
        self.truncated = truncated
        self.exit_status = exit_status


class TerminalExitResult:
    """Result of waiting for a terminal to exit."""

    def __init__(
        self,
        exit_code: Optional[int] = None,
        signal: Optional[str] = None,
    ) -> None:
        self.exit_code = exit_code
        self.signal = signal


class ClientInterface(ABC):
    """Abstract interface for Agent→Client operations.

    The Agent Client Protocol requires the agent to request the client
    (IDE/editor) to perform filesystem, terminal, and permission operations.
    This interface abstracts those operations so tools can work identically
    regardless of whether the client is local (TUI) or remote (JSON-RPC).
    """

    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------

    @abstractmethod
    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Read a text file.

        Args:
            session_id: ACP session identifier.
            path: Absolute file path.
            line: 1-based start line (optional).
            limit: Maximum lines to read (optional).

        Returns:
            File content as string.
        """
        ...

    @abstractmethod
    async def write_text_file(
        self,
        session_id: str,
        path: str,
        content: str,
    ) -> None:
        """Write a text file. Creates the file if it doesn't exist.

        Args:
            session_id: ACP session identifier.
            path: Absolute file path.
            content: File content to write.
        """
        ...

    # ------------------------------------------------------------------
    # Terminal
    # ------------------------------------------------------------------

    @abstractmethod
    async def terminal_create(
        self,
        session_id: str,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        output_byte_limit: Optional[int] = None,
    ) -> TerminalInfo:
        """Start a command in a new terminal.

        Args:
            session_id: ACP session identifier.
            command: Program to execute.
            args: Arguments for the command.
            env: Environment variables.
            cwd: Working directory.
            output_byte_limit: Max bytes to capture.

        Returns:
            TerminalInfo with the terminal ID.
        """
        ...

    @abstractmethod
    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalOutput:
        """Get current output from a terminal.

        Args:
            session_id: ACP session identifier.
            terminal_id: Terminal identifier.

        Returns:
            TerminalOutput with current output, truncation flag, and exit status.
        """
        ...

    @abstractmethod
    async def terminal_wait_for_exit(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalExitResult:
        """Block until the terminal command exits.

        Args:
            session_id: ACP session identifier.
            terminal_id: Terminal identifier.

        Returns:
            TerminalExitResult with exit code and/or signal.
        """
        ...

    @abstractmethod
    async def terminal_kill(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Terminate the terminal command. Terminal stays valid for output reads.

        Args:
            session_id: ACP session identifier.
            terminal_id: Terminal identifier.
        """
        ...

    @abstractmethod
    async def terminal_release(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Kill the command and release all terminal resources.

        After this call, the terminal ID becomes invalid.

        Args:
            session_id: ACP session identifier.
            terminal_id: Terminal identifier.
        """
        ...

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    @abstractmethod
    async def request_permission(
        self,
        session_id: str,
        message: str,
        options: list[PermissionOption],
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> PermissionOutcome:
        """Request permission from the client/user.

        Args:
            session_id: ACP session identifier.
            message: Human-readable description of what permission is for.
            options: Available permission options.
            tool_call_id: ACP tool call ID (for linking permission to a tool call).
            tool_name: Name of the tool requesting permission.

        Returns:
            PermissionOutcome indicating selection or cancellation.
        """
        ...
