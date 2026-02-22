"""File operation tools for Nora."""

import asyncio
from pathlib import Path
from typing import Any

from strands import tool
from strands.types.tools import ToolContext

from nora.utils.files import load_gitignore, is_binary_file


def _validate_path(path: str) -> Path:
    """Validate path is within CWD, not gitignored, and not in .git."""
    cwd = Path.cwd()
    resolved = (cwd / path).resolve()
    if not str(resolved).startswith(str(cwd)):
        raise ValueError(f"Path '{path}' is outside current directory")
    
    # Always ignore .git folder
    if ".git" in resolved.parts:
        raise ValueError(f"Path '{path}' is in .git directory")
    
    spec = load_gitignore(cwd)
    if spec and spec.match_file(path):
        raise ValueError(f"Path '{path}' is gitignored")
    
    return resolved


def _run_async(invocation_state: dict[str, Any], coro: Any) -> Any:
    """Run an async coroutine from a sync tool, using the event loop from invocation_state."""
    loop = invocation_state.get("event_loop")
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    # Fallback: create a new event loop (shouldn't happen in normal flow)
    return asyncio.run(coro)


def _get_client(tool_context: ToolContext) -> tuple[dict[str, Any], Any]:
    """Extract invocation_state and client from tool context.
    
    Returns:
        (invocation_state, client) — client may be None if not in ACP mode.
    """
    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    client = invocation_state.get("client")
    return invocation_state, client


