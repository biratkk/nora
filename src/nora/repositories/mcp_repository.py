"""Repository for MCP server configuration persistence."""

import logging
from pathlib import Path
from typing import Optional

from nora.config.constants import NORA_DIR_NAME, MCPS_FILENAME
from nora.models.mcp_config import McpConfigFile

logger = logging.getLogger(__name__)


class McpRepository:
    """Handles persistence of MCP server configs to disk.

    Two locations:
    - Local:  $CWD/.nora/mcps.json
    - Global: ~/.nora/mcps.json
    """

    def __init__(
        self,
        local_base: Optional[Path] = None,
        global_base: Optional[Path] = None,
    ) -> None:
        self._local_base = local_base or (Path.cwd() / NORA_DIR_NAME)
        self._global_base = global_base or (Path.home() / NORA_DIR_NAME)

    @property
    def _local_path(self) -> Path:
        return self._local_base / MCPS_FILENAME

    @property
    def _global_path(self) -> Path:
        return self._global_base / MCPS_FILENAME

    def _load(self, path: Path) -> McpConfigFile:
        if not path.exists():
            return McpConfigFile()
        try:
            return McpConfigFile.model_validate_json(path.read_text())
        except Exception:
            logger.warning("Malformed MCP config at %s, treating as empty", path)
            return McpConfigFile()

    def load_local(self) -> McpConfigFile:
        return self._load(self._local_path)

    def load_global(self) -> McpConfigFile:
        return self._load(self._global_path)

    def _save(self, path: Path, config: McpConfigFile) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.model_dump_json(indent=2))

    def save_local(self, config: McpConfigFile) -> None:
        self._save(self._local_path, config)

    def save_global(self, config: McpConfigFile) -> None:
        self._save(self._global_path, config)

    def server_name_exists(self, name: str, scope: str) -> bool:
        config = self.load_local() if scope == "local" else self.load_global()
        return name in config.mcpServers
