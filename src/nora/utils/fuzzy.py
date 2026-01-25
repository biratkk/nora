"""Fuzzy matching utilities."""

from typing import Callable, TypeVar

from rapidfuzz import fuzz


T = TypeVar("T")


def fuzzy_filter(
    query: str, 
    items: list[T], 
    key_fn: Callable[[T], str], 
    threshold: int = 50
) -> list[T]:
    """
    Filter and sort items by fuzzy match score.
    
    Uses partial ratio matching to find items where the query appears
    as a substring with some tolerance for typos.
    
    Args:
        query: Search query string.
        items: List of items to filter.
        key_fn: Function to extract searchable text from each item.
        threshold: Minimum score (0-100) to include item.
        
    Returns:
        Filtered and sorted list of items, best matches first.
    """
    if not query.strip():
        return items
    
    scored: list[tuple[T, int]] = []
    query_lower = query.lower()
    
    for item in items:
        search_text = key_fn(item).lower()
        score = fuzz.partial_ratio(query_lower, search_text)
        if score > threshold:
            scored.append((item, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored]
