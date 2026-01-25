"""Hooks for agent lifecycle events."""

from typing import Any

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry


class CancellationHook(HookProvider):
    """Hook that checks for cancellation before each tool call."""
    
    def __init__(self):
        self.cancelled = False
    
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check_cancelled)
    
    def check_cancelled(self, event: BeforeToolCallEvent) -> None:
        """Cancel tool execution if cancellation was requested."""
        if self.cancelled:
            event.cancel_tool = "Operation cancelled by user"
    
    def cancel(self) -> None:
        """Signal cancellation."""
        self.cancelled = True
    
    def reset(self) -> None:
        """Reset cancellation state."""
        self.cancelled = False
