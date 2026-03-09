"""MCP server management modals (/mcp command)."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static
from textual import work

from nora.models.mcp_config import McpServerConfig


class McpServerDetailModal(ModalScreen[Optional[tuple[McpServerConfig, str]]]):
    """Tabbed detail view for a single MCP server.

    Three tabs: Configuration, Enabled Tools, Trusted Tools.
    Returns (updated_config, scope) on dismiss, or None if unchanged.
    """

    DEFAULT_CSS = """
    McpServerDetailModal { align: center middle; }
    McpServerDetailModal > .modal-outer {
        width: 75%;
        max-height: 80%;
        border: round $primary;
        background: $surface;
    }
    McpServerDetailModal .modal-content { padding: 1 2; height: 1fr; }
    McpServerDetailModal .modal-status { background: $surface-lighten-1; padding: 0 1; }
    McpServerDetailModal .tab-bar { height: auto; margin-bottom: 1; }
    McpServerDetailModal .title { text-style: bold; margin-bottom: 1; }
    McpServerDetailModal VerticalScroll { height: 1fr; }
    McpServerDetailModal .config-row { height: auto; padding: 0 1; }
    McpServerDetailModal .config-label { text-style: bold; }
    McpServerDetailModal .tool-row { height: auto; padding: 0 1; }
    McpServerDetailModal .tool-row.selected { background: $primary 20%; }
    """

    BINDINGS = [("escape", "close", "Save and Exit"), ("ctrl+c", "close", "Save and Exit")]

    TABS = ["Configuration", "Enabled Tools", "Trusted Tools"]

    def __init__(
        self,
        name: str,
        config: McpServerConfig,
        scope: str,
        tools: list[dict],
    ) -> None:
        super().__init__()
        self._name = name
        self._config = config.model_copy(deep=True)
        self._scope = scope
        self._tools = tools
        self._current_tab = 0
        self._selected_index = 0

        # Build enabled/trusted state from config
        self._enabled: list[bool] = [
            t["name"] not in config.disabledTools for t in tools
        ]
        self._trusted: list[bool] = [
            t["name"] in config.trustedTools for t in tools
        ]

    def compose(self) -> ComposeResult:
        with Container(classes="modal-outer"):
            with Container(classes="modal-content"):
                yield Static(f"[bold]{self._name}[/bold]  ({self._scope})", classes="title")
                yield Static(self._render_tabs(), id="tab-bar", classes="tab-bar")
                yield VerticalScroll(id="detail-content")
            yield Static(
                "[Esc/Ctrl+C] Save and Exit  ←/→ Switch Tab  ↑/↓ Navigate  Enter Toggle",
                classes="modal-status",
            )

    def on_mount(self) -> None:
        self._render_tab_content()

    def _render_tabs(self) -> str:
        parts = []
        for i, tab in enumerate(self.TABS):
            if i == self._current_tab:
                parts.append(f"[bold reverse] {tab} [/bold reverse]")
            else:
                parts.append(f"[dim] {tab} [/dim]")
        return "  ".join(parts)

    def _render_tab_content(self) -> None:
        scroll = self.query_one("#detail-content", VerticalScroll)
        scroll.remove_children()

        if self._current_tab == 0:
            self._render_config_tab(scroll)
        elif self._current_tab == 1:
            self._render_tools_tab(scroll, self._enabled, "enabled")
        elif self._current_tab == 2:
            self._render_tools_tab(scroll, self._trusted, "trusted")

    def _render_config_tab(self, scroll: VerticalScroll) -> None:
        cfg = self._config
        rows = []
        rows.append(f"[bold]Name:[/bold]     {self._name}")
        if cfg.command:
            rows.append(f"[bold]Command:[/bold]  {cfg.command}")
        if cfg.args:
            rows.append(f"[bold]Args:[/bold]     {' '.join(cfg.args)}")
        if cfg.env:
            for k, v in cfg.env.items():
                rows.append(f"[bold]Env:[/bold]      {k}={v}")
        if cfg.url:
            rows.append(f"[bold]URL:[/bold]      {cfg.url}")
        if cfg.headers:
            for k, v in cfg.headers.items():
                rows.append(f"[bold]Header:[/bold]   {k}: {v}")
        rows.append(f"[bold]Disabled:[/bold] {'Yes' if cfg.disabled else 'No'}")
        rows.append(f"[bold]Scope:[/bold]    {self._scope}")

        for row in rows:
            scroll.mount(Static(row, classes="config-row"))

    def _render_tools_tab(
        self,
        scroll: VerticalScroll,
        states: list[bool],
        kind: str,
    ) -> None:
        if not self._tools:
            scroll.mount(Static("[dim]No tools discovered[/dim]", classes="config-row"))
            return
        for i, tool in enumerate(self._tools):
            check = "☑" if states[i] else "☐"
            classes = "tool-row selected" if i == self._selected_index else "tool-row"
            scroll.mount(
                Static(f"{check}  {tool['name']}", classes=classes, id=f"dt-{kind}-{i}")
            )

    async def on_key(self, event) -> None:
        if event.key in ("left",):
            self._current_tab = (self._current_tab - 1) % len(self.TABS)
            self._selected_index = 0
            self.query_one("#tab-bar", Static).update(self._render_tabs())
            self._render_tab_content()
            event.prevent_default()
        elif event.key in ("right",):
            self._current_tab = (self._current_tab + 1) % len(self.TABS)
            self._selected_index = 0
            self.query_one("#tab-bar", Static).update(self._render_tabs())
            self._render_tab_content()
            event.prevent_default()
        elif event.key in ("up", "ctrl+p"):
            if self._current_tab > 0 and self._selected_index > 0:
                self._selected_index -= 1
                self._refresh_tool_rows()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self._current_tab > 0 and self._selected_index < len(self._tools) - 1:
                self._selected_index += 1
                self._refresh_tool_rows()
            event.prevent_default()
        elif event.key == "enter":
            if self._current_tab == 1 and self._tools:
                self._enabled[self._selected_index] = not self._enabled[self._selected_index]
                self._refresh_tool_rows()
            elif self._current_tab == 2 and self._tools:
                self._trusted[self._selected_index] = not self._trusted[self._selected_index]
                self._refresh_tool_rows()
            event.prevent_default()

    def _refresh_tool_rows(self) -> None:
        """Update tool row visuals for the current tab."""
        states = self._enabled if self._current_tab == 1 else self._trusted
        kind = "enabled" if self._current_tab == 1 else "trusted"
        for i, tool in enumerate(self._tools):
            try:
                row = self.query_one(f"#dt-{kind}-{i}", Static)
            except Exception:
                continue
            check = "☑" if states[i] else "☐"
            row.update(f"{check}  {tool['name']}")
            if i == self._selected_index:
                row.add_class("selected")
                row.scroll_visible()
            else:
                row.remove_class("selected")

    def action_close(self) -> None:
        # Compute updated config
        disabled = [
            self._tools[i]["name"]
            for i in range(len(self._tools))
            if not self._enabled[i]
        ]
        trusted = [
            self._tools[i]["name"]
            for i in range(len(self._tools))
            if self._trusted[i]
        ]
        self._config.disabledTools = disabled
        self._config.trustedTools = trusted
        self.dismiss((self._config, self._scope))


class McpServerListModal(ModalScreen[bool]):
    """Server list modal for /mcp command.

    Shows all registered MCP servers in Local/Global sections.
    Returns True if any changes were made, False otherwise.
    """

    DEFAULT_CSS = """
    McpServerListModal { align: center middle; }
    McpServerListModal > .modal-outer {
        width: 70%;
        max-height: 80%;
        border: round $primary;
        background: $surface;
    }
    McpServerListModal .modal-content { padding: 1 2; height: 1fr; }
    McpServerListModal .modal-status { background: $surface-lighten-1; padding: 0 1; }
    McpServerListModal .title { text-style: bold; margin-bottom: 1; }
    McpServerListModal VerticalScroll { height: 1fr; }
    McpServerListModal .section-header { color: $text-muted; text-style: dim; height: auto; padding: 0 1; }
    McpServerListModal .server-row { height: auto; padding: 0 1; }
    McpServerListModal .server-row.selected { background: $primary 20%; }
    McpServerListModal .server-row.disabled-server { color: $text-muted; }
    """

    BINDINGS = [
        ("escape", "close", "Save and Exit"),
        ("ctrl+c", "close", "Save and Exit"),
        ("ctrl+d", "delete", "Delete Server"),
    ]

    def __init__(self, agent_service=None) -> None:
        super().__init__()
        from nora.services.mcp_service import McpService

        self._mcp_service = McpService()
        self._agent_service = agent_service
        self._servers: list[tuple[str, McpServerConfig, str]] = []
        self._selectable_indices: list[int] = []
        self._selected_pos = 0
        self._changed = False

    def compose(self) -> ComposeResult:
        with Container(classes="modal-outer"):
            with Container(classes="modal-content"):
                yield Static("MCP Servers", classes="title")
                yield VerticalScroll(id="server-list")
            yield Static(
                "[Esc/Ctrl+C] Save and Exit  ↑/↓ Navigate  Enter Select  Ctrl+D Delete",
                classes="modal-status",
            )

    async def on_mount(self) -> None:
        await self._load_servers()

    async def _load_servers(self) -> None:
        self._servers = self._mcp_service.get_all_servers()
        scroll = self.query_one("#server-list", VerticalScroll)
        await scroll.remove_children()

        local_servers = [(n, c, s) for n, c, s in self._servers if s == "local"]
        global_servers = [(n, c, s) for n, c, s in self._servers if s == "global"]

        self._selectable_indices = []
        row_idx = 0

        if local_servers:
            scroll.mount(Static("── Local ──", classes="section-header"))
            row_idx += 1
            for name, cfg, scope in local_servers:
                self._selectable_indices.append(row_idx)
                status = "✗" if cfg.disabled else "✓"
                desc = cfg.command or cfg.url or ""
                if cfg.args:
                    desc += " " + " ".join(cfg.args)
                classes = "server-row"
                if cfg.disabled:
                    classes += " disabled-server"
                scroll.mount(
                    Static(f"{name}    {desc}    {status}", classes=classes, id=f"srv-{row_idx}")
                )
                row_idx += 1

        if global_servers:
            scroll.mount(Static("── Global ──", classes="section-header"))
            row_idx += 1
            for name, cfg, scope in global_servers:
                self._selectable_indices.append(row_idx)
                status = "✗" if cfg.disabled else "✓"
                desc = cfg.command or cfg.url or ""
                if cfg.args:
                    desc += " " + " ".join(cfg.args)
                classes = "server-row"
                if cfg.disabled:
                    classes += " disabled-server"
                scroll.mount(
                    Static(f"{name}    {desc}    {status}", classes=classes, id=f"srv-{row_idx}")
                )
                row_idx += 1

        if not self._servers:
            scroll.mount(Static("[dim]No MCP servers configured[/dim]", classes="section-header"))

        self._selected_pos = 0
        self._update_selection()

    def _update_selection(self) -> None:
        for idx in self._selectable_indices:
            try:
                row = self.query_one(f"#srv-{idx}", Static)
                if self._selectable_indices and idx == self._selectable_indices[self._selected_pos]:
                    row.add_class("selected")
                    row.scroll_visible()
                else:
                    row.remove_class("selected")
            except Exception:
                continue

    def _get_selected_server(self) -> Optional[tuple[str, McpServerConfig, str]]:
        if not self._selectable_indices:
            return None
        # Map selectable position back to self._servers index
        return self._servers[self._selected_pos] if self._selected_pos < len(self._servers) else None

    async def on_key(self, event) -> None:
        if event.key in ("up", "ctrl+p"):
            if self._selectable_indices and self._selected_pos > 0:
                self._selected_pos -= 1
                self._update_selection()
            event.prevent_default()
        elif event.key in ("down", "ctrl+n"):
            if self._selectable_indices and self._selected_pos < len(self._selectable_indices) - 1:
                self._selected_pos += 1
                self._update_selection()
            event.prevent_default()
        elif event.key == "enter":
            server = self._get_selected_server()
            if server:
                self._open_detail(server)
            event.prevent_default()

    @work
    async def _open_detail(self, server: tuple[str, McpServerConfig, str]) -> None:
        """Open the detail modal for a server (runs in a worker for push_screen_wait)."""
        name, config, scope = server
        # Try to get tools from the live agent MCP client first (avoids spawning a new process)
        tools: list[dict] = []
        if not config.disabled:
            if self._agent_service:
                try:
                    tools = self._agent_service.get_mcp_tools_for_server(name)
                except Exception:
                    pass
            # Fall back to fresh discovery if no live tools available
            if not tools and config.command:
                try:
                    tools = self._mcp_service.discover_tools(config.command, config.args)
                except Exception:
                    pass
        detail = McpServerDetailModal(name, config, scope, tools)
        result = await self.app.push_screen_wait(detail)
        if result is not None:
            updated_config, updated_scope = result
            self._mcp_service.update_server(name, updated_config, updated_scope)
            self._changed = True
            await self._load_servers()

    async def action_delete(self) -> None:
        """Delete the currently selected MCP server."""
        server = self._get_selected_server()
        if not server:
            return
        name, _config, scope = server
        self._mcp_service.delete_server(name, scope)
        self._changed = True
        await self._load_servers()

    def action_close(self) -> None:
        self.dismiss(self._changed)