@tool(name="Read", context=True)
def read_file(
    tool_context: ToolContext,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read contents of a file in current working directory.
    
    Args:
        path: Relative path to the file
        start_line: Starting line number (1-indexed, inclusive). If not provided, starts from beginning.
        end_line: Ending line number (1-indexed, inclusive). If not provided, reads to end of file.
    """
    resolved = _validate_path(path)
    invocation_state, client = _get_client(tool_context)
    
    MAX_LINES = 2000
    
    if client is not None:
        # Delegate to client interface
        abs_path = str(resolved)
        limit = None
        if start_line is not None and end_line is not None:
            limit = end_line - start_line + 1
        elif start_line is not None:
            limit = None  # Read from start_line to end
        elif end_line is not None:
            start_line = 1
            limit = end_line
        
        content = _run_async(invocation_state, client.read_text_file(
            session_id=invocation_state.get("session_id", ""),
            path=abs_path,
            line=start_line,
            limit=limit,
        ))
        
        # Apply truncation for large files
        if start_line is None and end_line is None:
            lines = content.splitlines(keepends=True)
            if len(lines) > MAX_LINES:
                truncated = "".join(lines[:MAX_LINES])
                return f"{truncated}\n\n... ({len(lines) - MAX_LINES} more lines truncated. Use start_line/end_line to read specific sections.)"
        
        return content
    
    # Direct filesystem access (TUI/CLI mode)
    if not resolved.exists():
        raise FileNotFoundError(f"File '{path}' not found")
    if is_binary_file(resolved):
        raise ValueError(f"File '{path}' is binary")
    
    content = resolved.read_text()
    
    # If no line range specified, return full content (truncated if huge)
    if start_line is None and end_line is None:
        lines = content.splitlines(keepends=True)
        if len(lines) > MAX_LINES:
            truncated = "".join(lines[:MAX_LINES])
            return f"{truncated}\n\n... ({len(lines) - MAX_LINES} more lines truncated. Use start_line/end_line to read specific sections.)"
        return content
    
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    
    # Default values: start from 1, end at last line
    start = start_line if start_line is not None else 1
    end = end_line if end_line is not None else total_lines
    
    # Validate line numbers
    if start < 1:
        raise ValueError(f"start_line must be >= 1, got {start}")
    if end < start:
        raise ValueError(f"end_line ({end}) must be >= start_line ({start})")
    if start > total_lines:
        raise ValueError(f"start_line ({start}) exceeds file length ({total_lines} lines)")
    
    # Clamp end to file length
    end = min(end, total_lines)
    
    # Convert to 0-indexed and slice
    selected_lines = lines[start - 1:end]
    return "".join(selected_lines)


@tool(name="Write", context=True)
def write_file(tool_context: ToolContext, path: str, content: str, reason: str) -> str:
    """Write content to a file in current working directory.
    
    Args:
        path: Relative path to the file
        content: Content to write
        reason: One-line summary of the purpose of this write
    """
    resolved = _validate_path(path)
    invocation_state, client = _get_client(tool_context)
    mode = invocation_state.get("agent_mode", "vibe")
    
    # Read old content for diff display
    old_content = ""
    if resolved.exists():
        if client is not None:
            old_content = _run_async(invocation_state, client.read_text_file(
                session_id=invocation_state.get("session_id", ""),
                path=str(resolved),
            ))
        else:
            old_content = resolved.read_text()
    
    # Permission check for vibe mode
    if mode not in ("edit", "act"):
        if client is not None:
            # Use client permission flow
            outcome = _request_write_permission(invocation_state, client, path, old_content, content, reason, tool_use_id=tool_context.tool_use.get("toolUseId"))
            if outcome == "reject":
                raise ValueError("Tool call rejected by user")
            if outcome != "allow":
                return f"Write to {path} cancelled. User suggestion: {outcome}" if outcome != "cancel" else f"Write to {path} cancelled by user"
        else:
            # Use interrupt flow (TUI)
            approval = tool_context.interrupt("diff-confirm", reason={"path": path, "old": old_content, "new": content, "reason": reason})
            if approval == "reject":
                raise ValueError("Tool call rejected by user")
            if approval.lower() != "y":
                if approval.lower() != "n":
                    return f"Write to {path} cancelled. User suggestion: {approval}"
                return f"Write to {path} cancelled by user"
    
    # Perform the write
    if client is not None:
        _run_async(invocation_state, client.write_text_file(
            session_id=invocation_state.get("session_id", ""),
            path=str(resolved),
            content=content,
        ))
    else:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        # Notify TUI to show DiffBlock
        diff_callback = invocation_state.get("diff_callback")
        if diff_callback and mode in ("edit", "act"):
            tool_use_id = tool_context.tool_use.get("toolUseId")
            diff_callback(tool_use_id, path, old_content, content, reason)
    
    return f"Successfully wrote to {path}"


@tool(name="Edit", context=True)
def edit_file(tool_context: ToolContext, path: str, old_text: str, new_text: str, reason: str) -> str:
    """Edit existing file by replacing text.
    
    Args:
        path: Relative path to the file
        old_text: Text to find and replace
        new_text: Replacement text
        reason: One-line summary of the purpose of this edit
    """
    resolved = _validate_path(path)
    invocation_state, client = _get_client(tool_context)
    mode = invocation_state.get("agent_mode", "vibe")
    
    # Read current content
    if client is not None:
        file_content = _run_async(invocation_state, client.read_text_file(
            session_id=invocation_state.get("session_id", ""),
            path=str(resolved),
        ))
    else:
        if not resolved.exists():
            raise FileNotFoundError(f"File '{path}' not found")
        if is_binary_file(resolved):
            raise ValueError(f"File '{path}' is binary")
        file_content = resolved.read_text()
    
    if old_text not in file_content:
        raise ValueError(f"Text not found in '{path}'")
    
    new_content = file_content.replace(old_text, new_text, 1)
    
    # Permission check for vibe mode
    if mode not in ("edit", "act"):
        if client is not None:
            outcome = _request_write_permission(invocation_state, client, path, file_content, new_content, reason, tool_use_id=tool_context.tool_use.get("toolUseId"))
            if outcome == "reject":
                raise ValueError("Tool call rejected by user")
            if outcome != "allow":
                return f"Update to {path} cancelled. User suggestion: {outcome}" if outcome != "cancel" else f"Update to {path} cancelled by user"
        else:
            approval = tool_context.interrupt("diff-confirm", reason={"path": path, "old": file_content, "new": new_content, "reason": reason})
            if approval == "reject":
                raise ValueError("Tool call rejected by user")
            if approval.lower() != "y":
                if approval.lower() != "n":
                    return f"Update to {path} cancelled. User suggestion: {approval}"
                return f"Update to {path} cancelled by user"
    
    # Perform the edit
    if client is not None:
        _run_async(invocation_state, client.write_text_file(
            session_id=invocation_state.get("session_id", ""),
            path=str(resolved),
            content=new_content,
        ))
    else:
        resolved.write_text(new_content)
        # Notify TUI to show DiffBlock
        diff_callback = invocation_state.get("diff_callback")
        if diff_callback and mode in ("edit", "act"):
            tool_use_id = tool_context.tool_use.get("toolUseId")
            diff_callback(tool_use_id, path, file_content, new_content, reason)
    
    return f"Successfully edited {path}"


@tool(name="Explore")
def explore_dir(path: str = ".") -> str:
    """List contents of a directory.
    
    Args:
        path: Path to directory (relative or absolute), defaults to current directory
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Directory '{path}' not found")
    if not resolved.is_dir():
        raise ValueError(f"'{path}' is not a directory")
    
    entries = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = [e for e in entries if e.name != ".git"]
    lines = [f"{'d' if e.is_dir() else 'f'}  {e.name}" for e in entries]
    return "\n".join(lines) if lines else "(empty directory)"


@tool(name="Search")
def search_files(pattern: str, path: str = ".") -> str:
    """Search for text pattern in files recursively using grep.
    
    Args:
        pattern: Text or regex pattern to search for
        path: File or directory to search in, defaults to current directory (recursive)
    """
    import subprocess
    
    MAX_LINES = 200
    
    # Build exclude flags from .gitignore patterns
    cwd = Path.cwd()
    exclude_dirs = [".git"]
    exclude_files: list[str] = []
    
    gitignore_path = cwd / ".gitignore"
    if gitignore_path.exists():
        for line in gitignore_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip trailing slashes to get the name
            clean = line.rstrip("/")
            if line.endswith("/"):
                # Directory pattern
                exclude_dirs.append(clean)
            else:
                # Could be file or dir — exclude as both
                exclude_dirs.append(clean)
                exclude_files.append(clean)
    
    try:
        cmd = ["grep", "-rn"]
        for d in exclude_dirs:
            cmd.extend(["--exclude-dir", d])
        for f in exclude_files:
            cmd.extend(["--exclude", f])
        cmd.extend([pattern, path])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout.strip()
        if not output:
            return f"No matches found for '{pattern}'"
        
        lines = output.split("\n")
        if len(lines) > MAX_LINES:
            truncated = "\n".join(lines[:MAX_LINES])
            return f"{truncated}\n\n... ({len(lines) - MAX_LINES} more matches truncated. Narrow your search pattern or target a specific path.)"
        return output
    except subprocess.TimeoutExpired:
        return "Search timed out"
    except FileNotFoundError:
        return "grep not available"


def _request_write_permission(
    invocation_state: dict[str, Any],
    client: Any,
    path: str,
    old_content: str,
    new_content: str,
    reason: str,
    tool_use_id: str | None = None,
) -> str:
    """Request write permission via client interface.
    
    Returns:
        "allow" — user approved
        "cancel" — user cancelled
        "reject" — user rejected
        other string — user suggestion
    """
    from nora.acp.client_interface import PermissionOption, PermissionOutcome
    
    message = f"Write to {path}: {reason}"
    options = [
        PermissionOption("allow", "allow_once", "Allow", f"Write to {path}"),
        PermissionOption("reject", "reject_once", "Reject", "Reject this write"),
    ]
    
    outcome: PermissionOutcome = _run_async(invocation_state, client.request_permission(
        session_id=invocation_state.get("session_id", ""),
        message=message,
        options=options,
        tool_call_id=tool_use_id,
        tool_name="write_file",
    ))
    
    if outcome.is_cancelled:
        return "cancel"
    if outcome.option_id == "reject":
        return "reject"
    return "allow"
