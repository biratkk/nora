"""TUI widgets package."""

from nora.tui.widgets.chat import ChatMessage, ToolCallBlock, ToolIndicator, SubagentBlock, ShellBlock, ShellMessage, DiffBlock
from nora.tui.widgets.autocomplete import AutocompleteWidget, AutocompleteItem
from nora.tui.widgets.loading import LoadingWidget
from nora.tui.widgets.input import MarkdownInput
from nora.tui.widgets.confirmation import ToolConfirmModal
from nora.tui.widgets.modal import BaseModal
from nora.tui.widgets.model_modal import ModelSelectorModal
from nora.tui.widgets.switch_modal import SwitchModal
from nora.tui.widgets.context_bar import ContextBar
from nora.tui.widgets.ask_container import AskContainer
from nora.screens.diff_modal import DiffModal

__all__ = ["ChatMessage", "ToolCallBlock", "ToolIndicator", "SubagentBlock", "ShellBlock", "ShellMessage", "DiffBlock", "AutocompleteWidget", "AutocompleteItem", "LoadingWidget", "MarkdownInput", "ToolConfirmModal", "BaseModal", "ModelSelectorModal", "DiffModal", "SwitchModal", "ContextBar", "AskContainer"]
