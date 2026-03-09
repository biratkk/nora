"""Service for MCP client lifecycle and tool discovery."""

import logging
import os
from typing import Optional

from nora.models.mcp_config import McpServerConfig
from nora.repositories.mcp_repository import McpRepository

logger = logging.getLogger(__name__)


class McpService:
    """Manages MCP server configuration, tool discovery, and client creation."""

    def __init__(self, repository: Optional[McpRepository] = None) -> None:
        self._repository = repository or McpRepository()

    def discover_tools(self, command: str, args: list[str]) -> list[dict]:
        """Connect temporarily via stdio to list available tools.

        Returns list of {"name": str, "description": str}.
        Raises on connection failure.
        """
        from mcp import stdio_client, StdioServerParameters
        from strands.tools.mcp import MCPClient

        client = MCPClient(lambda: stdio_client(
            StdioServerParameters(command=command, args=args)
        ))
        with client:
            tools = client.list_tools_sync()
            return [
                {"name": t.tool_name, "description": t.tool_spec.get("description", "No description found.")}
                for t in tools
            ]

    def get_mcp_clients(self) -> list:
        """Create MCPClient instances for all enabled servers.

        Merges global + local configs (local overrides on name collision).
        Returns list of MCPClient instances to pass to Agent(tools=...).
        """
        from mcp import stdio_client, StdioServerParameters
        from strands.tools.mcp import MCPClient

        global_config = self._repository.load_global()
        local_config = self._repository.load_local()

        merged: dict[str, McpServerConfig] = {
            **global_config.mcpServers,
            **local_config.mcpServers,
        }

        clients = []
        for name, server in merged.items():
            if server.disabled:
                continue

            tool_filters = {}
            if server.disabledTools:
                tool_filters["rejected"] = server.disabledTools

            try:
                if server.command:
                    env = {k: os.path.expandvars(v) for k, v in server.env.items()}
                    client = MCPClient(
                        lambda cmd=server.command, a=server.args, e=env: stdio_client(
                            StdioServerParameters(command=cmd, args=a, env=e or None)
                        ),
                        tool_filters=tool_filters or None,
                        prefix=name,
                    )
                elif server.url:
                    from mcp.client.streamable_http import streamablehttp_client

                    client = MCPClient(
                        lambda u=server.url, h=server.headers: streamablehttp_client(
                            url=u, headers=h or None
                        ),
                        tool_filters=tool_filters or None,
                        prefix=name,
                    )
                else:
                    continue
                clients.append(client)
            except Exception:
                logger.warning("Failed to create MCP client for '%s'", name, exc_info=True)

        return clients

    def add_server(self, name: str, config: McpServerConfig, scope: str) -> None:
        """Add or replace a server entry in the given scope."""
        cfg = self._repository.load_local() if scope == "local" else self._repository.load_global()
        cfg.mcpServers[name] = config
        if scope == "local":
            self._repository.save_local(cfg)
        else:
            self._repository.save_global(cfg)

    def update_server(self, name: str, config: McpServerConfig, scope: str) -> None:
        """Update an existing server entry (alias for add_server)."""
        self.add_server(name, config, scope)

    def delete_server(self, name: str, scope: str) -> bool:
        """Remove a server entry from the given scope.

        Returns True if the server was found and removed, False otherwise.
        """
        cfg = self._repository.load_local() if scope == "local" else self._repository.load_global()
        if name not in cfg.mcpServers:
            return False
        del cfg.mcpServers[name]
        if scope == "local":
            self._repository.save_local(cfg)
        else:
            self._repository.save_global(cfg)
        return True

    def get_all_servers(self) -> list[tuple[str, McpServerConfig, str]]:
        """Return list of (name, config, scope). Local listed first."""
        result = []
        local = self._repository.load_local()
        for name, cfg in local.mcpServers.items():
            result.append((name, cfg, "local"))
        glb = self._repository.load_global()
        for name, cfg in glb.mcpServers.items():
            if name not in local.mcpServers:
                result.append((name, cfg, "global"))
        return result

    def server_name_exists(self, name: str, scope: str) -> bool:
        """Check if a server name already exists in the given scope."""
        return self._repository.server_name_exists(name, scope)
