"""Shell tool for executing system commands."""

import subprocess
from typing import Any

from strands import tool
from strands.types.tools import ToolContext

from nora.services.trust_service import TrustService


# Global trust service instance
_trust_service = TrustService()


@tool(name="Shell", context=True)
def run_shell(
    tool_context: ToolContext,
    program: str, 
    args: list[str], 
    reason: str,
) -> str:
    """Execute a shell command.

    Args:
        program: The program/command to execute (e.g., "git", "ls", "npm").
        args: List of arguments to pass to the program.
        reason: A brief explanation of why this command is being run and what it will accomplish.
        
    Returns:
        The command output (stdout and stderr combined).
        
    Note:
        - Command chaining (|, &&, ||, ;) is NOT allowed
        - Redirections (>, >>, <) are NOT allowed
        - Command substitution ($(), backticks) is NOT allowed
        - Each command must be executed separately
    """
    # Check for chaining patterns
    chaining_error = _trust_service.check_for_chaining(program, args)
    if chaining_error:
        return f"Error: {chaining_error}"
    
    # Get thread ID from invocation state
    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    thread_id = invocation_state.get("thread_id", "")
    
    # Check if command is already trusted
    if not _trust_service.is_command_trusted(program, args, thread_id):
        # Request user approval via interrupt
        command_display = f"{program} {' '.join(args)}" if args else program
        approval = tool_context.interrupt("shell-confirm", reason={
            "program": program,
            "args": args,
            "reason": reason,
            "command": command_display,
            "thread_id": thread_id,
        })
        
        if approval == "reject":
            return "Command rejected by user"
        
        # If approval is a string (command output), return it directly
        # This happens when user approves and app executes the command
        return approval
    
    # Command is already trusted - execute directly
    return _execute_command(program, args)


def _execute_command(program: str, args: list[str]) -> str:
    """
    Execute a shell command and return output.
    
    Args:
        program: The program to execute.
        args: The command arguments.
        
    Returns:
        The command output (stdout and stderr combined).
    """
    try:
        result = subprocess.run(
            [program] + args,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=None  # Use current working directory
        )
        
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr
        
        if result.returncode != 0:
            output = f"[Exit code: {result.returncode}]\n{output}"
        
        return output if output else "(no output)"
        
    except FileNotFoundError:
        return f"Error: Program not found: {program}"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after 300 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def execute_shell_after_approval(program: str, args: list[str]) -> str:
    """
    Execute a shell command after user approval.
    
    This is called by the app after the user approves a command.
    
    Args:
        program: The program to execute.
        args: The command arguments.
        
    Returns:
        The command output.
    """
    return _execute_command(program, args)
