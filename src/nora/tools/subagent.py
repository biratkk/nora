"""Subagent tool for orchestrated research."""

from strands import tool
from strands.types.tools import ToolContext

from nora.services.agent_service import AgentService


@tool(name="Subagent", context=True)
def run_subagent(tool_context: ToolContext, prompt: str, reason: str) -> str:
    """Run a subagent to research or explore a topic. Use for complex queries needing multiple tool calls.
    
    Args:
        prompt: Detailed instructions for what the subagent should find or do
        reason: Brief sentence explaining why (e.g., "Researching authentication flow.")
    """
    # Access context via invocation_state (set when agent is invoked)
    invocation_state = tool_context.invocation_state
    callback = invocation_state.get("subagent_callback")
    profile = invocation_state.get("profile")
    cancel_hook = invocation_state.get("cancel_hook")
    
    # Get tool_use_id from context to route callbacks correctly
    tool_use_id = tool_context.tool_use.get("toolUseId")
    
    # Use agent service to create subagent
    agent_service = AgentService()
    agent = agent_service.create_subagent(
        profile=profile,
        cancel_hook=cancel_hook,
    )
    
    all_content = []
    
    def on_stream(**kwargs):
        if callback:
            callback(tool_use_id, **kwargs)
        if "data" in kwargs:
            all_content.append(kwargs["data"])
    
    agent.callback_handler = on_stream
    agent(prompt)
    
    return "".join(all_content)
