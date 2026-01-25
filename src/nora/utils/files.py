"""File scanning and gitignore handling."""

import os
from pathlib import Path
import pathspec

MAX_FILE_SIZE = 1024 * 1024  # 1MB


def load_gitignore(cwd: Path) -> pathspec.PathSpec | None:
    patterns = []
    for root, _, _ in os.walk(cwd):
        gi = Path(root) / ".gitignore"
        if not gi.exists():
            continue
        try:
            rel_root = Path(root).relative_to(cwd)
            prefix = str(rel_root) + "/" if str(rel_root) != "." else ""
            for line in gi.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(prefix + line)
        except OSError:
            continue
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns) if patterns else None


def scan_files(cwd: Path) -> list[str]:
    files = []
    spec = load_gitignore(cwd)
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        # Skip .git directory
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
    idx = text.find(query)
    return len(query) if idx >= 0 else 0
