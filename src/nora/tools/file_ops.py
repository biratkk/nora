"""File operation tools for Nora."""

from pathlib import Path
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


@tool(name="Read")
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read contents of a file in current working directory.
    
    Args:
        path: Relative path to the file
        start_line: Starting line number (1-indexed, inclusive). If not provided, starts from beginning.
        end_line: Ending line number (1-indexed, inclusive). If not provided, reads to end of file.
    """
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"File '{path}' not found")
    if is_binary_file(resolved):
        raise ValueError(f"File '{path}' is binary")
    
    content = resolved.read_text()
    
    MAX_LINES = 2000
    
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
    
    old_content = resolved.read_text() if resolved.exists() else ""
    approval = tool_context.interrupt("diff-confirm", reason={"path": path, "old": old_content, "new": content, "reason": reason})
    if approval == "reject":
        raise ValueError(f"Tool call rejected by user")
    if approval.lower() != "y":
        if approval.lower() != "n":
            return f"Write to {path} cancelled. User suggestion: {approval}"
        return f"Write to {path} cancelled by user"
    
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
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
    if not resolved.exists():
        raise FileNotFoundError(f"File '{path}' not found")
    if is_binary_file(resolved):
        raise ValueError(f"File '{path}' is binary")
    
    file_content = resolved.read_text()
    if old_text not in file_content:
        raise ValueError(f"Text not found in '{path}'")
    
    new_content = file_content.replace(old_text, new_text, 1)
    approval = tool_context.interrupt("diff-confirm", reason={"path": path, "old": file_content, "new": new_content, "reason": reason})
    if approval == "reject":
        raise ValueError(f"Tool call rejected by user")
    if approval.lower() != "y":
        if approval.lower() != "n":
            return f"Update to {path} cancelled. User suggestion: {approval}"
        return f"Update to {path} cancelled by user"
    
    resolved.write_text(new_content)
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
    
    try:
        result = subprocess.run(
            ["grep", "-rn", "--exclude-dir=.git", pattern, path],
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
