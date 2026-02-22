"""Service for application settings management."""

from typing import Optional

from nora.models.settings import Settings
from nora.repositories.settings_repository import SettingsRepository


class SettingsService:
    """
    Manages application settings lifecycle.
    
    Provides a high-level interface for loading, saving, and initializing
    application settings and mode prompts.
    """
    
    _instance: Optional["SettingsService"] = None
    
    def __init__(self, repository: Optional[SettingsRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: Settings repository instance. Creates default if None.
        """
        self._repository = repository or SettingsRepository()
        self._cached_settings: Optional[Settings] = None
    
    @classmethod
    def get_instance(cls) -> "SettingsService":
        """
        Get the singleton service instance.
        
        Returns:
            The shared SettingsService instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def initialize(self) -> None:
        """
        Initialize settings directory and default files.
        
        Creates ~/.nora/ directory structure and default mode prompts
        if they don't exist.
        """
        self._repository.initialize()
    
    def load(self) -> Settings:
        """
        Load settings from disk.
        
        Uses cached settings if available.
        
        Returns:
            Current Settings instance.
        """
        if self._cached_settings is None:
            self._cached_settings = self._repository.load()
        return self._cached_settings
    
    def save(self, settings: Settings) -> None:
        """
        Save settings to disk.
        
        Updates the cache after saving.
        
        Args:
            settings: Settings to persist.
        """
        self._repository.save(settings)
        self._cached_settings = settings
    
    def update(self, **kwargs) -> Settings:
        """
        Update specific settings fields.
        
        Args:
            **kwargs: Fields to update (e.g., defaultProfile="my-profile").
            
        Returns:
            Updated Settings instance.
        """
        settings = self.load()
        
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        self.save(settings)
        return settings
    
    def get_mode_prompt(self, mode: str) -> Optional[str]:
        """
        Get the system prompt for a mode.
        
        Args:
            mode: Mode name (vibe, plan, edit, subagent).
            
        Returns:
            System prompt string or None.
        """
        return self._repository.load_mode_prompt(mode)
    
    def clear_cache(self) -> None:
        """Clear the cached settings."""
        self._cached_settings = None
