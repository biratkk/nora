"""Utility functions for TUI components."""

from typing import Callable, TypeVar

from rapidfuzz import fuzz

T = TypeVar("T")


def fuzzy_filter(query: str, items: list[T], key_fn: Callable[[T], str], threshold: int = 50) -> list[T]:
    """Filter and sort items by fuzzy match score.
    
    Args:
        query: Search query string
        items: List of items to filter
        key_fn: Function to extract search text from each item
        threshold: Minimum score to include item (default 50)
        
    Returns:
        Filtered and sorted list of items (best matches first)
    """
    if not query.strip():
        return items
    
    scored = []
    for item in items:
        search_text = key_fn(item)
        score = fuzz.partial_ratio(query.lower(), search_text.lower())
        if score > threshold:
            scored.append((item, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored]
