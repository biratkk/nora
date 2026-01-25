"""Main TUI application."""

import asyncio
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Static
from thefuzz import fuzz

from nora.models import Thread, Message
from nora.models.thread import Mode
from nora.config.constants import DEFAULT_MODEL_ID, MODE_CYCLE
from nora.services.settings_service import SettingsService
from nora.services.thread_service import ThreadService
from nora.services.plugin_service import PluginService
from nora.services.plan_service import PlanService
from nora.services.agent_service import AgentService, CancellationHook
from nora.widgets import ChatMessage, ToolCallBlock, SubagentBlock, ShellBlock, AutocompleteWidget, LoadingWidget, MarkdownInput
from nora.screens import ToolConfirmModal, ModelSelectorModal, DiffModal, SwitchModal, AddPluginModal, ShellApprovalModal, TrustLevelModal
from nora.services.trust_service import TrustService, TrustDecision
from nora.tools.shell import execute_shell_after_approval

MODE_COLORS = {"vibe": "cyan", "plan": "yellow", "act": "green"}


class ChatApp(App):
    CSS = """
    VerticalScroll { scrollbar-size: 1 1; }
    #main { padding: 1 2; background: black; }
    #chat-area { width: 1fr; height: 1fr; }
    #chat-container { height: 1fr; }
    #chat { height: 1fr; }
    .message-user, .message-assistant { padding: 0 1; height: auto; margin-bottom: 1; }
    .message-user { border-left: solid $primary; background: $primary 10%; padding: 1; }
    .message-assistant { }
    .message-tool { height: auto; padding: 0 1; margin: 1 0; }
    .message-content { margin: 0; padding: 0; }
    .message-time { dock: right; width: auto; }
    .message-user Markdown { margin: 0; padding: 0; }
    .message-user MarkdownBlock { margin: 0; padding: 0; }
    ToolIndicator { height: 1; }
    MarkdownHeader { content-align: left middle; }
    #input-container { padding: 0 1 1 1; height: auto; dock: bottom; }
    #input { height: auto; min-height: 3; max-height: 30; border: round $accent; background: transparent; }
    #input.disabled { opacity: 0.5; }
    #cancel-hint { height: 1; color: $text-muted; padding: 0 1; }
    #autocomplete { dock: bottom; margin-bottom: 4; }
    #status-bar { height: 1; dock: bottom; background: $surface; }
    #mode-indicator { width: auto; padding: 0 1; }
    .mode-vibe { background: cyan; color: black; }
    .mode-plan { background: yellow; color: black; }
    .mode-act { background: green; color: black; }
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

    def __init__(self, thread: Thread, profile: Optional[str] = None):
        super().__init__()
        self.thread = thread
        self.profile = profile
        
        # Services
        self._thread_service = ThreadService()
        self._plugin_service = PluginService()
        self._plan_service = PlanService()
        self._agent_service = AgentService()
        
        # State
        self.agent = None
        self._ac_trigger: Optional[str] = None
        self._ac_pos: int = 0
        self._ctrl_c_pressed = False
        self._current_model = DEFAULT_MODEL_ID
        self._processing = False
        self._current_worker = None
        self._cancel_hook = CancellationHook()
        self._subagent_expanded = False

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            with Container(id="chat-container"):
                yield VerticalScroll(id="chat")
            yield AutocompleteWidget(id="autocomplete")
            with Container(id="input-container"):
                yield MarkdownInput(placeholder="Type a message... (@file /cmd)", id="input")
                yield Static("", id="cancel-hint")
        with Horizontal(id="status-bar"):
            yield Static(f" {self.thread.mode.upper()} ", id="mode-indicator", classes=f"mode-{self.thread.mode}")
            yield Static(f" {self._agent_service.get_model_name()} ", id="model-name")
            yield Static("", id="status-spacer")
            yield Static("@file  /cmd  Esc quit", id="status-keys")

    def action_ctrl_c(self) -> None:
        if self._processing and self._current_worker:
            self._cancel_hook.cancel()
            self._current_worker.cancel()
            self._set_processing(False)
            chat_container = self.query_one("#chat-container", Container)
            for loading in chat_container.query(LoadingWidget):
                loading.remove()
            return
        
        if self._ctrl_c_pressed:
            self.exit()
        else:
            self._ctrl_c_pressed = True
            self.set_timer(1.0, self._reset_ctrl_c)

    def _reset_ctrl_c(self) -> None:
        self._ctrl_c_pressed = False

    def _set_processing(self, processing: bool) -> None:
        self._processing = processing
        inp = self.query_one("#input", MarkdownInput)
        hint = self.query_one("#cancel-hint", Static)
        if processing:
            self._cancel_hook.reset()
            inp.disabled = True
            inp.add_class("disabled")
            hint.update("[dim]Ctrl+C to cancel[/dim]")
        else:
            inp.disabled = False
            inp.remove_class("disabled")
            hint.update("")
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

    def on_mount(self) -> None:
        self._load_plugins()
        self._init_agent()
        chat = self.query_one("#chat", VerticalScroll)
        
        tool_block = None
        for msg in self.thread.messages:
            if msg.role == "tool_call":
                if tool_block is None:
                    tool_block = ToolCallBlock()
                    chat.mount(tool_block)
                tool_block.add_tool(msg.tool or "", msg.parameters or {}, finished=True)
            else:
                tool_block = None
                chat.mount(ChatMessage(msg.role, msg.content or ""))
        chat.scroll_end(animate=False)
        self.query_one("#input", MarkdownInput).focus()
        self.query_one("#autocomplete", AutocompleteWidget).cache_files()

    def _load_plugins(self) -> None:
        """Load plugins from $CWD/.nora/plugins/."""
        self._plugin_service.load_all(startup_only=True)

    def _init_agent(self) -> None:
        messages = self.thread.to_agent_messages()
        self.agent = self._agent_service.create_agent(
            messages, 
            self.profile, 
            self.thread.mode, 
            self._current_model, 
            hooks=[self._cancel_hook]
        )

    def _on_model_selected(self, model_id: str | None) -> None:
        if model_id:
            self._current_model = model_id
            self._init_agent()
            self.query_one("#model-name", Static).update(f" {self._agent_service.get_model_name(model_id)} ")

    def _on_thread_selected(self, thread: Thread | None) -> None:
        if thread is None:
            return
        self.thread = thread
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        tool_block = None
        for msg in self.thread.messages:
            if msg.role == "tool_call":
                if tool_block is None:
                    tool_block = ToolCallBlock()
                    chat.mount(tool_block)
                tool_block.add_tool(msg.tool or "", msg.parameters or {}, finished=True)
            else:
                tool_block = None
                chat.mount(ChatMessage(msg.role, msg.content or ""))
        chat.scroll_end(animate=False)
        self._update_status_bar()
        self._init_agent()

    def _on_plugin_created(self, plugin_path) -> None:
        """Handle plugin creation confirmation."""
        if plugin_path:
            chat = self.query_one("#chat", VerticalScroll)
            chat.mount(Static(f"[green]✓[/green] Plugin created: {plugin_path.name}"))
            chat.scroll_end()
            self._load_plugins()
            self._init_agent()

    def _start_new_thread(self) -> None:
        self.thread = Thread.create()
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self._init_agent()

    def _update_status_bar(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        indicator.update(f" {self.thread.mode.upper()} ")
        for mode in MODE_CYCLE:
            indicator.remove_class(f"mode-{mode}")
        indicator.add_class(f"mode-{self.thread.mode}")

    def action_cycle_mode(self) -> None:
        self._thread_service.cycle_mode(self.thread)
        self._update_status_bar()
        self._init_agent()
        self._thread_service.save(self.thread)

    def action_execute_plan(self) -> None:
        if self.thread.mode != "plan":
            return
        plan_content = self._thread_service.get_last_assistant_message(self.thread)
        if not plan_content:
            return
        plan = self._plan_service.save_and_link(self.thread, plan_content)
        self._update_status_bar()
        self._init_agent()
        self._thread_service.save(self.thread)
        self._set_processing(True)
        self._current_worker = self.run_worker(
            self._send_message(self._plan_service.get_implementation_prompt(plan)), 
            exclusive=True
        )

    async def _send_message(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(ChatMessage("user", text))
        chat.scroll_end()
        self.thread.messages.append(Message(role="user", content=text))
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

    async def on_markdown_input_submitted(self, event: MarkdownInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        if text == "/exit":
            self.exit()
            return
        if text == "/new":
            self._start_new_thread()
            return
        if text == "/model":
            self.push_screen(ModelSelectorModal(self._current_model), self._on_model_selected)
            return
        if text == "/switch":
            self.push_screen(SwitchModal(), self._on_thread_selected)
            return
        if text == "/add-plugin":
            self.push_screen(AddPluginModal(profile=self.profile), self._on_plugin_created)
            return

        # Match plugins based on fuzzy keyword matching
        matched_plugins = self._match_plugins(text)
        
        # If plugins matched, inject them BEFORE the user's message
        if matched_plugins:
            enhanced_text = self._plugin_service.enhance_prompt(text, matched_plugins)
            
            # Add user message to thread (with enhanced context)
            self.thread.messages.append(Message(role="user", content=enhanced_text))
            
            # Display only the original text in chat (not the plugin details)
            chat = self.query_one("#chat", VerticalScroll)
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
            
            self.thread.messages.append(Message(role="user", content=text))
            self._set_processing(True)
            self._current_worker = self.run_worker(self._fetch_response(text), exclusive=True)

    async def _fetch_response(self, prompt: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat_container = self.query_one("#chat-container", Container)
        loading = LoadingWidget(message="Thinking")
        chat_container.mount(loading)
        chat.scroll_end()

        current_content = []
        tool_block = None
        subagent_blocks: dict[str, SubagentBlock] = {}
        shell_blocks: dict[str, ShellBlock] = {}

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
                                if tr.get("status") == "error":
                                    self.call_from_thread(shell_block.mark_failed)
                                else:
                                    self.call_from_thread(shell_block.mark_finished)
                                del shell_blocks[tool_use_id]
                            else:
                                from nora.widgets.chat import ToolIndicator
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
                                self.thread.messages.append(Message(role="assistant", content=text))
                                self.call_from_thread(chat.mount, ChatMessage("assistant", text))
                                current_content = []
                            
                            tu = block["toolUse"]
                            tool_name = tu["name"]
                            tool_use_id = tu.get("toolUseId")
                            tool_input = tu.get("input", {})
                            
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
                            else:
                                if tool_block is None:
                                    tool_block = ToolCallBlock()
                                    self.call_from_thread(chat.mount, tool_block)
                                self.call_from_thread(tool_block.add_tool, tool_name, tool_input)
                            
                            self.call_from_thread(chat.scroll_end)
                            self.thread.messages.append(Message(
                                role="tool_call",
                                tool=tool_name,
                                parameters=tool_input
                            ))

            if "data" in kwargs:
                tool_block = None
                current_content.append(kwargs["data"])

        self.agent.callback_handler = on_stream
        invocation_state = {"subagent_callback": on_subagent_stream, "profile": self.profile, "cancel_hook": self._cancel_hook, "thread_id": self.thread.id}
        loop = asyncio.get_event_loop()
        rejected = False
        cancelled = False

        def mark_last_tool_failed():
            from nora.widgets.chat import ToolIndicator
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
            # Clear interrupt state so next message can be a regular string prompt
            # Note: agent.messages (conversation history) is preserved, only interrupt tracking is cleared
            self.agent._interrupt_state.deactivate()
        elif rejected:
            # Clear interrupt state so next message can be a regular string prompt
            # Note: agent.messages (conversation history) is preserved, only interrupt tracking is cleared
            self.agent._interrupt_state.deactivate()
        else:
            if current_content:
                text = "".join(current_content)
                self.thread.messages.append(Message(role="assistant", content=text))
                chat.mount(ChatMessage("assistant", text))
                chat.scroll_end()
        
        # Sync raw agent messages to preserve toolUse/toolResult structure for session restore
        self.thread.raw_messages = list(self.agent.messages)
        self._thread_service.save(self.thread)
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
        
        Args:
            reason: Dict containing program, args, reason, command, thread_id.
            
        Returns:
            Command output or rejection message.
        """
        program = reason["program"]
        args = reason["args"]
        cmd_reason = reason["reason"]
        thread_id = reason.get("thread_id", self.thread.id)
        
        # Show initial approval modal
        decision = await self.push_screen_wait(
            ShellApprovalModal(program, args, cmd_reason)
        )
        
        if decision == "n":
            return "reject"
        
        if decision == "y":
            # Allow once - execute without saving policy
            result = execute_shell_after_approval(program, args)
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
        trust_service.save_policy(program, selected_level, trust_decision, thread_id)
        
        # Execute the command
        result = execute_shell_after_approval(program, args)
        return result

    def _update_message(self, content: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        widgets = chat.query(".message-assistant")
        if widgets:
            widgets.last().update_content(content)
        chat.scroll_end()


def run_tui(thread: Thread, profile: Optional[str] = None) -> None:
    ChatApp(thread, profile).run()
