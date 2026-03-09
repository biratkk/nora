"""Text processing utilities."""

import re
from typing import Final


PLAN_DESCRIPTION_PATTERN: Final[re.Pattern] = re.compile(r"[^a-z0-9\s]")


def generate_plan_description(content: str, max_length: int = 20) -> str:
    """
    Generate a short description from plan content.
    
    .. deprecated::
        Use ``nora.tools.plan.generate_plan_name()`` instead for LLM-based naming.
    
    Extracts the first line, removes non-alphanumeric characters,
    and joins the first few words with hyphens.
    
    Args:
        content: Full plan content.
        max_length: Maximum length of description.
        
    Returns:
        Hyphenated description suitable for filenames.
    """
    first_line = content.strip().split("\n")[0]
    clean = PLAN_DESCRIPTION_PATTERN.sub("", first_line.lower())
    words = clean.split()[:4]
    return "-".join(words)[:max_length] or "plan"


def truncate_with_ellipsis(text: str, max_length: int) -> str:
    """
    Truncate text and add ellipsis if needed.
    
    Args:
        text: Text to truncate.
        max_length: Maximum length including ellipsis.
        
    Returns:
        Truncated text with ellipsis if shortened.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
