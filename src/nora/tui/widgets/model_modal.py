"""Model selection modal with fuzzy search."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, Input

from nora.core.agent import MODEL_NAMES
from nora.tui.utils import fuzzy_filter
from nora.tui.widgets.modal import BaseModal


class ModelItem(Static):
    """A model item in the selection list."""
    
    DEFAULT_CSS = """
    ModelItem {
        height: auto;
        border: round $surface-lighten-1;
        padding: 0 1;
    }
    ModelItem.selected { border: round $primary; }
    """
    
    def __init__(self, model_id: str, display_name: str) -> None:
        super().__init__(display_name)
        self.model_id = model_id


class ModelSelectorModal(BaseModal):
    """Modal for selecting AI models with fuzzy search."""
    
    def status_text(self) -> str:
        return "Type to search  ↑/↓ navigate  Enter select  Esc close"

    DEFAULT_CSS = """
    ModelSelectorModal > Container { width: 50%; max-height: 60%; }
    ModelSelectorModal .title { text-style: bold; margin-bottom: 1; }
    ModelSelectorModal .search-input { margin-bottom: 1; }
    ModelSelectorModal VerticalScroll { height: auto; }
    ModelSelectorModal .no-matches { color: $text-muted; text-align: center; padding: 2; }
    """

    def __init__(self, current_model: str):
        super().__init__()
        self.current_model = current_model
        self.models = list(MODEL_NAMES.keys())
        self.filtered_models = self.models.copy()
        self.selected_index = self.models.index(current_model) if current_model in self.models else 0
        self.search_query = ""

    def compose_content(self) -> ComposeResult:
        yield Static("Select Model", classes="title")
        yield Input(placeholder="Type to filter...", classes="search-input", id="model-search")
        with VerticalScroll(id="model-list"):
            for i, model_id in enumerate(self.filtered_models):
                item = ModelItem(model_id, MODEL_NAMES[model_id])
                if i == self.selected_index:
                    item.add_class("selected")
                yield item

    def _get_model_search_text(self, model_id: str) -> str:
        """Get searchable text for a model (name + id)."""
        return f"{MODEL_NAMES[model_id]} {model_id}"

    def _filter_models(self) -> None:
        """Filter models based on current search query."""
        self.filtered_models = fuzzy_filter(
            self.search_query,
            self.models,
            self._get_model_search_text
        )
        self.selected_index = 0

    async def _refresh_model_list(self) -> None:
        """Re-render the model list after filtering."""
        scroll = self.query_one("#model-list", VerticalScroll)
        await scroll.remove_children()
        
        if not self.filtered_models:
            await scroll.mount(Static("No matches\n[dim]Press Enter to clear search[/dim]", classes="no-matches"))
        else:
            for i, model_id in enumerate(self.filtered_models):
                item = ModelItem(model_id, MODEL_NAMES[model_id])
                if i == self.selected_index:
                    item.add_class("selected")
                await scroll.mount(item)

    def _update_selection(self) -> None:
        """Update visual selection highlighting."""
        if not self.filtered_models:
            return
        
        items = list(self.query(ModelItem))
        for i, item in enumerate(items):
            if i == self.selected_index:
                item.add_class("selected")
                item.scroll_visible()
            else:
                item.remove_class("selected")

    def on_mount(self) -> None:
        """Focus search input when modal opens."""
        self.query_one("#model-search", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "model-search":
            self.search_query = event.value
            self._filter_models()
            await self._refresh_model_list()

    async def on_key(self, event) -> None:
        if event.key in ("up", "ctrl+p"):
            if self.filtered_models:
                self.selected_index = (self.selected_index - 1) % len(self.filtered_models)
                self._update_selection()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self.filtered_models:
                self.selected_index = (self.selected_index + 1) % len(self.filtered_models)
                self._update_selection()
            event.prevent_default()
        elif event.key == "enter":
            if not self.filtered_models:
                # Clear search when no matches
                search_input = self.query_one("#model-search", Input)
                search_input.value = ""
                self.search_query = ""
                self._filter_models()
                await self._refresh_model_list()
            else:
                self.dismiss(self.filtered_models[self.selected_index])
            event.prevent_default()
