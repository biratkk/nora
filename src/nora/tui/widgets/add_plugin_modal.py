"""Plugin creation modal."""

import asyncio
from textual import events, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, Checkbox, Button, TextArea
from textual.binding import Binding

from nora.tui.widgets.modal import BaseModal
from nora.storage.plugins import Plugin, save_plugin, validate_plugin_name


async def generate_plugin_metadata(name: str, instructions: str, profile: str | None = None) -> tuple[str, list[str]]:
    """Use a Strands agent to generate description and keywords for a plugin."""
    import boto3
    from strands import Agent
    from strands.models import BedrockModel
    
    kwargs = {"model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"}
    if profile:
        kwargs["boto_session"] = boto3.Session(profile_name=profile)
    model = BedrockModel(**kwargs)
    
    prompt = f"""Given this plugin name and instructions, generate:
1. A brief one-sentence description (max 100 chars)
2. Up to 30 relevant keywords that would help match user queries to this plugin

Plugin Name: {name}

Instructions:
{instructions}

Respond in this exact format (no extra text):
DESCRIPTION: <one sentence description>
KEYWORDS: <comma-separated keywords>"""

    agent = Agent(model=model, tools=[], system_prompt="You are a helpful assistant that generates metadata for plugins. Respond only in the exact format requested.")
    
    result = await asyncio.to_thread(agent, prompt)
    response = str(result)
    
    # Parse response
    description = ""
    keywords = []
    
    for line in response.strip().split("\n"):
        if line.startswith("DESCRIPTION:"):
            description = line.replace("DESCRIPTION:", "").strip()
        elif line.startswith("KEYWORDS:"):
            keywords_str = line.replace("KEYWORDS:", "").strip()
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()][:30]
    
    return description, keywords


