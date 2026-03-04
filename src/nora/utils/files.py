"""File scanning and gitignore handling."""

import os
from pathlib import Path
from typing import Optional

import pathspec

MAX_FILE_SIZE = 1024 * 1024  # 1MB

# Module-level cache for compiled gitignore patterns, keyed by cwd string.
_gitignore_cache: dict[str, Optional[pathspec.PathSpec]] = {}


def clear_gitignore_cache() -> None:
    """Clear the cached gitignore patterns.
    
    Call after modifying a .gitignore file to ensure subsequent
    path validations use fresh patterns.
    """
    _gitignore_cache.clear()


def load_gitignore(cwd: Path) -> Optional[pathspec.PathSpec]:
    """
    Load and compile gitignore patterns from a directory tree.
    
    Results are cached by cwd. Use clear_gitignore_cache() to invalidate.
    
    Walks the directory tree and collects patterns from all .gitignore files,
    prefixing patterns with their relative directory path.
    
    Args:
        cwd: The root directory to start scanning from.
        
    Returns:
        Compiled PathSpec for matching, or None if no patterns found.
    """
    key = str(cwd)
    if key in _gitignore_cache:
        return _gitignore_cache[key]

    patterns: list[str] = []
    
    for root, _, _ in os.walk(cwd):
        gitignore_path = Path(root) / ".gitignore"
        if not gitignore_path.exists():
            continue
            
        try:
            rel_root = Path(root).relative_to(cwd)
            prefix = f"{rel_root}/" if str(rel_root) != "." else ""
            
            for line in gitignore_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(prefix + line)
        except OSError:
            continue
    
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns) if patterns else None
    _gitignore_cache[key] = spec
    return spec


def scan_files(cwd: Path) -> list[str]:
    """
    Scan directory for all non-ignored, non-binary files.
    
    Excludes .git directories, gitignored files, and files exceeding MAX_FILE_SIZE.
    
    Args:
        cwd: The root directory to scan.
        
    Returns:
        List of relative file paths as strings.
    """
    files: list[str] = []
    spec = load_gitignore(cwd)
    
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
            
        rel = path.relative_to(cwd)
        if spec and spec.match_file(str(rel)):
            continue
            
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
            
        files.append(str(rel))
    
    return files


def consecutive_score(text: str, query: str) -> int:
    """
    Score based on consecutive character match.
    
    Returns the length of query if found as substring, otherwise 0.
    Used for file path matching where exact substring matches are preferred.
    
    Args:
        text: Text to search in.
        query: Query to find.
        
    Returns:
        Length of query if found, 0 otherwise.
    """
    idx = text.find(query)
    return len(query) if idx >= 0 else 0


def is_path_valid(path: str, cwd: Path) -> tuple[bool, str]:
    """
    Validate that a path is within cwd and not gitignored.
    
    Args:
        path: Relative path to validate.
        cwd: Current working directory.
        
    Returns:
        Tuple of (is_valid, error_message). Error message is empty if valid.
    """
    resolved = (cwd / path).resolve()
    
    if not str(resolved).startswith(str(cwd)):
        return False, f"Path '{path}' is outside current directory"
    
    if ".git" in resolved.parts:
        return False, f"Path '{path}' is in .git directory"
    
    spec = load_gitignore(cwd)
    if spec and spec.match_file(path):
        return False, f"Path '{path}' is gitignored"
    
    return True, ""


def is_binary_file(path: Path) -> bool:
    """
    Check if a file appears to be binary.
    
    Reads the first 8KB and checks for null bytes.
    
    Args:
        path: Path to the file to check.
        
    Returns:
        True if file appears to be binary, False otherwise.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except OSError:
        return False
