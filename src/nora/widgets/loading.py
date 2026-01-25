"""Loading widget."""

from typing import Literal
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

LoadingStyle = Literal["spinner", "bar", "pulse", "wave"]

ANIMATIONS: dict[LoadingStyle, list[str]] = {
    "spinner": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "bar": ["▱▱▱▱▱", "▰▱▱▱▱", "▰▰▱▱▱", "▰▰▰▱▱", "▰▰▰▰▱", "▰▰▰▰▰"],
    "pulse": ["◐", "◓", "◑", "◒"],
    "wave": ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂"],
}


class LoadingWidget(Widget):
    """
    Animated loading indicator with multiple styles.
    
    Displays an animation with an optional message while operations are in progress.
    """
    
    DEFAULT_CSS = """
    LoadingWidget { height: auto; width: auto; padding: 0 1; }
    """
    
    frame: reactive[int] = reactive(0)

    def __init__(
        self, 
        message: str = "Thinking", 
        style: LoadingStyle = "pulse", 
        speed: float = 0.1,
        **kwargs
    ) -> None:
        """
        Initialize the loading widget.
        
        Args:
            message: Message to display next to animation.
            style: Animation style.
            speed: Animation frame interval in seconds.
            **kwargs: Additional widget arguments.
        """
        super().__init__(**kwargs)
        self.message = message
        self.loading_style = style
        self.speed = speed

    def on_mount(self) -> None:
        """Start the animation timer on mount."""
        self.set_interval(self.speed, self._advance)

    def _advance(self) -> None:
        """Advance to the next animation frame."""
        self.frame = (self.frame + 1) % len(ANIMATIONS[self.loading_style])

    def watch_frame(self, _: int) -> None:
        """Refresh display when frame changes."""
        self.refresh()

    def render(self) -> Text:
        """Render the current animation frame."""
        frames = ANIMATIONS[self.loading_style]
        text = Text()
        text.append(frames[self.frame], style="bold rgb(100,100,0)")
        text.append(f" {self.message}...", style="dim")
        return text
