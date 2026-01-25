"""Autocomplete widget."""

from pathlib import Path
from dataclasses import dataclass
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual.widget import Widget

from nora.utils.files import scan_files, consecutive_score

COMMANDS = ["/new", "/switch", "/model", "/add-plugin", "/exit"]
MAX_RESULTS = 10


@dataclass
class AutocompleteItem:
    value: str
    display: str
    score: int = 0


class AutocompleteWidget(Widget):
    DEFAULT_CSS = """
    AutocompleteWidget {
        layer: autocomplete;
        width: 100%;
        height: auto;
        max-height: 12;
        border: round $primary;
        padding: 0 1;
        display: none;
    }
    AutocompleteWidget.visible { display: block; }
    AutocompleteWidget .item { width: 100%; }
    AutocompleteWidget .item.selected { background: $primary; }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.items: list[AutocompleteItem] = []
        self.selected_index = 0
        self._file_cache: list[str] = []

    def compose(self) -> ComposeResult:
        yield Vertical()

    def show(self, items: list[AutocompleteItem]) -> None:
        self.items = items
        self.selected_index = 0
        self._render_items()
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")
        self.items = []

    def _render_items(self) -> None:
        container = self.query_one(Vertical)
        container.remove_children()
        if not self.items:
            container.mount(Static("[dim]No matches[/dim]", classes="item"))
            return
        for i, item in enumerate(self.items):
            cls = "item selected" if i == self.selected_index else "item"
            container.mount(Static(item.display, classes=cls, markup=False))

    def move_selection(self, delta: int) -> None:
        if not self.items:
            return
        self.selected_index = (self.selected_index + delta) % len(self.items)
        self._render_items()

    def get_selected(self) -> AutocompleteItem | None:
        if self.items and 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def cache_files(self) -> None:
        self._file_cache = scan_files(Path.cwd())

    def get_command_matches(self, query: str) -> list[AutocompleteItem]:
        q = query.lower()
        return [AutocompleteItem(c, c) for c in COMMANDS if c.lower().startswith(q)]

    def get_file_matches(self, query: str) -> list[AutocompleteItem]:
        q = query.lower()
        matches = [(f, consecutive_score(f.lower(), q)) for f in self._file_cache if q in f.lower()]
        matches.sort(key=lambda x: (-x[1], x[0]))
        matches = matches[:MAX_RESULTS]
        names = [Path(m[0]).name for m in matches]
        name_counts = {n: names.count(n) for n in names}
        return [
            AutocompleteItem(
                m[0],
                Path(m[0]).name if name_counts[Path(m[0]).name] == 1 else m[0],
                m[1]
            )
            for m in matches
        ]
