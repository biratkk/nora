"""Main TUI application."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Static
from thefuzz import fuzz

from nora.acp.models.session import Session
from nora.acp.models.message import AcpMessage, TrajectoryMetadata
from nora.acp.models.run import Run, RunStatus
from nora.config.constants import DEFAULT_MODEL_ID, MODE_CYCLE
from nora.services.settings_service import SettingsService
from nora.services.session_service import SessionService
from nora.services.run_service import RunService
from nora.services.plugin_service import PluginService
from nora.services.plan_service import PlanService
from nora.services.agent_service import AgentService, CancellationHook
from nora.widgets import ChatMessage, ToolCallBlock, ToolIndicator, SubagentBlock, ShellBlock, ShellMessage, DiffBlock, AutocompleteWidget, LoadingWidget, MarkdownInput
from nora.screens import ToolConfirmModal, ModelSelectorModal, DiffModal, SwitchModal, ShellApprovalModal, TrustLevelModal
from nora.services.trust_service import TrustService, TrustDecision
from nora.tools.shell import async_execute_command, async_execute_shell_command

logger = logging.getLogger(__name__)

MODE_COLORS = {"vibe": "cyan", "plan": "yellow", "edit": "green"}


@dataclass
class _ActiveInvocation:
    """State needed to snapshot and save a partial run on cancellation."""
    agent: object  # strands.Agent — avoid import for type only
    run: Run
    messages_before: int


class ChatApp(App):
    ANSI_COLOR = True
    CSS = """
    VerticalScroll { scrollbar-size: 1 1; }
    #main { padding: 1 2; background: #010101; }
    #chat-area { width: 1fr; height: 1fr; }
    #chat-container { height: 1fr; }
    #chat { height: 1fr; }
    .message-user, .message-assistant { padding: 0 1; height: auto; margin-bottom: 1; }
    .message-user { border-left: solid $primary; background: $primary 10%; padding: 1; }
    .message-assistant { }
    .message-tool { height: auto; padding: 0 1; margin: 0 0; }
    .message-content { margin: 0; padding: 0; }
    .message-time { dock: right; width: auto; }
    Markdown { margin: 0; padding: 0; }
    MarkdownBlock { margin: 0 0 1 0; padding: 0; }
    .message-assistant Markdown > *:last-child { margin: 0; }
    .message-user Markdown > *:last-child { margin: 0; }
    MarkdownHeader { content-align: left middle; }
    #input-container { padding: 0 1 1 1; height: auto; dock: bottom; border-left: solid $primary; background: #1a1a1a; }
    #input { height: auto; min-height: 3; max-height: 30; border:transparent; background: #1a1a1a; }
    #input:focus { background: #1a1a1a; }
    #input .text-area--cursor-line { background: #1a1a1a; }
    #input.shell-mode { border: round red; }
    #input.disabled { opacity: 0.5; }
    #autocomplete { dock: bottom; margin-bottom: 4; }
    #status-bar { height: 1; dock: bottom; background: $surface; }
    #mode-indicator { width: auto; padding: 0 1; }
    .mode-vibe { background: cyan; color: black; }
    .mode-plan { background: yellow; color: black; }
    .mode-edit { background: green; color: black; }
    #status-spacer { width: 1fr; }
    #status-keys { width: auto; padding: 0 1; color: $text-muted; }
    #model-name { width: auto; padding: 0 1; color: $text-muted; }
    LoadingWidget { dock: bottom; }
    """
    BINDINGS = [
        Binding("ctrl+c", "ctrl_c", "Quit", show=False),
        Binding("ctrl+o", "toggle_subagent_output", "Toggle subagent output", show=False),
    ]
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, session: Session, profile: Optional[str] = None):
        super().__init__()
        self.session = session
        self.profile = profile
        
        # Services
        self._session_service = SessionService()
        self._run_service = RunService()
        self._plugin_service = PluginService()
        self._plan_service = PlanService()
        self._agent_service = AgentService()
        
        # State
        self.agent = None
        self._agent_mode = "vibe"  # Agent mode for next run (vibe/plan/edit)
        self._ac_trigger: Optional[str] = None
        self._ac_pos: int = 0
        self._ctrl_c_pressed = False
        self._agent_model = DEFAULT_MODEL_ID
        self._processing = False
        self._current_worker = None
        self._cancel_hook = CancellationHook()
        self._active_invocation: Optional[_ActiveInvocation] = None
        self._subagent_expanded = False

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            with Container(id="chat-container"):
                yield VerticalScroll(id="chat")
            yield AutocompleteWidget(id="autocomplete")
            with Container(id="input-container"):
                yield MarkdownInput(placeholder="Type a message... (@file /cmd)", id="input")
        with Horizontal(id="status-bar"):
            yield Static(f" {self._agent_mode.upper()} ", id="mode-indicator", classes=f"mode-{self._agent_mode}")
            yield Static(f" {self._agent_service.get_model_name()} ", id="model-name")
            yield Static("", id="status-spacer")
            yield Static("@file  /cmd  Esc quit", id="status-keys")

    def action_ctrl_c(self) -> None:
        if not self._processing or not self._current_worker:
            # Not processing — handle double-Ctrl+C exit
            if self._ctrl_c_pressed:
                self.exit()
            else:
                self._ctrl_c_pressed = True
                self.set_timer(1.0, self._reset_ctrl_c)
            return

        self._cancel_hook.cancel()
        self._current_worker.cancel()

        # Save completed work from the interrupted run, then replace
        # the agent with a fresh instance (fresh lock, clean state).
        self._save_partial_run()
        self._init_agent()

        self._set_processing(False)
        self._active_invocation = None

        chat_container = self.query_one("#chat-container", Container)
        for loading in chat_container.query(LoadingWidget):
            loading.remove()

    def _reset_ctrl_c(self) -> None:
        self._ctrl_c_pressed = False

    def _save_partial_run(self) -> None:
        """Snapshot and save messages from the interrupted run.

        Reads agent.messages from the old (still-locked) agent instance.
        The background thread may still be appending, but Python's GIL
        makes the list slice atomic at the bytecode level. Any dangling
        toolUse blocks will be repaired by _validate_tool_pairing when
        the history is reloaded.
        """
        invocation = self._active_invocation
        if not invocation:
            return

        try:
            partial_messages = list(
                invocation.agent.messages[invocation.messages_before:]
            )
            self._run_service.cancel(invocation.run)
            self._run_service.confirm_cancel(invocation.run)
            self._run_service.save(invocation.run, partial_messages)
        except Exception:
            logger.warning(
                "Failed to save partial run on cancellation",
                exc_info=True,
            )

    def _set_processing(self, processing: bool) -> None:
        self._processing = processing
        inp = self.query_one("#input", MarkdownInput)
        if processing:
            self._cancel_hook.reset()
            inp.disabled = True
            inp.add_class("disabled")
        else:
            inp.disabled = False
            inp.remove_class("disabled")
            inp.focus()

    def action_toggle_subagent_output(self) -> None:
        self._subagent_expanded = not self._subagent_expanded
        chat = self.query_one("#chat", VerticalScroll)
        for block in chat.query(SubagentBlock):
            if block.collapsed == self._subagent_expanded:
                block.toggle_collapsed()
        for block in chat.query(ShellBlock):
            if block.collapsed == self._subagent_expanded:
                block.toggle_collapsed()
        for block in chat.query(ToolIndicator):
            if block.tool in ToolIndicator.VERBOSE_TOOLS and block.collapsed == self._subagent_expanded:
                block.toggle_collapsed()
        for block in chat.query(DiffBlock):
            if block.collapsed == self._subagent_expanded:
                block.toggle_collapsed()

    def on_mount(self) -> None:
        self._init_agent()
        # Set initial input container border color
        input_container = self.query_one("#input-container", Container)
        input_container.styles.border_left = ("solid", MODE_COLORS[self._agent_mode])
        
        chat = self.query_one("#chat", VerticalScroll)
        
        # Render chat history from session runs
        self._render_session_history(chat)
        
        chat.scroll_end(animate=False)
        self.query_one("#input", MarkdownInput).focus()
        self.query_one("#autocomplete", AutocompleteWidget).cache_files()

    def _render_session_history(self, chat: VerticalScroll) -> None:
        """Render all messages from session runs into the chat widget."""
        runs = self._session_service.get_runs(self.session)
        
        for run in runs:
            # Render input messages
            for msg in run.input:
                self._render_acp_message(chat, msg)
            
            # Render output messages
            tool_block = None
            for msg in run.output:
                if msg.has_trajectory():
                    # Tool trajectory messages
                    for part in msg.parts:
                        if isinstance(part.metadata, TrajectoryMetadata):
                            if tool_block is None:
                                tool_block = ToolCallBlock()
                                chat.mount(tool_block)
                            tool_block.add_tool(
                                part.metadata.tool_name or "",
                                part.metadata.tool_input or {},
                                finished=True
                            )
                elif msg.is_displayable():
                    tool_block = None
                    text = msg.get_text()
                    if text and msg.role.startswith("agent"):
                        chat.mount(ChatMessage("assistant", text))
                    elif text and msg.role == "user":
                        chat.mount(ChatMessage("user", text))

    def _render_acp_message(self, chat: VerticalScroll, msg: AcpMessage) -> None:
        """Render a single AcpMessage into the chat widget."""
        if msg.is_shell():
            # Shell passthrough message
            command = ""
            output = ""
            for part in msg.parts:
                if part.content_type == "application/x-nora-shell":
                    command = part.content or ""
                    if hasattr(part.metadata, 'output'):
                        output = part.metadata.output or ""
            chat.mount(ShellMessage(command, output))
        elif msg.role == "user":
            text = msg.get_text()
            if text:
                chat.mount(ChatMessage("user", text))
        elif msg.role.startswith("agent"):
            if msg.is_displayable():
                text = msg.get_text()
                if text:
                    chat.mount(ChatMessage("assistant", text))

    def _init_agent(self) -> None:
        messages = self._session_service.get_strands_history(self.session)
        self.agent = self._agent_service.create_agent(
            messages, 
            self.profile, 
            self._agent_mode, 
            self._agent_model, 
            hooks=[self._cancel_hook]
        )

    def _on_model_selected(self, model_id: str | None) -> None:
        if model_id:
            self._agent_model = model_id
            self._init_agent()
            self.query_one("#model-name", Static).update(f" {self._agent_service.get_model_name(model_id)} ")

    def _on_session_selected(self, session: Session | None) -> None:
        if session is None:
            return
        self.session = session
        # Infer mode from the last run in this session, default to vibe
        runs = self._session_service.get_runs(session)
        self._agent_mode = runs[-1].agent_mode if runs else "vibe"
        # Normalize legacy "act" to "edit"
        if self._agent_mode == "act":
            self._agent_mode = "edit"
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self._render_session_history(chat)
        chat.scroll_end(animate=False)
        self._update_status_bar()
        self._init_agent()

    def _start_new_session(self) -> None:
        self.session = Session.create()
        self._agent_mode = "vibe"
        self._session_service.save(self.session)
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self._update_status_bar()
        self._init_agent()

    def _update_status_bar(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        indicator.update(f" {self._agent_mode.upper()} ")
        for mode in MODE_CYCLE:
            indicator.remove_class(f"mode-{mode}")
        indicator.add_class(f"mode-{self._agent_mode}")
        # Update input container border color
        input_container = self.query_one("#input-container", Container)
        input_container.styles.border_left = ("solid", MODE_COLORS[self._agent_mode])

    def action_cycle_mode(self) -> None:
        current_idx = MODE_CYCLE.index(self._agent_mode)
        self._agent_mode = MODE_CYCLE[(current_idx + 1) % len(MODE_CYCLE)]
        self._update_status_bar()
        self._init_agent()

    def action_execute_plan(self) -> None:
        if self._agent_mode != "plan":
            return
        plan_content = self._session_service.get_last_assistant_text(self.session)
        if not plan_content:
            return
        plan = self._plan_service.save_and_link_session(self.session, plan_content)
        self._agent_mode = "edit"
        self._update_status_bar()
        self._init_agent()
        self._session_service.save(self.session)
        self._set_processing(True)
        self._current_worker = self.run_worker(
            self._send_message(self._plan_service.get_implementation_prompt(plan)), 
            exclusive=True
        )

    async def _send_message(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(ChatMessage("user", text))
        chat.scroll_end()
        await self._fetch_response(text)

    def _get_current_word(self, text: str, cursor: int) -> str:
        text_to_cursor = text[:cursor]
        last_space = text_to_cursor.rfind(" ")
        return text_to_cursor[last_space + 1:]

    def _get_word_start_pos(self, text: str, cursor: int) -> int:
        return text[:cursor].rfind(" ") + 1

    def on_text_area_changed(self, event) -> None:
        inp = self.query_one("#input", MarkdownInput)
        if event.text_area != inp:
            return
        ac = self.query_one("#autocomplete", AutocompleteWidget)
        text = inp.internal_value
        cursor = inp._cursor_to_internal(inp.cursor_location[1])

        # Command autocomplete
        if text.startswith("/"):
            ac.show(ac.get_command_matches(text))
            self._ac_trigger = "/"
            self._ac_pos = 0
            return

        # File autocomplete
        word = self._get_current_word(text, cursor)
        if word.startswith("@") and len(word) >= 2:
            ac.show(ac.get_file_matches(word[1:]))
            self._ac_trigger = "@"
            self._ac_pos = self._get_word_start_pos(text, cursor)
            return

        self._ac_trigger = None
        ac.hide()

    def on_key(self, event) -> None:
        ac = self.query_one("#autocomplete", AutocompleteWidget)
        if not ac.has_class("visible"):
            return

        if event.key in ("up", "ctrl+p"):
            ac.move_selection(-1)
            event.prevent_default()
            event.stop()
        elif event.key in ("down", "ctrl+n"):
            ac.move_selection(1)
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            item = ac.get_selected()
            if item:
                self._apply_selection(item.value)
                event.prevent_default()
                event.stop()
        elif event.key == "escape":
            ac.hide()
            self._ac_trigger = None
            event.prevent_default()
            event.stop()

    def _apply_selection(self, value: str) -> None:
        inp = self.query_one("#input", MarkdownInput)
        ac = self.query_one("#autocomplete", AutocompleteWidget)

        if self._ac_trigger == "/":
            inp.set_internal(value, len(value))
            inp.post_message(inp.Submitted(inp, value))
        elif self._ac_trigger == "@":
            text = inp.internal_value
            before = text[:self._ac_pos]
            after_at = text[self._ac_pos + 1:]
            space_idx = after_at.find(" ")
            after = after_at[space_idx + 1:] if space_idx >= 0 else ""
            filename = Path(value).name
            link = f"[{filename}]({value})"
            new_internal = before + link + " " + after
            inp.set_internal(new_internal, len(before + link) + 1)

        ac.hide()
        self._ac_trigger = None

    def _match_plugins(self, text: str) -> list:
        """Use fuzzy matching to find plugins whose keywords match the text."""
        return self._plugin_service.match_plugins(text)

    def on_markdown_input_shell_mode_changed(self, event: MarkdownInput.ShellModeChanged) -> None:
        input_container = self.query_one("#input-container", Container)
        if event.shell_mode:
            input_container.styles.border_left = ("solid", "red")
        else:
            input_container.styles.border_left = ("solid", MODE_COLORS[self._agent_mode])

    async def on_markdown_input_submitted(self, event: MarkdownInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        # Handle shell passthrough commands
        if event.is_shell:
            await self._execute_shell_passthrough(text[1:].strip())  # Strip the ! prefix
            return

        if text == "/exit":
            self.exit()
            return
        if text == "/new":
            self._start_new_session()
            return
        if text == "/model":
            self.push_screen(ModelSelectorModal(self._agent_model), self._on_model_selected)
            return
        if text == "/switch":
            self.push_screen(SwitchModal(), self._on_session_selected)
            return

        # Match plugins based on fuzzy keyword matching
        matched_plugins = self._match_plugins(text)
        
        # If plugins matched, inject them BEFORE the user's message
        if matched_plugins:
            enhanced_text = self._plugin_service.enhance_prompt(text, matched_plugins)
            
            # Display plugin activation indicators and original text in chat
            chat = self.query_one("#chat", VerticalScroll)
            for plugin in matched_plugins:
                chat.mount(Static(f"[cyan bold]🔌 Plugin Activated: {plugin.name}[/cyan bold]"))
            chat.mount(ChatMessage("user", text))
            chat.scroll_end()
            
            # Fetch response with enhanced context
            self._set_processing(True)
            self._current_worker = self.run_worker(self._fetch_response(enhanced_text), exclusive=True)
        else:
            # No plugins matched, proceed normally
            chat = self.query_one("#chat", VerticalScroll)
            chat.mount(ChatMessage("user", text))
            chat.scroll_end()
            
            self._set_processing(True)
            self._current_worker = self.run_worker(self._fetch_response(text), exclusive=True)

    async def _execute_shell_passthrough(self, command: str) -> None:
        """
        Execute a shell passthrough command asynchronously.
        
        Uses asyncio subprocess to avoid blocking the event loop,
        streaming output line-by-line to the ShellMessage widget.
        Saves the command as an AcpMessage.shell() in a Run.
        
        Args:
            command: Shell command to execute (without ! prefix).
        """
        chat = self.query_one("#chat", VerticalScroll)
        
        # Mount the message widget immediately with empty output
        shell_msg = ShellMessage(command, "")
        chat.mount(shell_msg)
        chat.scroll_end()
        
        # Stream output asynchronously
        def on_output(accumulated: str) -> None:
            shell_msg.update_output(accumulated.rstrip())
            chat.scroll_end()
        
        output = await async_execute_shell_command(
            command,
            on_output=on_output,
            cancel_hook=self._cancel_hook,
        )
        
        # Final update with complete output
        if output:
            shell_msg.update_output(output.rstrip())
            chat.scroll_end()
        
        # Save as an AcpMessage.shell() in a Run
        shell_message = AcpMessage.shell(command, output.rstrip() if output else "")
        run = self._run_service.create("nora", [shell_message], self.session.id)
        run.start()
        run.complete([])  # Shell passthrough has no agent output
        self._run_service.save(run)
        
        # Update session
        if not self.session.metadata.name or self.session.name.startswith("Session "):
            self.session.generate_name(f"! {command}")
        self._session_service.save(self.session)

    async def _fetch_response(self, prompt: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat_container = self.query_one("#chat-container", Container)
        loading = LoadingWidget(message="Thinking", style="bar", color=MODE_COLORS[self._agent_mode])
        chat_container.mount(loading)
        chat.scroll_end()

        # Create a Run for this prompt/response cycle
        input_message = AcpMessage.user(prompt)
        run = self._run_service.create("nora", [input_message], self.session.id, agent_mode=self._agent_mode)
        self._run_service.start(run)

        current_content = []
        tool_block = None
        subagent_blocks: dict[str, SubagentBlock] = {}
        shell_blocks: dict[str, ShellBlock] = {}
        indicator_blocks: dict[str, ToolIndicator] = {}
        run_output: list[AcpMessage] = []

        def on_subagent_stream(tool_use_id: str, **kwargs):
            subagent = subagent_blocks.get(tool_use_id)
            if subagent is None:
                return
            if "message" in kwargs:
                msg = kwargs["message"]
                if msg.get("role") == "assistant":
                    for block in msg.get("content", []):
                        if "toolUse" in block:
                            tu = block["toolUse"]
                            self.call_from_thread(subagent.add_nested_tool, tu["name"], tu.get("input", {}))
            if "data" in kwargs:
                self.call_from_thread(subagent.add_nested_content, kwargs["data"])

        def on_stream(**kwargs):
            nonlocal tool_block, current_content
            
            if self._cancel_hook.cancelled:
                return
            
            if "message" in kwargs:
                msg = kwargs["message"]
                if msg.get("role") == "user":
                    for block in msg.get("content", []):
                        if "toolResult" in block:
                            tr = block["toolResult"]
                            tool_use_id = tr.get("toolUseId")
                            if tool_use_id and tool_use_id in subagent_blocks:
                                subagent = subagent_blocks[tool_use_id]
                                if tr.get("status") == "error":
                                    self.call_from_thread(subagent.mark_failed)
                                else:
                                    self.call_from_thread(subagent.mark_finished)
                                del subagent_blocks[tool_use_id]
                            elif tool_use_id and tool_use_id in shell_blocks:
                                shell_block = shell_blocks[tool_use_id]
                                # Extract output from toolResult content
                                output_text = ""
                                for content_block in tr.get("content", []):
                                    if "text" in content_block:
                                        output_text += content_block["text"]
                                if output_text:
                                    self.call_from_thread(shell_block.set_output, output_text)
                                if tr.get("status") == "error":
                                    self.call_from_thread(shell_block.mark_failed)
                                else:
                                    self.call_from_thread(shell_block.mark_finished)
                                del shell_blocks[tool_use_id]
                            elif tool_use_id and tool_use_id in diff_blocks:
                                diff_block = diff_blocks[tool_use_id]
                                if tr.get("status") == "error":
                                    self.call_from_thread(diff_block.mark_failed)
                                # Already marked finished in on_diff callback
                                del diff_blocks[tool_use_id]
                            elif tool_use_id and tool_use_id in indicator_blocks:
                                ind = indicator_blocks[tool_use_id]
                                # Extract output for verbose tools
                                output_text = ""
                                for content_block in tr.get("content", []):
                                    if "text" in content_block:
                                        output_text += content_block["text"]
                                if output_text and ind.tool in ToolIndicator.VERBOSE_TOOLS:
                                    self.call_from_thread(ind.set_output, output_text)
                                if tr.get("status") == "error":
                                    self.call_from_thread(ind.mark_failed)
                                else:
                                    self.call_from_thread(ind.mark_finished)
                                del indicator_blocks[tool_use_id]
                            else:
                                indicators = chat.query(ToolIndicator)
                                for ind in reversed(list(indicators)):
                                    if not ind.finished:
                                        if tr.get("status") == "error":
                                            self.call_from_thread(ind.mark_failed)
                                        else:
                                            self.call_from_thread(ind.mark_finished)
                                        break
                elif msg.get("role") == "assistant":
                    for block in msg.get("content", []):
                        if "toolUse" in block:
                            if current_content:
                                text = "".join(current_content)
                                run_output.append(AcpMessage.agent(text))
                                self.call_from_thread(chat.mount, ChatMessage("assistant", text))
                                current_content = []
                            
                            tu = block["toolUse"]
                            tool_name = tu["name"]
                            tool_use_id = tu.get("toolUseId")
                            tool_input = tu.get("input", {})
                            
                            # Record tool trajectory
                            run_output.append(AcpMessage.tool_trajectory(
                                tool_name=tool_name,
                                tool_input=tool_input,
                                tool_output="",
                            ))
                            
                            if tool_name == "Subagent":
                                subagent_reason = tool_input.get("reason", "Running subagent.")
                                subagent_block = SubagentBlock(subagent_reason, collapsed=not self._subagent_expanded)
                                if tool_use_id:
                                    subagent_blocks[tool_use_id] = subagent_block
                                self.call_from_thread(chat.mount, subagent_block)
                                tool_block = None
                            elif tool_name == "Shell":
                                program = tool_input.get("program", "")
                                args = tool_input.get("args", [])
                                reason = tool_input.get("reason", "")
                                shell_block = ShellBlock(program, args, reason, collapsed=not self._subagent_expanded)
                                if tool_use_id:
                                    shell_blocks[tool_use_id] = shell_block
                                self.call_from_thread(chat.mount, shell_block)
                                tool_block = None
                            elif tool_name in ("Write", "Edit") and self._agent_mode in ("edit", "act"):
                                # In edit mode, DiffBlock is created via diff_callback
                                # from inside the tool — skip creating a ToolIndicator
                                tool_block = None
                            else:
                                if tool_block is None:
                                    tool_block = ToolCallBlock()
                                    self.call_from_thread(chat.mount, tool_block)
                                collapsed = not self._subagent_expanded
                                indicator = ToolIndicator(tool_name, tool_input, collapsed=collapsed)
                                if tool_use_id:
                                    indicator_blocks[tool_use_id] = indicator
                                self.call_from_thread(tool_block.mount, indicator)
                            
                            self.call_from_thread(chat.scroll_end)

            if "data" in kwargs:
                tool_block = None
                current_content.append(kwargs["data"])

        def on_shell_output(tool_use_id: str, accumulated: str):
            """Route streaming shell output to the correct ShellBlock."""
            shell_block = shell_blocks.get(tool_use_id)
            if shell_block is not None:
                self.call_from_thread(shell_block.set_output, accumulated)
                self.call_from_thread(chat.scroll_end)

        diff_blocks: dict[str, DiffBlock] = {}

        def on_diff(tool_use_id: str, path: str, old_content: str, new_content: str, reason: str):
            """Mount a DiffBlock in chat for auto-approved file changes."""
            # If old_content was empty, it's a new file (Write); otherwise it's an Edit
            tool_name = "Write" if not old_content else "Edit"
            block = DiffBlock(
                path, old_content, new_content, reason,
                tool_name=tool_name,
                collapsed=not self._subagent_expanded,
            )
            block.finished = True  # Already written to disk
            if tool_use_id:
                diff_blocks[tool_use_id] = block
            self.call_from_thread(chat.mount, block)
            self.call_from_thread(chat.scroll_end)

        self.agent.callback_handler = on_stream
        invocation_state = {
            "subagent_callback": on_subagent_stream,
            "shell_output_callback": on_shell_output,
            "diff_callback": on_diff,
            "profile": self.profile,
            "cancel_hook": self._cancel_hook,
            "session_id": str(self.session.id),
            "agent_mode": self._agent_mode,
        }
        loop = asyncio.get_event_loop()
        rejected = False
        cancelled = False
        # Track message count before this run so we only save NEW messages
        messages_before_run = len(self.agent.messages)

        # Store invocation state so action_ctrl_c can snapshot messages
        # and save the partial run if the user cancels mid-execution.
        self._active_invocation = _ActiveInvocation(
            agent=self.agent,
            run=run,
            messages_before=messages_before_run,
        )

        def mark_last_tool_failed():
            indicators = chat.query(ToolIndicator)
            for ind in reversed(list(indicators)):
                if not ind.finished:
                    ind.mark_failed()
                    break

        def run_agent_with_cancellation(input_data):
            if self._cancel_hook.cancelled:
                return None
            return self.agent(input_data, invocation_state=invocation_state)

        try:
            result = await loop.run_in_executor(None, lambda: run_agent_with_cancellation(prompt))
            
            if result is None:
                cancelled = True
            else:
                while result.stop_reason == "interrupt" and not rejected and not self._cancel_hook.cancelled:
                    responses = []
                    for interrupt in result.interrupts:
                        approval = await self._get_confirmation(interrupt.name, interrupt.reason)
                        if approval == "reject":
                            rejected = True
                            mark_last_tool_failed()
                            break
                        responses.append({
                            "interruptResponse": {
                                "interruptId": interrupt.id,
                                "response": approval
                            }
                        })
                    if not rejected and not self._cancel_hook.cancelled:
                        result = await loop.run_in_executor(None, lambda: run_agent_with_cancellation(responses))
                        if result is None:
                            cancelled = True
                            break
        except asyncio.CancelledError:
            cancelled = True
        except Exception as e:
            if self._cancel_hook.cancelled:
                cancelled = True
            else:
                raise

        loading.remove()

        if cancelled or self._cancel_hook.cancelled:
            # If action_ctrl_c already saved the partial run and replaced the
            # agent, skip — avoid double-saving or operating on the wrong agent.
            if self._active_invocation is None:
                return
            # Clear interrupt state so next message can be a regular string prompt
            self.agent._interrupt_state.deactivate()
            # Save run as cancelled
            self._run_service.cancel(run)
            self._run_service.confirm_cancel(run)
            self._run_service.save(run, list(self.agent.messages[messages_before_run:]))
        elif rejected:
            # Clear interrupt state so next message can be a regular string prompt
            self.agent._interrupt_state.deactivate()
            # Save run as completed with whatever output we have
            if current_content:
                text = "".join(current_content)
                run_output.append(AcpMessage.agent(text))
                chat.mount(ChatMessage("assistant", text))
                chat.scroll_end()
            self._run_service.complete(run, run_output)
            self._run_service.save(run, list(self.agent.messages[messages_before_run:]))
        else:
            if current_content:
                text = "".join(current_content)
                run_output.append(AcpMessage.agent(text))
                chat.mount(ChatMessage("assistant", text))
                chat.scroll_end()
            # Complete the run with all output
            self._run_service.complete(run, run_output)
            self._run_service.save(run, list(self.agent.messages[messages_before_run:]))
        
        # Update session metadata
        if not self.session.metadata.name or self.session.name.startswith("Session "):
            self.session.generate_name(prompt)
        self._session_service.save(self.session)
        self._active_invocation = None
        self._set_processing(False)

    async def _get_confirmation(self, name: str, reason: dict) -> str:
        """Show confirmation modal and return user response."""
        if name == "diff-confirm":
            return await self.push_screen_wait(DiffModal(reason["path"], reason["old"], reason["new"], reason["reason"]))
        if name == "shell-confirm":
            return await self._handle_shell_confirmation(reason)
        tool_name = name.replace("-confirm", "")
        return await self.push_screen_wait(ToolConfirmModal(tool_name, reason))
    
    async def _handle_shell_confirmation(self, reason: dict) -> str:
        """
        Handle shell command approval with trust policy flow.
        
        Uses async subprocess execution to avoid blocking the event loop
        while the command runs after approval.
        
        Args:
            reason: Dict containing program, args, reason, command, session_id.
            
        Returns:
            Command output or rejection message.
        """
        program = reason["program"]
        args = reason["args"]
        cmd_reason = reason["reason"]
        session_id = reason.get("session_id", str(self.session.id))
        
        # Show initial approval modal
        decision = await self.push_screen_wait(
            ShellApprovalModal(program, args, cmd_reason)
        )
        
        if decision == "n":
            return "reject"
        
        if decision == "y":
            # Allow once - execute asynchronously without saving policy
            result = await async_execute_command(
                program, args,
                cancel_hook=self._cancel_hook,
            )
            return result
        
        # For 't' (trust permanent) or 's' (trust session), show trust level modal
        trust_service = TrustService()
        trust_levels = trust_service.get_trust_levels(program, args)
        
        level_selection = await self.push_screen_wait(
            TrustLevelModal(trust_levels)
        )
        
        if level_selection is None:
            # User pressed Escape - deny the command
            return "reject"
        
        # Save the policy
        selected_level = trust_levels[level_selection - 1]
        trust_decision = (
            TrustDecision.TRUST_PERMANENT if decision == "t" 
            else TrustDecision.TRUST_SESSION
        )
        trust_service.save_policy(program, selected_level, trust_decision, session_id)
        
        # Execute the command asynchronously
        result = await async_execute_command(
            program, args,
            cancel_hook=self._cancel_hook,
        )
        return result

    def _update_message(self, content: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        widgets = chat.query(".message-assistant")
        if widgets:
            widgets.last().update_content(content)
        chat.scroll_end()


def run_tui(session: Session, profile: Optional[str] = None) -> None:
    ChatApp(session, profile).run()
