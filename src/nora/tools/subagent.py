"""Subagent tool for orchestrated research."""

from strands import tool
from strands.types.tools import ToolContext


@tool(name="Subagent", context=True)
def run_subagent(tool_context: ToolContext, prompt: str) -> str:
    """Run a subagent to research or explore a topic. Use for complex queries needing multiple tool calls.
    
    Args:
        prompt: Concise, clear prompt explaining what the subagent should find or do
    """
    from nora.core.agent import create_agent
    from nora.core.hooks import CancellationHook
    
    # Access context via invocation_state (set when agent is invoked)
    invocation_state = tool_context.invocation_state
    callback = invocation_state.get("subagent_callback")
    profile = invocation_state.get("profile")
    cancel_hook = invocation_state.get("cancel_hook")
    
    # Get tool_use_id from context to route callbacks correctly
    tool_use_id = tool_context.tool_use.get("toolUseId")
    
    # Create a new cancel hook for the subagent that shares state with parent
    subagent_hooks = []
    if cancel_hook:
        subagent_hooks.append(cancel_hook)  # Share the same hook instance
    
    # Use subagent mode for concise output
    agent = create_agent([], profile=profile, mode="subagent", hooks=subagent_hooks)
    
    all_content = []
    
    def on_stream(**kwargs):
        if callback:
            callback(tool_use_id, **kwargs)
        if "data" in kwargs:
            all_content.append(kwargs["data"])
    
    agent.callback_handler = on_stream
    agent(prompt)
    
    return "".join(all_content)
