"""Context window usage bar widget."""

from textual.reactive import reactive
from textual.widget import Widget
from rich.text import Text

from nora.config.constants import MODE_COLORS

# Dimmed versions of mode colors for unfilled segments
_DIM_COLORS = {
    "vibe": "rgb(0,80,80)",
    "plan": "rgb(80,80,0)",
    "edit": "rgb(0,80,0)",
}

BAR_WIDTH = 10
FILLED_CHAR = "╍"
UNFILLED_CHAR = "╌"


class ContextBar(Widget):
    """Displays context window usage as a 20-char progress bar.

    Filled segments use the current mode color; unfilled segments
    use a dimmed variant of the same hue. A percentage label is
    shown to the right of the bar.
    """

    DEFAULT_CSS = """
    ContextBar {
        height: 1;
        width: 1fr;
        text-align: right;
    }
    """

    input_tokens: reactive[int] = reactive(0)
    max_tokens: reactive[int] = reactive(200_000)
    mode: reactive[str] = reactive("vibe")

    def __init__(
        self,
        max_tokens: int = 200_000,
        mode: str = "vibe",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.max_tokens = max_tokens
        self.mode = mode

    def update_usage(self, input_tokens: int) -> None:
        """Update the bar with a new token count."""
        self.input_tokens = input_tokens

    def set_max_tokens(self, max_tokens: int) -> None:
        """Update the denominator (when model changes)."""
        self.max_tokens = max_tokens

    def set_mode(self, mode: str) -> None:
        """Update bar color (when mode changes)."""
        self.mode = mode

    def reset(self) -> None:
        """Reset to 0 (new session)."""
        self.input_tokens = 0

    def watch_input_tokens(self, _: int) -> None:
        self.refresh()

    def watch_max_tokens(self, _: int) -> None:
        self.refresh()

    def watch_mode(self, _: str) -> None:
        self.refresh()

    def _get_percentage(self) -> int:
        if self.max_tokens <= 0:
            return 0
        pct = (self.input_tokens / self.max_tokens) * 100
        return min(int(round(pct)), 100)

    def render(self) -> Text:
        pct = self._get_percentage()
        filled_count = round(BAR_WIDTH * pct / 100)
        unfilled_count = BAR_WIDTH - filled_count

        filled_color = MODE_COLORS.get(self.mode, "cyan")
        dim_color = _DIM_COLORS.get(self.mode, "rgb(0,80,80)")

        text = Text(justify="right")
        text.append(FILLED_CHAR * filled_count, style=f"bold {filled_color}")
        text.append(UNFILLED_CHAR * unfilled_count, style=dim_color)
        text.append(f" {pct}%", style="dim")
        return text
