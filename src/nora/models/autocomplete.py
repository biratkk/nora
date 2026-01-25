"""Autocomplete models for TUI input assistance."""

from dataclasses import dataclass


@dataclass
class AutocompleteItem:
    """
    Represents an item in the autocomplete dropdown.
    
    Used for both command and file path autocompletion.
    """
    
    value: str
    display: str
    score: int = 0
