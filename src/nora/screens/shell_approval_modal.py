"""Shell command approval modal."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.binding import Binding


class ShellApprovalModal(ModalScreen[str]):
    """
    Modal for approving shell command execution.
    
    Shows the command and allows user to:
    - y: Allow once
    - n: Deny
    - t: Trust permanently (shows trust level modal)
    - s: Trust for session (shows trust level modal)
    """

    DEFAULT_CSS = """
    ShellApprovalModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    ShellApprovalModal > Container {
        width: auto;
        min-width: 50;
        max-width: 80;
        height: auto;
        border: round $primary;
        background: black;
        padding: 1 2;
    }
    
    ShellApprovalModal .title {
        text-style: bold;
        margin-bottom: 1;
        text-align: center;
    }
    
    ShellApprovalModal .command {
        background: $surface;
        padding: 1;
        margin-bottom: 1;
        text-align: center;
    }
    
    ShellApprovalModal .shell-dir {
        margin-bottom: 1;
        text-align: center;
    }
    
    ShellApprovalModal .reason {
        margin-bottom: 1;
        text-align: center;
        color: $text-muted;
    }
    
    ShellApprovalModal .options {
        margin-top: 1;
    }
    
    ShellApprovalModal .option {
        padding: 0 1;
    }
    
    ShellApprovalModal .key {
        text-style: bold;
        color: $accent;
    }
    """

    BINDINGS = [
        Binding("y", "allow_once", "Allow once", show=False),
        Binding("n", "deny", "Deny", show=False),
        Binding("t", "trust_permanent", "Trust permanently", show=False),
        Binding("s", "trust_session", "Trust for session", show=False),
        Binding("escape", "deny", "Deny", show=False),
    ]

    def __init__(self, program: str, args: list[str], reason: str, dir: Optional[str] = None) -> None:
        """
        Initialize the approval modal.
        
        Args:
            program: The program to execute.
            args: The command arguments.
            reason: The agent's explanation for running this command.
            dir: Optional working directory for the command.
        """
        super().__init__()
        self.program = program
        self.args = args
        self.reason = reason
        self.dir = dir
    
    @property
    def command_display(self) -> str:
        """Format the command for display."""
        if self.args:
            return f"{self.program} {' '.join(self.args)}"
        return self.program

    def compose(self) -> ComposeResult:
        """Compose the modal content."""
        with Container():
            yield Static("[bold]Shell Command[/bold]", classes="title")
            yield Static(f"[yellow]{self.command_display}[/yellow]", classes="command")
            if self.dir:
                yield Static(f"[dim]in [/dim][cyan]{self.dir}[/cyan]", classes="shell-dir")
            yield Static(f"[dim]{self.reason}[/dim]", classes="reason")
            
            with Vertical(classes="options"):
                yield Static("[bold cyan]y[/bold cyan] = allow once", classes="option")
                yield Static("[bold cyan]n[/bold cyan] = deny", classes="option")
                yield Static("[bold cyan]t[/bold cyan] = trust permanently", classes="option")
                yield Static("[bold cyan]s[/bold cyan] = trust for this session", classes="option")

    def action_allow_once(self) -> None:
        """Allow the command once without saving policy."""
        self.dismiss("y")

    def action_deny(self) -> None:
        """Deny the command."""
        self.dismiss("n")

    def action_trust_permanent(self) -> None:
        """Trust permanently - will show trust level modal."""
        self.dismiss("t")

    def action_trust_session(self) -> None:
        """Trust for session - will show trust level modal."""
        self.dismiss("s")
