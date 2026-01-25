"""Service for shell command trust policy management."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from nora.models.trust_policy import Policy, TrustPolicyFile
from nora.repositories.trust_repository import TrustRepository


class TrustDecision(Enum):
    """User's trust decision for a command."""
    ALLOW_ONCE = "y"      # Allow this one time, no policy saved
    DENY = "n"            # Deny the command
    TRUST_PERMANENT = "t" # Save policy with trust_all_threads=True
    TRUST_SESSION = "s"   # Save policy with trustedThreads=[current_thread]


@dataclass
class TrustLevel:
    """A trust level option for the user to select."""
    level: int           # 1-6 or dynamic
    display: str         # e.g., "git log -n *"
    args: list[str]      # Base args for the policy
    trust_all_args: bool # Whether to trust all additional args
    extra_trusted: list[str]  # Specific trusted arguments beyond base


class TrustService:
    """
    Manages trust policy evaluation and creation.
    
    Handles checking if commands are trusted and creating new policies
    based on user decisions.
    """
    
    # Shell programs that interpret command strings
    SHELL_PROGRAMS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh"}
    
    # Blocked patterns when inside shell -c command strings
    BLOCKED_SHELL_PATTERNS = [
        "|",    # Pipe
        "&&",   # Logical AND
        "||",   # Logical OR
        ";",    # Command separator
        "`",    # Backtick command substitution
        "$(",   # Command substitution
        ">",    # Output redirection
        ">>",   # Append redirection
        "<",    # Input redirection
    ]
    
    def __init__(self, repository: Optional[TrustRepository] = None) -> None:
        """
        Initialize the service.
        
        Args:
            repository: TrustRepository instance. Creates new one if None.
        """
        self._repository = repository or TrustRepository()
    
    def _is_shell_program(self, program: str) -> bool:
        """Check if program is a shell that interprets command strings."""
        # Handle both "bash" and "/bin/bash"
        prog_name = program.split("/")[-1]
        return prog_name in self.SHELL_PROGRAMS
    
    def check_for_chaining(self, program: str, args: list[str]) -> Optional[str]:
        """
        Check if command contains blocked chaining patterns.
        
        Only blocks dangerous patterns when using a shell with -c flag,
        since that's the only case where operators like | are interpreted.
        Direct program execution (subprocess with list args) doesn't invoke
        a shell, so | etc. are just literal characters.
        
        Args:
            program: The program name.
            args: The command arguments.
            
        Returns:
            Error message if chaining detected, None otherwise.
        """
        # Only check for chaining when program is a shell
        if not self._is_shell_program(program):
            return None
        
        # Only dangerous if using -c flag (command string)
        if "-c" not in args:
            return None
        
        # Find the command string after -c
        try:
            c_index = args.index("-c")
            if c_index + 1 >= len(args):
                return None
            cmd = args[c_index + 1]
            
            # Check for shell operators in the command string
            for pattern in self.BLOCKED_SHELL_PATTERNS:
                if pattern in cmd:
                    return f"Command chaining is not allowed. Found '{pattern}' in shell command."
        except (ValueError, IndexError):
            return None
        
        return None
    
    def is_command_trusted(
        self, 
        program: str, 
        args: list[str], 
        thread_id: str
    ) -> bool:
        """
        Check if a command is trusted based on existing policies.
        
        Args:
            program: The program name.
            args: The command arguments.
            thread_id: The current thread ID.
            
        Returns:
            True if any policy allows the command.
        """
        policy_file = self._repository.load(program)
        return policy_file.find_matching_policy(args, thread_id) is not None
    
    def get_trust_levels(
        self, 
        program: str, 
        args: list[str]
    ) -> list[TrustLevel]:
        """
        Generate trust level options for a command.
        
        For command "git log -n 5", generates:
        1. git log           (base command only)
        2. git log *         (any arguments)
        3. git log -n        (first arg only)
        4. git log -n *      (first arg + any additional)
        5. git log -n 5      (exact command)
        6. git log -n 5 *    (exact + any additional)
        
        Args:
            program: The program name.
            args: The command arguments.
            
        Returns:
            List of TrustLevel options.
        """
        levels = []
        level_num = 1
        
        # Level 1: Base command only (no args)
        levels.append(TrustLevel(
            level=level_num,
            display=program,
            args=[],
            trust_all_args=False,
            extra_trusted=[]
        ))
        level_num += 1
        
        # Level 2: Base command with any args
        levels.append(TrustLevel(
            level=level_num,
            display=f"{program} *",
            args=[],
            trust_all_args=True,
            extra_trusted=[]
        ))
        level_num += 1
        
        # For each argument, add two levels: exact and wildcard
        for i, arg in enumerate(args):
            current_args = args[:i + 1]
            display_base = f"{program} {' '.join(current_args)}"
            
            # Exact level (these specific args only)
            levels.append(TrustLevel(
                level=level_num,
                display=display_base,
                args=current_args.copy(),
                trust_all_args=False,
                extra_trusted=[]
            ))
            level_num += 1
            
            # Wildcard level (these args + any additional)
            levels.append(TrustLevel(
                level=level_num,
                display=f"{display_base} *",
                args=current_args.copy(),
                trust_all_args=True,
                extra_trusted=[]
            ))
            level_num += 1
        
        return levels
    
    def create_policy_from_level(
        self, 
        level: TrustLevel, 
        decision: TrustDecision,
        thread_id: str
    ) -> Policy:
        """
        Create a Policy from a trust level and decision.
        
        Args:
            level: The selected trust level.
            decision: TRUST_PERMANENT or TRUST_SESSION.
            thread_id: The current thread ID.
            
        Returns:
            Configured Policy instance.
        """
        return Policy(
            args=level.args,
            default_trusted=True,
            trust_all_arguments=level.trust_all_args,
            trust_all_threads=(decision == TrustDecision.TRUST_PERMANENT),
            trusted_threads=[thread_id] if decision == TrustDecision.TRUST_SESSION else [],
            trusted_arguments=level.extra_trusted
        )
    
    def save_policy(
        self, 
        program: str, 
        level: TrustLevel, 
        decision: TrustDecision,
        thread_id: str
    ) -> None:
        """
        Create and save a policy based on user's trust decision.
        
        Args:
            program: The program name.
            level: The selected trust level.
            decision: TRUST_PERMANENT or TRUST_SESSION.
            thread_id: The current thread ID.
        """
        policy = self.create_policy_from_level(level, decision, thread_id)
        self._repository.add_policy(program, policy)
