"""Utils package."""

from nora.utils.files import (
    load_gitignore,
    scan_files,
    consecutive_score,
    is_path_valid,
    is_binary_file,
    MAX_FILE_SIZE,
)
from nora.utils.fuzzy import fuzzy_filter
from nora.utils.text import generate_plan_description, truncate_with_ellipsis

__all__ = [
    "load_gitignore",
    "scan_files",
    "consecutive_score",
    "is_path_valid",
    "is_binary_file",
    "MAX_FILE_SIZE",
    "fuzzy_filter",
    "generate_plan_description",
    "truncate_with_ellipsis",
]
