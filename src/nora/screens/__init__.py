"""Screen and modal components - re-exports from tui/widgets for flat structure."""

# Re-export from existing locations for new flat import structure
from nora.tui.widgets.confirmation import ToolConfirmModal
from nora.screens.diff_modal import DiffModal
from nora.tui.widgets.model_modal import ModelSelectorModal
from nora.tui.widgets.switch_modal import SwitchModal
from nora.screens.shell_approval_modal import ShellApprovalModal
from nora.screens.trust_level_modal import TrustLevelModal

__all__ = [
    "ToolConfirmModal",
    "DiffModal",
    "ModelSelectorModal",
    "SwitchModal",
    "ShellApprovalModal",
    "TrustLevelModal",
]
