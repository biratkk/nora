"""Shell tool for executing system commands."""

import asyncio
import subprocess
import time
from typing import Any, Callable, Optional

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
    
    # Get session/thread ID from invocation state
    invocation_state = getattr(tool_context, "invocation_state", {}) or {}
    # Prefer session_id (ACP-native), fall back to thread_id (legacy)
    session_id = invocation_state.get("session_id", invocation_state.get("thread_id", ""))
    shell_output_callback = invocation_state.get("shell_output_callback")
    cancel_hook = invocation_state.get("cancel_hook")
    
    # Get tool_use_id from context to route streaming output to the correct ShellBlock
    tool_use_id = tool_context.tool_use.get("toolUseId")
    
    # Build an on_output callback that routes to the correct ShellBlock via tool_use_id
    on_output = None
    if shell_output_callback and tool_use_id:
        def on_output(accumulated: str) -> None:
            shell_output_callback(tool_use_id, accumulated)
    
    # Check if command is already trusted
    if not _trust_service.is_command_trusted(program, args, session_id):
        # Request user approval via interrupt
        command_display = f"{program} {' '.join(args)}" if args else program
        approval = tool_context.interrupt("shell-confirm", reason={
            "program": program,
            "args": args,
            "reason": reason,
            "command": command_display,
            "session_id": session_id,
        })
        
        if approval == "reject":
            return "Command rejected by user"
        
        # If approval is a string (command output), return it directly
        # This happens when user approves and app executes the command
        return approval
    
    # Command is already trusted - execute with streaming
    return _execute_command_streaming(program, args, on_output=on_output, cancel_hook=cancel_hook)


def _execute_command(program: str, args: list[str]) -> str:
    """
    Execute a shell command and return output (non-streaming).
    
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


def _execute_command_streaming(
    program: str,
    args: list[str],
    on_output: Optional[Callable[[str], None]] = None,
    cancel_hook: Optional[Any] = None,
) -> str:
    """
    Execute a shell command with streaming output.
    
    Streams output line-by-line to the on_output callback while the process runs.
    Falls back to non-streaming execution if no callback is provided.
    
    Args:
        program: The program to execute.
        args: The command arguments.
        on_output: Callback invoked with accumulated output as each line arrives.
        cancel_hook: CancellationHook to check for cancellation.
        
    Returns:
        The command output (stdout and stderr combined).
    """
    if on_output is None:
        return _execute_command(program, args)
    
    try:
        process = subprocess.Popen(
            [program] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=None,
        )
        
        # Track process for cancellation
        output_lines: list[str] = []
        start_time = time.monotonic()
        timeout = 300  # 5 minute timeout
        
        try:
            for line in iter(process.stdout.readline, ""):
                # Check cancellation
                if cancel_hook and getattr(cancel_hook, "cancelled", False):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return "Error: Command cancelled by user"
                
                # Check timeout
                if time.monotonic() - start_time > timeout:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return f"Error: Command timed out after {timeout} seconds"
                
                output_lines.append(line)
                on_output("".join(output_lines))
            
            process.wait()
        except Exception:
            process.kill()
            process.wait()
            raise
        
        output = "".join(output_lines)
        
        if process.returncode != 0:
            output = f"[Exit code: {process.returncode}]\n{output}"
        
        return output if output else "(no output)"
        
    except FileNotFoundError:
        return f"Error: Program not found: {program}"
    except Exception as e:
        return f"Error executing command: {str(e)}"


async def async_execute_command(
    program: str,
    args: list[str],
    on_output: Optional[Callable[[str], None]] = None,
    cancel_hook: Optional[Any] = None,
) -> str:
    """
    Execute a shell command asynchronously without blocking the event loop.
    
    Uses asyncio.create_subprocess_exec for non-blocking execution with
    line-by-line output streaming.
    
    Args:
        program: The program to execute.
        args: The command arguments.
        on_output: Callback invoked with accumulated output as each line arrives.
        cancel_hook: CancellationHook to check for cancellation.
        
    Returns:
        The command output (stdout and stderr combined).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            program, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        output_lines: list[str] = []
        start_time = time.monotonic()
        timeout = 300  # 5 minute timeout
        
        try:
            while True:
                # Check cancellation
                if cancel_hook and getattr(cancel_hook, "cancelled", False):
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                    return "Error: Command cancelled by user"
                
                # Check timeout
                if time.monotonic() - start_time > timeout:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                    return f"Error: Command timed out after {timeout} seconds"
                
                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    # No output yet, keep waiting
                    if process.returncode is not None:
                        break
                    continue
                
                if not line_bytes:
                    break
                
                line = line_bytes.decode()
                output_lines.append(line)
                if on_output:
                    on_output("".join(output_lines))
            
            await process.wait()
        except Exception:
            process.kill()
            await process.wait()
            raise
        
        output = "".join(output_lines)
        
        if process.returncode != 0:
            output = f"[Exit code: {process.returncode}]\n{output}"
        
        return output if output else "(no output)"
        
    except FileNotFoundError:
        return f"Error: Program not found: {program}"
    except Exception as e:
        return f"Error executing command: {str(e)}"


async def async_execute_shell_command(
    command: str,
    on_output: Optional[Callable[[str], None]] = None,
    cancel_hook: Optional[Any] = None,
) -> str:
    """
    Execute a shell command string asynchronously (for passthrough commands).
    
    Uses asyncio.create_subprocess_shell for shell features (pipes, redirects, etc).
    
    Args:
        command: Shell command string to execute.
        on_output: Callback invoked with accumulated output as each line arrives.
        cancel_hook: CancellationHook to check for cancellation.
        
    Returns:
        The command output (stdout and stderr combined).
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        output_lines: list[str] = []
        start_time = time.monotonic()
        timeout = 300
        
        try:
            while True:
                # Check cancellation
                if cancel_hook and getattr(cancel_hook, "cancelled", False):
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                    return "Error: Command cancelled by user"
                
                # Check timeout
                if time.monotonic() - start_time > timeout:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                    return f"Error: Command timed out after {timeout} seconds"
                
                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue
                
                if not line_bytes:
                    break
                
                line = line_bytes.decode()
                output_lines.append(line)
                if on_output:
                    on_output("".join(output_lines))
            
            await process.wait()
        except Exception:
            process.kill()
            await process.wait()
            raise
        
        output = "".join(output_lines)
        
        if process.returncode != 0:
            output = f"[Exit code: {process.returncode}]\n{output}"
        
        return output.rstrip() if output else ""
        
    except Exception as e:
        return str(e)


def execute_shell_after_approval(program: str, args: list[str]) -> str:
    """
    Execute a shell command after user approval (non-streaming).
    
    This is kept for backward compatibility but async_execute_command
    should be preferred in the TUI.
    
    Args:
        program: The program to execute.
        args: The command arguments.
        
    Returns:
        The command output.
    """
    return _execute_command(program, args)
