"""Repository for plugin persistence."""

from pathlib import Path
from typing import Optional, List

import yaml

from nora.config.constants import NORA_DIR_NAME, PLUGINS_DIR_NAME
from nora.models.plugin import Plugin


class PluginRepository:
    """
    Handles persistence of plugins to disk.
    
    Plugins are stored as markdown files with YAML frontmatter
    in $CWD/.nora/plugins/.
    """
    
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """
        Initialize the repository.
        
        Args:
            base_dir: Base directory for plugins. Defaults to $CWD/.nora.
        """
        cwd_nora = Path.cwd() / NORA_DIR_NAME
        self._base_dir = base_dir or cwd_nora
        self._plugins_dir = self._base_dir / PLUGINS_DIR_NAME
    
    @property
    def plugins_dir(self) -> Path:
        """Get the plugins directory path."""
        return self._plugins_dir
    
    def _ensure_dirs(self) -> None:
        """Ensure the plugins directory exists."""
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_plugin_path(self, name: str) -> Path:
        """Get the file path for a plugin."""
        return self._plugins_dir / f"{name}.md"
    
    def _parse_plugin_file(self, path: Path) -> Optional[Plugin]:
        """
        Parse a plugin markdown file.
        
        Args:
            path: Path to the plugin file.
            
        Returns:
            Plugin instance or None if parsing fails.
        """
        try:
            content = path.read_text()
            
            if not content.startswith("---"):
                return None
            
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            
            frontmatter_str = parts[1].strip()
            instructions = parts[2].strip()
            
            metadata = yaml.safe_load(frontmatter_str) or {}
            
            name = metadata.get("name", "")
            if not name:
                return None
            
            description = metadata.get("description", "")
            keywords_str = metadata.get("keywords", "")
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
            load_on_startup = str(metadata.get("load_on_startup", "no")).lower() == "yes"
            
            return Plugin(
                name=name,
                description=description,
                keywords=keywords,
                instructions=instructions,
                load_on_startup=load_on_startup
            )
        except Exception:
            return None
    
    def save(self, plugin: Plugin) -> Path:
        """
        Save a plugin to disk.
        
        Args:
            plugin: Plugin instance to persist.
            
        Returns:
            Path to the created plugin file.
        """
        self._ensure_dirs()
        
        path = self._get_plugin_path(plugin.name)
        path.write_text(plugin.to_markdown())
        
        return path
    
    def load(self, name: str) -> Optional[Plugin]:
        """
        Load a plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            Plugin instance or None if not found.
        """
        path = self._get_plugin_path(name)
        
        if not path.exists():
            return None
        
        return self._parse_plugin_file(path)
    
    def load_all(self, startup_only: bool = False) -> List[Plugin]:
        """
        Load all plugins from disk.
        
        Args:
            startup_only: If True, only load plugins with load_on_startup=True.
            
        Returns:
            List of Plugin instances.
        """
        if not self._plugins_dir.exists():
            return []
        
        plugins: List[Plugin] = []
        
        for path in self._plugins_dir.glob("*.md"):
            plugin = self._parse_plugin_file(path)
            if plugin is None:
                continue
            if startup_only and not plugin.load_on_startup:
                continue
            plugins.append(plugin)
        
        return plugins
    
    def exists(self, name: str) -> bool:
        """
        Check if a plugin exists.
        
        Args:
            name: The plugin name.
            
        Returns:
            True if plugin file exists.
        """
        return self._get_plugin_path(name).exists()
    
    def delete(self, name: str) -> bool:
        """
        Delete a plugin from disk.
        
        Args:
            name: The plugin name.
            
        Returns:
            True if plugin was deleted, False if it didn't exist.
        """
        path = self._get_plugin_path(name)
        
        if path.exists():
            path.unlink()
            return True
        
        return False
