"""Main TUI application."""

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Static
from thefuzz import fuzz

from nora.models import Thread, Message
from nora.models.thread import Mode
from nora.storage import save_thread
from nora.storage.plugins import load_plugins
from nora.storage.plans import save_plan
from nora.core import create_agent, get_model_name, MODEL_ID, CancellationHook
from nora.tui.widgets import ChatMessage, ToolCallBlock, SubagentBlock, AutocompleteWidget, LoadingWidget, MarkdownInput, ToolConfirmModal, ModelSelectorModal, DiffModal, SwitchModal, AddPluginModal
from nora.storage.plugins import load_plugins
from nora.tui import events

MODE_COLORS = {"vibe": "cyan", "plan": "yellow", "act": "green"}
MODE_CYCLE: list[Mode] = ["vibe", "plan", "act"]


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
        self.agent = None
        self._ac_trigger: Optional[str] = None
        self._ac_pos: int = 0
        self._pending_tool: Optional[dict] = None
        self._ctrl_c_pressed = False
        self._current_model = MODEL_ID
        self._plugins = []
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
            yield Static(f" {get_model_name()} ", id="model-name")
            yield Static("", id="status-spacer")
            yield Static("@file  /cmd  Esc quit", id="status-keys")

    def action_ctrl_c(self) -> None:
        if self._processing and self._current_worker:
            # Signal cancellation to the agent via hook
            self._cancel_hook.cancel()
            self._current_worker.cancel()
            self._set_processing(False)
            # Clean up loading widget if present
            chat_container = self.query_one("#chat-container", Container)
            for loading in chat_container.query(LoadingWidget):
                loading.remove()
            # Agent retains its state (files read, context, etc.)
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
            self._cancel_hook.reset()  # Reset cancellation flag
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
            # Set collapsed to opposite of expanded
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
        self._plugins = load_plugins(startup_only=True)

    def _init_agent(self) -> None:
        messages = [{"role": m.role, "content": [{"text": m.content}]} for m in self.thread.messages if m.role != "tool_call" and m.content]
        self.agent = create_agent(messages, self.profile, self.thread.mode, self._current_model, hooks=[self._cancel_hook])

    def _on_model_selected(self, model_id: str | None) -> None:
        if model_id:
            self._current_model = model_id
            self._init_agent()
            self.query_one("#model-name", Static).update(f" {get_model_name(model_id)} ")

    def _on_thread_selected(self, thread: Thread | None) -> None:
        if thread is None:
            return
        self.thread = thread
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        # Reload messages from selected thread
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
            # Reload plugins
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
        idx = MODE_CYCLE.index(self.thread.mode)
        self.thread.mode = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]
        self._update_status_bar()
        self._init_agent()
        save_thread(self.thread)

    def action_execute_plan(self) -> None:
        if self.thread.mode != "plan":
            return
        # Get last assistant message as plan content
        plan_content = ""
        for msg in reversed(self.thread.messages):
            if msg.role == "assistant" and msg.content:
                plan_content = msg.content
                break
        if not plan_content:
            return
        plan = save_plan(self.thread.id, plan_content)
        self.thread.plan_id = plan.id
        self.thread.mode = "act"
        self._update_status_bar()
        self._init_agent()
        save_thread(self.thread)
        # Send implementing message
        self._set_processing(True)
        self._current_worker = self.run_worker(self._send_message(f"Implementing Plan: {plan.id}-{plan.description}"), exclusive=True)

    async def _send_message(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(ChatMessage("user", text))
        chat.scroll_end()
        self.thread.messages.append(Message(role="user", content=text))
        await self._fetch_response(text)

    def on_text_area_changed(self, event) -> None:
        inp = self.query_one("#input", MarkdownInput)
        if event.text_area != inp:
            return
        ac = self.query_one("#autocomplete", AutocompleteWidget)
        text = inp.internal_value
        cursor = inp._cursor_to_internal(inp.cursor_location[1])

        if events.try_cmd_autocomplete(text, ac):
            self._ac_trigger = "/"
            self._ac_pos = 0
            return
        if events.try_file_autocomplete(text, cursor, ac):
            self._ac_trigger = "@"
            self._ac_pos = events.get_word_start_pos(text, cursor)
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
            events.apply_cmd_selection(inp, value)
        elif self._ac_trigger == "@":
            events.apply_file_selection(inp, value, self._ac_pos)

        ac.hide()
        self._ac_trigger = None

    def _match_plugins(self, text: str) -> list:
        """Use fuzzy matching to find plugins whose keywords match the text."""
        matched_plugins = []
        text_lower = text.lower()
        
        for plugin in self._plugins:
            # Check each keyword against the text using fuzzy matching
            for keyword in plugin.keywords:
                # Partial ratio works well for finding keyword in longer text
                ratio = fuzz.partial_ratio(keyword.lower(), text_lower)
                if ratio >= 80:  # 80% similarity threshold
                    matched_plugins.append(plugin)
                    break  # Don't add same plugin multiple times
        
        return matched_plugins

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
            plugin_context = ""
            for plugin in matched_plugins:
                plugin_context += f"<PluginDetails name='{plugin.name}'>\n{plugin.instructions}\n</PluginDetails>\n\n"
            
            # Plugin context comes BEFORE user's text so agent can use it to respond
            enhanced_text = plugin_context + text
            
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
        subagent_blocks: dict[str, SubagentBlock] = {}  # Track by toolUseId

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
            
            # Check for cancellation
            if self._cancel_hook.cancelled:
                return
            
            if "message" in kwargs:
                msg = kwargs["message"]
                if msg.get("role") == "user":
                    for block in msg.get("content", []):
                        if "toolResult" in block:
                            tr = block["toolResult"]
                            tool_use_id = tr.get("toolUseId")
                            # Check if this is a subagent result
                            if tool_use_id and tool_use_id in subagent_blocks:
                                subagent = subagent_blocks[tool_use_id]
                                if tr.get("status") == "error":
                                    self.call_from_thread(subagent.mark_failed)
                                else:
                                    self.call_from_thread(subagent.mark_finished)
                                del subagent_blocks[tool_use_id]
                            else:
                                indicators = chat.query("ToolIndicator")
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
                            # Flush current content as a message before tool use
                            if current_content:
                                text = "".join(current_content)
                                self.thread.messages.append(Message(role="assistant", content=text))
                                self.call_from_thread(chat.mount, ChatMessage("assistant", text))
                                current_content = []
                            
                            tu = block["toolUse"]
                            tool_name = tu["name"]
                            tool_use_id = tu.get("toolUseId")
                            
                            if tool_name == "Subagent":
                                # Create subagent block with current expanded state
                                subagent_prompt = tu.get("input", {}).get("prompt", "")
                                subagent_block = SubagentBlock(subagent_prompt, collapsed=not self._subagent_expanded)
                                if tool_use_id:
                                    subagent_blocks[tool_use_id] = subagent_block
                                self.call_from_thread(chat.mount, subagent_block)
                                tool_block = None
                            else:
                                if tool_block is None:
                                    tool_block = ToolCallBlock()
                                    self.call_from_thread(chat.mount, tool_block)
                                self.call_from_thread(tool_block.add_tool, tool_name, tu.get("input", {}))
                            
                            self.call_from_thread(chat.scroll_end)
                            self.thread.messages.append(Message(
                                role="tool_call",
                                tool=tool_name,
                                parameters=tu.get("input", {})
                            ))

            if "data" in kwargs:
                tool_block = None
                current_content.append(kwargs["data"])

        self.agent.callback_handler = on_stream
        invocation_state = {"subagent_callback": on_subagent_stream, "profile": self.profile, "cancel_hook": self._cancel_hook}
        loop = asyncio.get_event_loop()
        rejected = False
        cancelled = False

        def mark_last_tool_failed():
            indicators = chat.query("ToolIndicator")
            for ind in reversed(list(indicators)):
                if not ind.finished:
                    ind.mark_failed()
                    break

        def run_agent_with_cancellation(input_data):
            """Wrapper that checks cancellation before executing agent."""
            if self._cancel_hook.cancelled:
                return None
            return self.agent(input_data, invocation_state=invocation_state)

        try:
            result = await loop.run_in_executor(None, lambda: run_agent_with_cancellation(prompt))
            
            if result is None:  # Cancelled before execution
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
                        if result is None:  # Cancelled during continuation
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
            pass  # Keep agent state - it retains context from files read, etc.
        elif rejected:
            pass  # Keep agent state after rejection too
        else:
            # Flush any remaining content
            if current_content:
                text = "".join(current_content)
                self.thread.messages.append(Message(role="assistant", content=text))
                chat.mount(ChatMessage("assistant", text))
                chat.scroll_end()
        save_thread(self.thread)
        self._set_processing(False)

    async def _get_confirmation(self, name: str, reason: dict) -> str:
        """Show confirmation modal and return user response."""
        if name == "diff-confirm":
            return await self.push_screen_wait(DiffModal(reason["path"], reason["old"], reason["new"]))
        tool_name = name.replace("-confirm", "")
        return await self.push_screen_wait(ToolConfirmModal(tool_name, reason))

    def _update_message(self, content: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        widgets = chat.query(".message-assistant")
        if widgets:
            widgets.last().update_content(content)
        chat.scroll_end()


def run_tui(thread: Thread, profile: Optional[str] = None) -> None:
    ChatApp(thread, profile).run()
