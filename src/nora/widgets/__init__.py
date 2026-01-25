"""Reusable Textual widgets - re-exports from tui/widgets for flat structure."""

# Re-export from existing locations for new flat import structure
from nora.tui.widgets.chat import ChatMessage, ToolCallBlock, ToolIndicator, SubagentBlock, ShellBlock
from nora.tui.widgets.autocomplete import AutocompleteWidget, AutocompleteItem
from nora.tui.widgets.loading import LoadingWidget
from nora.tui.widgets.input import MarkdownInput
from nora.tui.widgets.modal import BaseModal

__all__ = [
    "ChatMessage",
    "ToolCallBlock",
    "ToolIndicator",
    "SubagentBlock",
    "ShellBlock",
    "AutocompleteWidget",
    "AutocompleteItem",
    "LoadingWidget",
    "MarkdownInput",
    "BaseModal",
]
