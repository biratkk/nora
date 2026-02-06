"""Switch session modal with keyboard navigation and fuzzy search.

This is a duplicate — the canonical implementation has moved to
nora.tui.widgets.switch_modal. This file is kept for any direct
imports but re-exports from the canonical location.
"""

from nora.tui.widgets.switch_modal import SwitchModal, SessionItem

__all__ = ["SwitchModal", "SessionItem"]
