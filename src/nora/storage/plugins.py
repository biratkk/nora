"""Plugin persistence and loading."""

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

PLUGINS_DIR_NAME = ".nora/plugins"


@dataclass
class Plugin:
    """Represents a plugin with its metadata and instructions."""
    name: str
    description: str
    keywords: List[str]
    instructions: str

    def to_markdown(self) -> str:
        """Convert plugin to markdown format with frontmatter."""
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "keywords": ", ".join(self.keywords),
        }
        yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
        return f"---\n{yaml_str}\n---\n{self.instructions}\n"


def get_plugins_dir() -> Path:
    """Get or create plugins directory in current working directory."""
    plugins_dir = Path.cwd() / ".nora" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def validate_plugin_name(name: str) -> tuple[bool, str]:
    """Validate plugin name format.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Name cannot be empty"
    if " " in name:
        return False, "Name cannot contain spaces"
    if "/" in name:
        return False, "Name cannot contain /"
    if "\\" in name:
        return False, "Name cannot contain \\"
    return True, ""


def save_plugin(plugin: Plugin) -> Path:
    """Save plugin to markdown file.
    
    Returns:
        Path to the created plugin file
    """
    plugins_dir = get_plugins_dir()
    path = plugins_dir / f"{plugin.name}.md"
    path.write_text(plugin.to_markdown())
    return path


def parse_plugin_file(path: Path) -> Optional[Plugin]:
    """Parse plugin markdown file.
    
    Returns:
        Plugin object or None if parsing fails
    """
    try:
        content = path.read_text()
        
        # Check for frontmatter
        if not content.startswith("---"):
            return None
        
        # Split frontmatter and body
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        
        frontmatter_str = parts[1].strip()
        instructions = parts[2].strip()
        
        # Parse frontmatter with YAML
        metadata = yaml.safe_load(frontmatter_str) or {}
        
        # Extract required fields
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        keywords_str = metadata.get("keywords", "")
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        
        if not name:
            return None
        
        return Plugin(
            name=name,
            description=description,
            keywords=keywords,
            instructions=instructions,
        )
    except Exception:
        return None


def load_plugins() -> List[Plugin]:
    """Load all plugins from $CWD/.nora/plugins/.
    
    Returns:
        List of Plugin objects
    """
    plugins_dir = Path.cwd() / ".nora" / "plugins"
    if not plugins_dir.exists():
        return []
    
    plugins = []
    for path in plugins_dir.glob("*.md"):
        plugin = parse_plugin_file(path)
        if plugin:
            plugins.append(plugin)
    
    return plugins
