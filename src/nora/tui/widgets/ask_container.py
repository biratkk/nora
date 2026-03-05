"""AskContainer widget for inline structured question UI.

Replaces #input-container and #info-container while active.
Resolves an asyncio.Future with formatted Q/A answers when complete.
"""

import asyncio
from typing import Optional

from textual import events
from textual.containers import Container, Horizontal
from textual.widgets import Static


class AskContainer(Container, can_focus=True):
    """Inline container for structured multiple-choice questions.

    Mounts in place of #input-container and #info-container.
    Supports 1–7 questions with tab navigation, option selection,
    and a free-text "Other" option on each question.
    """

    DEFAULT_CSS = """
    AskContainer {
        height: auto;
        max-height: 33vh;
        padding: 1;
        background: #1a1a1a;
        border-left: solid yellow;
    }
    AskContainer .ask-tabs {
        height: auto;
        padding: 0 0 0 0;
        margin-bottom: 1;
    }
    AskContainer .ask-question {
        padding: 0 0 0 0;
        margin-bottom: 1;
        text-style: bold;
    }
    AskContainer .ask-option {
        height: 1;
        padding: 0 0 0 2;
    }
    AskContainer .ask-option-selected {
        height: 1;
        padding: 0 0 0 0;
        text-style: bold;
    }
    AskContainer .ask-tooltip {
        height: 1;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        questions: list[dict],
        future: asyncio.Future,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._questions = questions
        self._future = future
        self._current_tab = 0
        self._selected_indices: list[int] = [0] * len(questions)
        self._answers: list[Optional[str]] = [None] * len(questions)
        self._other_text: list[str] = [""] * len(questions)
        self._is_multi = len(questions) > 1

    @property
    def _current_options(self) -> list[str]:
        """Get the predefined options for the current question."""
        return self._questions[self._current_tab].get("options", [])

    @property
    def _total_options(self) -> int:
        """Total options including the 'Other' option."""
        return len(self._current_options) + 1

    @property
    def _is_on_other(self) -> bool:
        """Whether the highlight is on the 'Other' option."""
        return self._selected_indices[self._current_tab] == self._total_options - 1

    @property
    def _is_last_tab(self) -> bool:
        """Whether the current tab is the last question."""
        return self._current_tab == len(self._questions) - 1

    def compose(self):
        if self._is_multi:
            yield Static("", id="ask-tabs", classes="ask-tabs")
        yield Static("", id="ask-question", classes="ask-question")
        yield Container(id="ask-options")
        yield Static("", id="ask-tooltip", classes="ask-tooltip")

    def on_mount(self) -> None:
        self._render_current()
        self.focus()

    def _render_current(self) -> None:
        """Re-render the entire widget state for the current tab."""
        # Tabs
        if self._is_multi:
            tabs_widget = self.query_one("#ask-tabs", Static)
            tab_parts = []
            for i in range(len(self._questions)):
                answered = self._answers[i] is not None
                active = i == self._current_tab
                tick = "✓ " if answered else ""
                label = f"{tick}Q{i + 1}"
                if active:
                    tab_parts.append(f"[bold yellow]\\[{label}][/bold yellow]")
                elif answered:
                    tab_parts.append(f"[green]\\[{label}][/green]")
                else:
                    tab_parts.append(f"[dim]\\[{label}][/dim]")
            tabs_widget.update("  ".join(tab_parts))

        # Question text
        question_text = self._questions[self._current_tab].get("question", "")
        self.query_one("#ask-question", Static).update(question_text)

        # Options
        options_container = self.query_one("#ask-options", Container)
        options_container.remove_children()

        options = self._current_options
        selected = self._selected_indices[self._current_tab]

        for i, opt in enumerate(options):
            if i == selected:
                options_container.mount(
                    Static(f"› {opt}", classes="ask-option-selected")
                )
            else:
                options_container.mount(
                    Static(opt, classes="ask-option")
                )

        # "Other" option (always last)
        other_idx = len(options)
        other_text = self._other_text[self._current_tab]
        other_display = f"Other: {other_text}" if other_text else "Other:"
        if selected == other_idx:
            options_container.mount(
                Static(f"› {other_display}", classes="ask-option-selected")
            )
        else:
            options_container.mount(
                Static(other_display, classes="ask-option")
            )

        # Tooltip
        self._render_tooltip()

    def _render_tooltip(self) -> None:
        """Update the tooltip based on current position."""
        parts = ["[dim]\\[↑↓] Navigate[/dim]"]

        if not self._is_multi:
            # Single question
            parts.append("[dim]\\[Enter] Submit[/dim]")
        elif self._is_last_tab:
            parts.append("[dim]\\[Enter] Submit[/dim]")
            if self._current_tab > 0:
                parts.append("[dim]\\[Backspace] Previous question[/dim]")
        else:
            parts.append("[dim]\\[Enter] Next question[/dim]")
            if self._current_tab > 0:
                parts.append("[dim]\\[Backspace] Previous question[/dim]")

        self.query_one("#ask-tooltip", Static).update("  ".join(parts))

    def on_key(self, event: events.Key) -> None:
        event.prevent_default()
        event.stop()

        tab = self._current_tab
        selected = self._selected_indices[tab]

        if event.key == "up":
            if selected > 0:
                # If leaving "Other", clear its text
                if self._is_on_other:
                    self._other_text[tab] = ""
                self._selected_indices[tab] = selected - 1
                self._render_current()

        elif event.key == "down":
            if selected < self._total_options - 1:
                self._selected_indices[tab] = selected + 1
                self._render_current()

        elif event.key == "enter":
            self._lock_answer()
            if self._is_last_tab or not self._is_multi:
                self._submit_all()
            else:
                self._current_tab += 1
                # If revisiting a previously answered question, keep its selection
                self._render_current()

        elif event.key == "backspace":
            if self._is_on_other and self._other_text[tab]:
                # Delete character from Other text
                self._other_text[tab] = self._other_text[tab][:-1]
                self._render_current()
            elif self._current_tab > 0 and not (self._is_on_other and self._other_text[tab]):
                # Go back to previous question
                self._current_tab -= 1
                self._render_current()

        elif event.character and event.is_printable and self._is_on_other:
            # Type into "Other" field
            self._other_text[tab] += event.character
            self._render_current()

    def _lock_answer(self) -> None:
        """Lock in the currently selected option as the answer."""
        tab = self._current_tab
        selected = self._selected_indices[tab]
        options = self._current_options

        if selected < len(options):
            self._answers[tab] = options[selected]
        else:
            # "Other" option
            other_text = self._other_text[tab].strip()
            self._answers[tab] = f"Other: {other_text}" if other_text else "Other:"

    def _submit_all(self) -> None:
        """Format all answers and resolve the future."""
        lines = []
        for i, q in enumerate(self._questions):
            lines.append(f"Q: {q.get('question', '')}")
            lines.append(f"A: {self._answers[i]}")
            if i < len(self._questions) - 1:
                lines.append("")
        result = "\n".join(lines)
        if not self._future.done():
            self._future.set_result(result)
