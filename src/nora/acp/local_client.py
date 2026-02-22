"""Local client implementation — direct filesystem and subprocess access.

Used in TUI/CLI mode where Nora has direct access to the filesystem and
can execute commands locally. This preserves existing behavior while
conforming to the ClientInterface abstraction.
"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from nora.acp.client_interface import (
    ClientInterface,
    PermissionOption,
    PermissionOutcome,
    TerminalExitResult,
    TerminalInfo,
    TerminalOutput,
)

logger = logging.getLogger("nora.acp.local_client")


class LocalClient(ClientInterface):
    """Client that performs all operations locally.

    Filesystem calls go directly to the OS. Terminal operations use
    subprocess.Popen. Permission requests auto-approve (the TUI layer
    can override this with its own interactive logic).
    """

    def __init__(self) -> None:
        self._terminals: dict[str, _LocalTerminal] = {}

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
        """Read a text file from the local filesystem."""
        logger.debug("read_text_file: path=%s, line=%s, limit=%s", path, line, limit)
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = p.read_text()

        if line is not None:
            lines = content.splitlines(keepends=True)
            start_idx = line - 1  # Convert 1-based to 0-based
            if start_idx < 0:
                start_idx = 0
            if limit is not None:
                selected = lines[start_idx : start_idx + limit]
            else:
                selected = lines[start_idx:]
            content = "".join(selected)

        return content

    async def write_text_file(
        self,
        session_id: str,
        path: str,
        content: str,
    ) -> None:
        """Write a text file to the local filesystem. Creates parent dirs."""
        logger.debug("write_text_file: path=%s, content_length=%d", path, len(content))
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

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
        """Start a command as a local subprocess."""
        terminal_id = f"term_{uuid4().hex[:12]}"

        cmd = [command] + (args or [])
        logger.info("terminal_create: id=%s, cmd=%s, cwd=%s", terminal_id, cmd, cwd)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            env=env,
        )

        terminal = _LocalTerminal(
            process=process,
            output_byte_limit=output_byte_limit,
        )
        self._terminals[terminal_id] = terminal

        return TerminalInfo(terminal_id=terminal_id)

    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalOutput:
        """Get current accumulated output from a local terminal."""
        terminal = self._get_terminal(terminal_id)

        # Read any new output without blocking
        terminal.drain_output()

        exit_status = None
        if terminal.process.poll() is not None:
            exit_status = terminal.process.returncode

        return TerminalOutput(
            output=terminal.accumulated_output,
            truncated=terminal.truncated,
            exit_status=exit_status,
        )

    async def terminal_wait_for_exit(
        self,
        session_id: str,
        terminal_id: str,
    ) -> TerminalExitResult:
        """Block until the local subprocess exits."""
        terminal = self._get_terminal(terminal_id)

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, terminal.process.wait)

        # Drain remaining output
        terminal.drain_output()

        return TerminalExitResult(exit_code=exit_code)

    async def terminal_kill(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Terminate the local subprocess."""
        logger.debug("terminal_kill: id=%s", terminal_id)
        terminal = self._get_terminal(terminal_id)
        terminal.process.terminate()
        try:
            terminal.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Terminal %s did not exit after terminate, sending kill", terminal_id)
            terminal.process.kill()

    async def terminal_release(
        self,
        session_id: str,
        terminal_id: str,
    ) -> None:
        """Kill and clean up a local terminal."""
        logger.debug("terminal_release: id=%s", terminal_id)
        terminal = self._terminals.pop(terminal_id, None)
        if terminal is None:
            return

        if terminal.process.poll() is None:
            terminal.process.terminate()
            try:
                terminal.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Terminal %s did not exit after terminate, sending kill", terminal_id)
                terminal.process.kill()

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
        """Auto-approve permission requests in local mode.

        The TUI layer overrides this behavior with interactive dialogs.
        In headless/local mode, we auto-select the first "allow" option.
        """
        for opt in options:
            if opt.kind.startswith("allow"):
                logger.debug("Auto-approved permission: %s (option=%s)", message[:80], opt.option_id)
                return PermissionOutcome(outcome="selected", option_id=opt.option_id)

        # No allow options — cancel
        logger.debug("Permission denied (no allow options): %s", message[:80])
        return PermissionOutcome(outcome="cancelled")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_terminal(self, terminal_id: str) -> "_LocalTerminal":
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise ValueError(f"Unknown terminal: {terminal_id}")
        return terminal


class _LocalTerminal:
    """Wraps a subprocess.Popen with output accumulation."""

    def __init__(
        self,
        process: subprocess.Popen,
        output_byte_limit: Optional[int] = None,
    ) -> None:
        self.process = process
        self.output_byte_limit = output_byte_limit
        self.accumulated_output = ""
        self.truncated = False

    def drain_output(self) -> None:
        """Read available output from stdout without blocking."""
        if self.process.stdout is None:
            return

        import select
        import sys

        # Use non-blocking read approach
        while True:
            # Check if there's data available
            if self.process.poll() is not None:
                # Process exited — read remaining output
                remaining = self.process.stdout.read()
                if remaining:
                    self._append_output(remaining)
                break

            try:
                # Try to read a line with a small timeout
                line = self.process.stdout.readline()
                if not line:
                    break
                self._append_output(line)
            except Exception:
                break

    def _append_output(self, text: str) -> None:
        """Append text to accumulated output, respecting byte limit."""
        if self.truncated:
            return

        self.accumulated_output += text

        if self.output_byte_limit and len(self.accumulated_output.encode()) > self.output_byte_limit:
            self.truncated = True