class AddPluginModal(BaseModal):
    """Multi-step modal for creating plugins."""
    
    STEPS = ["name", "instructions", "advanced"]
    
    STEP_TITLES = {
        "name": "Plugin Name",
        "instructions": "Instructions",
        "advanced": "Advanced Options"
    }
    
    STEP_HINTS = {
        "name": "Enter a unique name (no spaces, /, or \\)",
        "instructions": "Enter the plugin instructions (Enter for newline, Ctrl+D to continue)",
        "advanced": "Space to toggle checkbox, Enter to create plugin"
    }
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, profile: str | None = None):
        super().__init__()
        self.current_step = 0
        self.profile = profile
        self.data = {
            "name": "",
            "instructions": "",
            "load_on_startup": True
        }
        self._generating = False
    
    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Static(self._get_title(), id="modal-title")
            yield Static("", id="error-message")
            with Vertical(id="step-content"):
                yield from self._compose_step_content()
            yield Static(self._get_hint(), id="step-hint", classes="dim")
            with Horizontal(id="nav-hint"):
                yield Static("[dim]Backspace: Back | Esc: Cancel[/dim]")
    
    def _get_title(self) -> str:
        step = self.STEPS[self.current_step]
        step_num = self.current_step + 1
        total = len(self.STEPS)
        return f"[bold]Add Plugin[/bold] - Step {step_num}/{total}: {self.STEP_TITLES[step]}"
    
    def _get_hint(self) -> str:
        step = self.STEPS[self.current_step]
        return self.STEP_HINTS[step]
    
    def _compose_step_content(self) -> ComposeResult:
        step = self.STEPS[self.current_step]
        
        if step == "advanced":
            yield Checkbox("Load at startup", id="load_on_startup", value=self.data["load_on_startup"])
            yield Static("")
            yield Button("Create Plugin", id="submit-btn", variant="primary")
        elif step == "instructions":
            yield TextArea(
                self.data["instructions"],
                id="input_instructions"
            )
        else:
            yield Input(
                placeholder=self.STEP_HINTS[step],
                value=self.data[step],
                id=f"input_{step}"
            )
    
    def _refresh_content(self) -> None:
        """Refresh the modal content for current step."""
        # Update title
        title = self.query_one("#modal-title", Static)
        title.update(self._get_title())
        
        # Update hint
        hint = self.query_one("#step-hint", Static)
        hint.update(self._get_hint())
        
        # Clear error
        error = self.query_one("#error-message", Static)
        error.update("")
        
        # Rebuild step content
        content = self.query_one("#step-content", Vertical)
        content.remove_children()
        
        step = self.STEPS[self.current_step]
        if step == "advanced":
            checkbox = Checkbox("Load at startup", id="load_on_startup", value=self.data["load_on_startup"])
            content.mount(checkbox)
            content.mount(Static(""))
            content.mount(Button("Create Plugin", id="submit-btn", variant="primary"))
        elif step == "instructions":
            text_area = TextArea(self.data["instructions"], id="input_instructions")
            content.mount(text_area)
            text_area.focus()
        else:
            input_widget = Input(
                placeholder=self.STEP_HINTS[step],
                value=self.data[step],
                id=f"input_{step}"
            )
            content.mount(input_widget)
            input_widget.focus()
    
    def on_mount(self) -> None:
        """Focus the first input on mount."""
        self.call_after_refresh(self._focus_input)
    
    def _focus_input(self) -> None:
        """Focus the current input."""
        step = self.STEPS[self.current_step]
        if step == "instructions":
            try:
                text_area = self.query_one("#input_instructions", TextArea)
                text_area.focus()
            except Exception:
                pass
        elif step != "advanced":
            try:
                input_widget = self.query_one(f"#input_{step}", Input)
                input_widget.focus()
            except Exception:
                pass
    
    async def on_key(self, event: events.Key) -> None:
        """Handle key events for navigation."""
        if self._generating:
            event.prevent_default()
            return
            
        step = self.STEPS[self.current_step]
        
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            return
        
        if step == "advanced":
            if event.key == "space":
                # Toggle checkbox
                checkbox = self.query_one("#load_on_startup", Checkbox)
                checkbox.value = not checkbox.value
                event.prevent_default()
                return
            elif event.key == "enter":
                # Submit
                self._submit()
                event.prevent_default()
                return
            elif event.key == "backspace":
                self._prev_step()
                event.prevent_default()
                return
        elif step == "instructions":
            # Ctrl+D to continue to next step
            if event.key == "ctrl+d":
                self._next_step()
                event.prevent_default()
                return
            elif event.key == "backspace":
                # Only go back if text area is empty
                try:
                    text_area = self.query_one("#input_instructions", TextArea)
                    if text_area.text == "":
                        self._prev_step()
                        event.prevent_default()
                except Exception:
                    pass
        else:
            if event.key == "enter":
                self._next_step()
                event.prevent_default()
                return
            
            if event.key == "backspace":
                # Check if current input is empty
                try:
                    input_widget = self.query_one(f"#input_{step}", Input)
                    if input_widget.value == "":
                        self._prev_step()
                        event.prevent_default()
                except Exception:
                    pass
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "submit-btn" and not self._generating:
            self._submit()
    
    def _show_error(self, message: str) -> None:
        """Display an error message."""
        error = self.query_one("#error-message", Static)
        error.update(f"[red]{message}[/red]")
    
    def _show_status(self, message: str) -> None:
        """Display a status message."""
        error = self.query_one("#error-message", Static)
        error.update(f"[cyan]{message}[/cyan]")
    
    def _next_step(self) -> None:
        """Move to the next step."""
        step = self.STEPS[self.current_step]
        
        # Get current value
        if step == "instructions":
            try:
                text_area = self.query_one("#input_instructions", TextArea)
                value = text_area.text.strip()
            except Exception:
                value = ""
        else:
            try:
                input_widget = self.query_one(f"#input_{step}", Input)
                value = input_widget.value.strip()
            except Exception:
                value = ""
        
        # Validate
        if step == "name":
            if not value:
                self._show_error("Name is required")
                return
            is_valid, error = validate_plugin_name(value)
            if not is_valid:
                self._show_error(error)
                return
        elif step == "instructions":
            if not value:
                self._show_error("Instructions are required")
                return
        
        # Save value
        self.data[step] = value
        
        # Move to next step
        if self.current_step < len(self.STEPS) - 1:
            self.current_step += 1
            self._refresh_content()
    
    def _prev_step(self) -> None:
        """Move to the previous step."""
        if self.current_step > 0:
            # Save current value before going back
            step = self.STEPS[self.current_step]
            if step == "advanced":
                try:
                    checkbox = self.query_one("#load_on_startup", Checkbox)
                    self.data["load_on_startup"] = checkbox.value
                except Exception:
                    pass
            elif step == "instructions":
                try:
                    text_area = self.query_one("#input_instructions", TextArea)
                    self.data["instructions"] = text_area.text
                except Exception:
                    pass
            else:
                try:
                    input_widget = self.query_one(f"#input_{step}", Input)
                    self.data[step] = input_widget.value
                except Exception:
                    pass
            
            self.current_step -= 1
            self._refresh_content()
    
    def _submit(self) -> None:
        """Submit and create the plugin."""
        if self._generating:
            return
            
        # Get checkbox value
        try:
            checkbox = self.query_one("#load_on_startup", Checkbox)
            self.data["load_on_startup"] = checkbox.value
        except Exception:
            pass
        
        # Start async generation
        self._generating = True
        self._show_status("Generating description and keywords...")
        
        # Disable button
        try:
            btn = self.query_one("#submit-btn", Button)
            btn.disabled = True
            btn.label = "Generating..."
        except Exception:
            pass
        
        self._do_submit()
    
    @work(exclusive=True)
    async def _do_submit(self) -> None:
        """Async submit with metadata generation."""
        try:
            # Generate description and keywords
            description, keywords = await generate_plugin_metadata(
                self.data["name"],
                self.data["instructions"],
                self.profile
            )
            
            # Create plugin
            plugin = Plugin(
                name=self.data["name"],
                description=description,
                keywords=keywords,
                instructions=self.data["instructions"],
                load_on_startup=self.data["load_on_startup"]
            )
            
            # Save plugin
            path = save_plugin(plugin)
            self.dismiss(path)
            
        except Exception as e:
            self._generating = False
            self._show_error(f"Failed to create plugin: {e}")
            
            # Re-enable button
            try:
                btn = self.query_one("#submit-btn", Button)
                btn.disabled = False
                btn.label = "Create Plugin"
            except Exception:
                pass
    
    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)
