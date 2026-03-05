"""Service for AI agent management."""

from typing import Any, Optional, List

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from nora.config.constants import DEFAULT_MODEL_ID, AVAILABLE_MODELS
from nora.models.thread import Thread
from nora.services.settings_service import SettingsService


class CancellationHook(HookProvider):
    """
    Hook that enables cancellation of agent tool execution.
    
    Can be shared between parent and child agents to propagate cancellation.
    """
    
    def __init__(self) -> None:
        """Initialize with cancelled state as False."""
        self.cancelled: bool = False
    
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """
        Register cancellation check with hook registry.
        
        Args:
            registry: Strands hook registry.
            **kwargs: Additional arguments.
        """
        registry.add_callback(BeforeToolCallEvent, self.check_cancelled)
    
    def check_cancelled(self, event: BeforeToolCallEvent) -> None:
        """
        Check and apply cancellation to tool event.
        
        Args:
            event: BeforeToolCallEvent instance.
        """
        if self.cancelled:
            event.cancel_tool = "Operation cancelled by user"
    
    def cancel(self) -> None:
        """Signal cancellation."""
        self.cancelled = True
    
    def reset(self) -> None:
        """Reset cancellation state for reuse."""
        self.cancelled = False


class AgentService:
    """
    Manages AI agent creation and configuration.
    
    Handles agent instantiation with appropriate tools, system prompts,
    and model configuration based on mode and settings.
    """
    
    def __init__(self, settings_service: Optional[SettingsService] = None) -> None:
        """
        Initialize the service.
        
        Args:
            settings_service: Settings service instance. Uses singleton if None.
        """
        self._settings_service = settings_service or SettingsService.get_instance()
        self._tool_sets: Optional[dict[str, List]] = None
    
    def create_agent(
        self,
        messages: List[dict],
        profile: Optional[str] = None,
        mode: str = "vibe",
        model_id: Optional[str] = None,
        hooks: Optional[List] = None,
    ) -> Agent:
        """
        Create a configured agent instance.
        
        Args:
            messages: Initial conversation messages.
            profile: AWS profile name override.
            mode: Agent mode (vibe, plan, edit, subagent).
            model_id: Model ID override.
            hooks: Additional hooks to register.
            
        Returns:
            Configured Agent instance.
        """
        effective_model_id = model_id or DEFAULT_MODEL_ID
        model = self._create_model(effective_model_id, profile)
        system_prompt = self._get_system_prompt(mode)
        tools = self._get_tools_for_mode(mode)
        
        return Agent(
            model=model,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            hooks=hooks or [],
        )
    
    def create_agent_from_thread(
        self,
        thread: Thread,
        profile: Optional[str] = None,
        model_id: Optional[str] = None,
        hooks: Optional[List] = None,
    ) -> Agent:
        """
        Create an agent initialized from a thread.
        
        Args:
            thread: Thread to initialize from.
            profile: AWS profile name override.
            model_id: Model ID override.
            hooks: Additional hooks to register.
            
        Returns:
            Configured Agent instance.
        """
        messages = thread.to_agent_messages()
        return self.create_agent(
            messages=messages,
            profile=profile,
            mode=thread.mode,
            model_id=model_id,
            hooks=hooks,
        )
    
    def create_subagent(
        self,
        profile: Optional[str] = None,
        cancel_hook: Optional[CancellationHook] = None,
    ) -> Agent:
        """
        Create a subagent for research tasks.
        
        Subagents have read-only access and use the subagent prompt.
        
        Args:
            profile: AWS profile name.
            cancel_hook: Shared cancellation hook.
            
        Returns:
            Configured subagent instance.
        """
        hooks = [cancel_hook] if cancel_hook else []
        return self.create_agent(
            messages=[],
            profile=profile,
            mode="subagent",
            hooks=hooks,
        )
    
    def _create_model(
        self, 
        model_id: str, 
        profile: Optional[str]
    ) -> BedrockModel:
        """
        Create a Bedrock model instance.
        
        Args:
            model_id: The model ID to use.
            profile: Optional AWS profile name.
            
        Returns:
            Configured BedrockModel instance.
        """
        kwargs: dict[str, Any] = {"model_id": model_id}
        
        if profile:
            kwargs["boto_session"] = boto3.Session(profile_name=profile)
        
        return BedrockModel(**kwargs)
    
    def _get_system_prompt(self, mode: str) -> Optional[str]:
        """
        Get the system prompt for a mode.
        
        Args:
            mode: Agent mode.
            
        Returns:
            System prompt string.
        """
        return self._settings_service.get_mode_prompt(mode)
    
    def _get_tools_for_mode(self, mode: str) -> List:
        """
        Get the tool set for a mode.
        
        Tool lists are cached on first call since they never change.
        
        Args:
            mode: Agent mode.
            
        Returns:
            List of tool functions.
        """
        if self._tool_sets is None:
            # Import here to avoid circular imports
            from nora.tools import (
                read_file, write_file, edit_file, explore_dir, 
                search_files, run_subagent, fetch_url, run_shell,
                read_plugin, write_plugin, edit_plugin, delete_plugin, search_plugin,
            )
            from nora.tools.shell import update_shell_tool_cwd
            
            # Inject current working directory into Shell tool's dir parameter description
            update_shell_tool_cwd()
            
            plugin_tools = [read_plugin, write_plugin, edit_plugin, delete_plugin, search_plugin]
            readonly_tools = [read_file, explore_dir, search_files, fetch_url]
            plan_tools = readonly_tools + [run_subagent] + plugin_tools
            full_tools = [read_file, write_file, edit_file, explore_dir, search_files, run_subagent, fetch_url, run_shell] + plugin_tools
            
            self._tool_sets = {
                "subagent": readonly_tools,
                "plan": plan_tools,
                "vibe": full_tools,
                "edit": full_tools,
                "act": full_tools,
            }
        
        return self._tool_sets.get(mode, self._tool_sets["vibe"])
    
    @staticmethod
    def get_model_name(model_id: Optional[str] = None) -> str:
        """
        Get display name for a model.
        
        Args:
            model_id: Model ID to look up. Uses default if None.
            
        Returns:
            Human-readable model name.
        """
        effective_id = model_id or DEFAULT_MODEL_ID
        return AVAILABLE_MODELS.get(effective_id, effective_id)
    
    @staticmethod
    def get_available_models() -> dict[str, str]:
        """
        Get mapping of model IDs to display names.
        
        Returns:
            Dictionary of model_id -> display_name.
        """
        return AVAILABLE_MODELS.copy()
