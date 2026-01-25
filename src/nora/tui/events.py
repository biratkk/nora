"""TUI event handlers."""

from pathlib import Path
from textual.widgets import Input

from nora.tui.widgets import AutocompleteWidget, MarkdownInput


def try_cmd_autocomplete(text: str, ac: AutocompleteWidget) -> bool:
    if not text.startswith("/"):
        return False
    ac.show(ac.get_command_matches(text))
    return True


def try_file_autocomplete(text: str, cursor: int, ac: AutocompleteWidget) -> bool:
    word = _get_current_word(text, cursor)
    if not word.startswith("@") or len(word) < 2:
        return False
    ac.show(ac.get_file_matches(word[1:]))
    return True


def _get_current_word(text: str, cursor: int) -> str:
    text_to_cursor = text[:cursor]
    last_space = text_to_cursor.rfind(" ")
    return text_to_cursor[last_space + 1:]


def get_word_start_pos(text: str, cursor: int) -> int:
    text_to_cursor = text[:cursor]
    return text_to_cursor.rfind(" ") + 1


def apply_cmd_selection(inp: MarkdownInput, value: str) -> None:
    inp.set_internal(value, len(value))
    inp.post_message(inp.Submitted(inp, value))


def apply_file_selection(inp: MarkdownInput, value: str, ac_pos: int) -> None:
    text = inp.internal_value
    before = text[:ac_pos]
    after_at = text[ac_pos + 1:]
    space_idx = after_at.find(" ")
    after = after_at[space_idx + 1:] if space_idx >= 0 else ""
    filename = Path(value).name
    link = f"[{filename}]({value})"
    new_internal = before + link + " " + after
    inp.set_internal(new_internal, len(before + link) + 1)
