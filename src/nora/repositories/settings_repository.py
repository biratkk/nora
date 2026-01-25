"""Repository for application settings persistence."""

from pathlib import Path
from typing import Optional

from nora.config.constants import NORA_DIR_NAME, SETTINGS_FILENAME, MODES_DIR_NAME
from nora.config.prompts import DEFAULT_PROMPTS
from nora.models.settings import Settings


class SettingsRepository:
    """
    Handles persistence of application settings to disk.
    
    Settings are stored in ~/.nora/settings.json. Mode prompts are stored
    as individual markdown files in ~/.nora/modes/.
    """
    
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """
        Initialize the repository.
        
        Args:
            base_dir: Base directory for settings. Defaults to ~/.nora.
        """
        self._base_dir = base_dir or (Path.home() / NORA_DIR_NAME)
        self._settings_file = self._base_dir / SETTINGS_FILENAME
        self._modes_dir = self._base_dir / MODES_DIR_NAME
    
    @property
    def base_dir(self) -> Path:
        """Get the base directory path."""
        return self._base_dir
    
    @property
    def modes_dir(self) -> Path:
        """Get the modes directory path."""
        return self._modes_dir
    
    def initialize(self) -> None:
        """
        Initialize settings directory structure.
        
        Creates ~/.nora/, settings.json, and default mode prompt files
        if they don't exist.
        """
        self._base_dir.mkdir(parents=True, exist_ok=True)
        
        if not self._settings_file.exists():
            self._settings_file.write_text("{}")
        
        self._modes_dir.mkdir(exist_ok=True)
        
        for mode, prompt in DEFAULT_PROMPTS.items():
            if mode == "subagent":
                continue
            prompt_file = self._modes_dir / f"{mode}.md"
            if not prompt_file.exists():
                prompt_file.write_text(prompt)
    
    def load(self) -> Settings:
        """
        Load settings from disk.
        
        Returns:
            Settings instance, or default settings if file doesn't exist or is invalid.
        """
        if not self._settings_file.exists():
            return Settings()
        
        try:
            return Settings.model_validate_json(self._settings_file.read_text())
        except Exception:
            return Settings()
    
    def save(self, settings: Settings) -> None:
        """
        Save settings to disk.
        
        Args:
            settings: Settings instance to persist.
        """
        self._settings_file.write_text(
            settings.model_dump_json(exclude_none=True, indent=2)
        )
    
    def load_mode_prompt(self, mode: str) -> Optional[str]:
        """
        Load a mode-specific system prompt.
        
        Args:
            mode: The mode name (vibe, plan, act, subagent).
            
        Returns:
            The prompt content, or default prompt if file doesn't exist.
        """
        prompt_file = self._modes_dir / f"{mode}.md"
        
        if prompt_file.exists():
            return prompt_file.read_text()
        
        return DEFAULT_PROMPTS.get(mode)
