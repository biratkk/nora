"""Service for plugin management and matching."""

from pathlib import Path
from typing import Optional, List

from thefuzz import fuzz

from nora.config.constants import PLUGIN_MATCH_THRESHOLD
from nora.models.plugin import Plugin
from nora.repositories.plugin_repository import PluginRepository


class PluginService:
    """
    Manages plugin lifecycle and keyword matching.
    
    Provides operations for loading plugins and matching them
    against user input using fuzzy keyword matching.
    """
    
    def __init__(self, repository: Optional[PluginRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Plugin repository instance. Creates default if None.
        """
        self._repository = repository or PluginRepository()
        self._cached_plugins: Optional[List[Plugin]] = None
    
    def load_all(self, startup_only: bool = True) -> List[Plugin]:
        """
        Load all plugins from disk.
        
        Args:
            startup_only: If True, only load startup plugins.
            
        Returns:
            List of Plugin instances.
        """
        self._cached_plugins = self._repository.load_all(startup_only=startup_only)
        return self._cached_plugins
    
    def get_cached_plugins(self) -> List[Plugin]:
        """
        Get cached plugins, loading if necessary.
        
        Returns:
            List of cached Plugin instances.
        """
        if self._cached_plugins is None:
            self.load_all()
        return self._cached_plugins or []
    
    def save(self, plugin: Plugin) -> Path:
        """
        Save a plugin to disk.
        
        Clears the cache after saving.
        
        Args:
            plugin: Plugin to persist.
            
        Returns:
            Path to the created plugin file.
        """
        path = self._repository.save(plugin)
        self._cached_plugins = None
        return path
    
    def match_plugins(
        self, 
        text: str, 
        threshold: int = PLUGIN_MATCH_THRESHOLD
    ) -> List[Plugin]:
        """
        Find plugins matching the given text using fuzzy keyword matching.
        
        Args:
            text: User input text to match against.
            threshold: Minimum match score (0-100).
            
        Returns:
            List of matching Plugin instances.
        """
        plugins = self.get_cached_plugins()
        matched: List[Plugin] = []
        text_lower = text.lower()
        
        for plugin in plugins:
            if self._plugin_matches(plugin, text_lower, threshold):
                matched.append(plugin)
        
        return matched
    
    def _plugin_matches(
        self, 
        plugin: Plugin, 
        text_lower: str, 
        threshold: int
    ) -> bool:
        """
        Check if a plugin matches the text.
        
        Args:
            plugin: Plugin to check.
            text_lower: Lowercase user input.
            threshold: Minimum match score.
            
        Returns:
            True if any keyword matches above threshold.
        """
        for keyword in plugin.keywords:
            ratio = fuzz.partial_ratio(keyword.lower(), text_lower)
            if ratio >= threshold:
                return True
        return False
    
    def build_context(self, plugins: List[Plugin]) -> str:
        """
        Build context string from matched plugins.
        
        Args:
            plugins: List of plugins to include.
            
        Returns:
            Combined plugin context blocks.
        """
        if not plugins:
            return ""
        
        blocks = [plugin.to_context_block() for plugin in plugins]
        return "\n\n".join(blocks) + "\n\n"
    
    def enhance_prompt(self, text: str, plugins: List[Plugin]) -> str:
        """
        Enhance user prompt with plugin context.
        
        Args:
            text: Original user text.
            plugins: Matched plugins to inject.
            
        Returns:
            Enhanced prompt with plugin context prepended.
        """
        context = self.build_context(plugins)
        return context + text
    
    def clear_cache(self) -> None:
        """Clear the cached plugins."""
        self._cached_plugins = None
