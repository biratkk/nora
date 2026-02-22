# Nora - Agent Context

## Overview

CLI tool using Strands Agents SDK with AWS Bedrock (Claude Opus 4.5).
Implements the **Agent Client Protocol (ACP)** (JSON-RPC 2.0) for IDE/editor interoperability.

## Tech Stack

- **Framework**: Strands Agents
- **Model**: Claude Opus 4.5 via AWS Bedrock
- **Protocol**: Agent Client Protocol (JSON-RPC 2.0) — https://agentclientprotocol.com
- **CLI**: Typer | **TUI**: Textual | **HTTP**: FastAPI + Uvicorn | **Package**: uv

## Architecture

Service Layer Pattern: `Presentation → Services → Repositories → File System`

ACP Layer: `stdio/HTTP (JSON-RPC 2.0) → ProtocolHandler → Strands Agent → Tools`

## Structure

```
src/nora/
├── acp/           # Agent Client Protocol implementation
│   ├── models/    # Internal persistence models (Message, Run, Session)
│   ├── server.py  # FastAPI JSON-RPC endpoint (nora acp --port)
│   ├── stdio.py   # stdio transport (nora acp)
│   ├── protocol.py # Transport-agnostic JSON-RPC dispatch
│   ├── jsonrpc.py # JSON-RPC 2.0 message models
│   ├── convert.py # Internal ↔ Strands message conversion
│   └── migrate.py # Legacy thread → session migration
├── cli/           # CLI commands (chat, acp, manifest, migrate)
├── config/        # Constants, prompts
├── models/        # Pydantic data models (legacy + internal re-exports)
├── repositories/  # Data persistence (session, run, thread, etc.)
├── services/      # Business logic (session, run, thread, etc.)
├── screens/       # TUI modals (re-exports)
├── widgets/       # TUI widgets (re-exports)
├── tui/           # TUI app + widgets
├── tools/         # Agent tools
├── utils/         # Utilities
├── core/          # Backward compat
└── storage/       # Backward compat
```

## Agent Client Protocol (JSON-RPC 2.0)

Nora implements the Agent Client Protocol from https://agentclientprotocol.com.
Transport: stdio (default) or HTTP. Protocol: JSON-RPC 2.0.

### CLI Commands

```bash
nora chat              # TUI chat (default)
nora acp               # Start ACP stdio transport (default)
nora acp --port 8000   # Start ACP HTTP transport
nora manifest          # Print agent info as JSON
nora migrate           # Migrate legacy threads to ACP sessions
```

### JSON-RPC Methods

| Method | Direction | Description |
|--------|-----------|-------------|
| `initialize` | Client → Agent | Protocol version & capability negotiation |
| `session/new` | Client → Agent | Create a new session (returns sessionId) |
| `session/load` | Client → Agent | Replay session history via notifications |
| `session/prompt` | Client → Agent | Send prompt, receive streaming updates, get stopReason |
| `session/cancel` | Client → Agent (notification) | Cancel in-progress prompt |
| `session/update` | Agent → Client (notification) | Streaming content, tool calls, plans |

### session/update Types

| sessionUpdate | Description |
|---------------|-------------|
| `agent_message_chunk` | Agent text streaming |
| `user_message_chunk` | User message replay (session/load) |
| `tool_call` | New tool call (with kind, rawInput) |
| `tool_call_update` | Tool call status/output update |

### Internal Data Models

```python
from nora.acp.models import (
    AcpMessage,        # Internal message with parts
    MessagePart,       # Content part with MIME type
    TrajectoryMetadata, # Tool call metadata
    CitationMetadata,  # Citation metadata
    Run, RunStatus,    # Run lifecycle (internal tracking)
    Session,           # Conversation context (replaces Thread)
    AcpError,          # Error model
)
```

### Storage Format

```
$CWD/.nora/sessions/<uuid>/
├── session.json              # Session metadata
└── runs/
    ├── <uuid>.json           # Run (input + output messages)
    └── <uuid>.strands.json   # Strands-native messages (agent re-init)
```

### Run Lifecycle

```
created → in-progress → completed
                      → failed
                      → cancelling → cancelled
                      → awaiting → (resumed) → in-progress
```

Each user prompt → agent response = one Run within a Session.

### Cancellation Architecture

When the user presses `Ctrl+C` during an active agent run:

1. `CancellationHook.cancel()` signals the agent to stop at the next tool boundary
2. The Textual worker is cancelled
3. `_save_partial_run()` snapshots `agent.messages` from the old (still-locked) agent and saves the run as cancelled — Python's GIL makes the list slice thread-safe
4. `_init_agent()` creates a **fresh agent instance** with its own `_invocation_lock`, rebuilt from saved session history
5. Input is re-enabled immediately

**Why replace the agent?** The Strands SDK holds an internal `threading.Lock` (`_invocation_lock`) during execution. When the worker is cancelled, the background thread may still be running (e.g., mid-Bedrock-stream), so the lock isn't released. Creating a fresh agent avoids the "Agent is already processing a request" error.

**Message repair**: Any dangling `toolUse` blocks (no matching `toolResult`) are repaired by `RunRepository._validate_tool_pairing()` when session history is reloaded. It injects synthetic error `toolResult` messages with text "Tool execution was interrupted."

**Key types**:
- `_ActiveInvocation` (dataclass in `tui/app.py`): Groups the old agent reference, run, and message offset needed for the cancel snapshot
- `CancellationHook` (in `services/agent_service.py`): Strands `HookProvider` that cancels tool execution via `BeforeToolCallEvent`

## Services

```python
from nora.services import (
    SettingsService,    # Singleton - settings
    ThreadService,      # Thread CRUD (legacy)
    SessionService,     # Session CRUD (new)
    RunService,         # Run lifecycle (new)
    PluginService,      # Plugin CRUD, matching, metadata generation
    PlanService,        # Plan operations
    AgentService,       # Agent creation
    CancellationHook,   # Cancellation
)
```

## Modes

| Mode | Tools | Description |
|------|-------|-------------|
| vibe | All (including plugin tools) | Full access |
| plan | Read-only + Subagent + Plugin tools | Planning with research |
| edit | All (including plugin tools) | Auto-approved file writes, execute plans |
| subagent | Read-only | Research (no nested subagents, no plugin tools) |

## Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `Read` | `path`, `start_line?`, `end_line?` | Read file contents (optionally specific line range) |
| `Write` | `path`, `content`, `reason` | Write file (shows diff) |
| `Edit` | `path`, `old_text`, `new_text`, `reason` | Find & replace (shows diff) |
| `Explore` | `path` | List directory contents |
| `Search` | `pattern`, `path` | Grep for text |
| `Subagent` | `prompt`, `reason` | Spawn read-only research agent |
| `Fetch` | `url` | Fetch webpage HTML |
| `Shell` | `program`, `args`, `reason` | Execute shell command |
| `ReadPlugin` | `name` | Read a plugin's full content by name |
| `WritePlugin` | `name`, `instructions`, `load_on_startup?` | Create a new plugin (auto-generates description & keywords via LLM) |
| `EditPlugin` | `name`, `instructions?`, `load_on_startup?` | Partial update of an existing plugin (regenerates metadata if instructions change) |
| `DeletePlugin` | `name` | Delete a plugin by name |
| `SearchPlugin` | `keyword` | Fuzzy-search plugin keywords, returns matches with scores |

### Shell Tool & Trust Policy

The Shell tool executes system commands with user approval. Commands require confirmation unless trusted.

**Trust Levels** - When approving a command like `git log -n 5`:
1. `git log` - Base command only
2. `git log *` - Any arguments allowed
3. `git log -n` - First arg only
4. `git log -n *` - First arg + any additional
5. `git log -n 5` - Exact command
6. `git log -n 5 *` - Exact + any additional

**Trust Scope**:
- **Session** (`s`) - Trust only in current thread
- **Permanent** (`t`) - Trust across all threads

**Storage**: `$CWD/.nora/trust/<program>.json`

```json
{
  "program": "git",
  "policies": [{
    "args": ["log", "-n"],
    "default_trusted": true,
    "trust_all_arguments": true,
    "trust_all_threads": false,
    "trusted_threads": ["20250125_190718"]
  }]
}
```

**Security**: Command chaining (`|`, `&&`, `;`, `>`, etc.) is blocked only when using shell programs (`bash -c "..."`) - direct execution passes args as literals.

**Async Execution**: All shell commands execute asynchronously to keep the TUI responsive:
- **Trusted commands** (agent thread): Use `subprocess.Popen` with streaming via `_execute_command_streaming()`. Output streams line-by-line to `ShellBlock` via `call_from_thread` using the `shell_output_callback` in `invocation_state`.
- **Approved commands** (interrupt flow): Use `async_execute_command()` with `asyncio.create_subprocess_exec()`. Runs on the event loop without blocking.
- **Cancellation**: All execution paths check `cancel_hook.cancelled` between lines and terminate the subprocess if set.

**Key functions in `tools/shell.py`**:
- `_execute_command()` — Sync, non-streaming (backward compat)
- `_execute_command_streaming()` — Sync with Popen, streams via callback (agent thread)
- `async_execute_command()` — Async with `create_subprocess_exec` (approved commands)
- `async_execute_shell_command()` — Async with `create_subprocess_shell` (passthrough `!` commands)

### Shell Passthrough (`!` prefix)

Users can run shell commands directly (bypassing the AI agent) by prefixing input with `!`:

```
! ls -la
! git status
```

**Behavior**:
- Input box turns red when `!` detected
- Executes via `asyncio.create_subprocess_shell` - supports pipes, redirects, etc.
- Output **streams line-by-line** into chat with red left border as it arrives
- UI remains responsive during execution (non-blocking)
- Cancellable with `Ctrl+C`
- **No trust policy** - all commands trusted (user-initiated)
- **Not sent to AI** - saved in thread history with `role: "shell"` but excluded from `to_agent_messages()`
- `ShellMessage` widget supports incremental updates via `update_output()`

**Message Model**:
```python
Message(role="shell", content="ls -la", output="file1.txt\nfile2.txt")
```

### Write/Edit Reason Parameter

The `reason` parameter is required for `Write` and `Edit` tools. It provides a one-line summary of the change purpose, displayed in the diff modal header:

```
[bold]path/to/file.py[/bold] · Reason for the change
```

The diff modal shows: **filepath** `·` reason (middle dot separator).

## Storage

- Settings: `~/.nora/`
- Sessions: `$CWD/.nora/sessions/` (new)
- Threads (legacy): `$CWD/.nora/threads/`
- Plugins: `$CWD/.nora/plugins/`
- Plans: `$CWD/.nora/plans/`

## Testing Process

Before considering any task complete, run the build check:

```bash
uv build
```

This verifies the project compiles without errors (syntax errors, missing imports, etc.). If `uv build` fails, fix the reported errors and re-run until it passes. Do not consider a task done until the build succeeds.

### Test Suite

```bash
uv run --with pytest pytest tests/ -v
```

| Test file | Coverage |
|-----------|----------|
| `tests/test_validate_tool_pairing.py` | Message repair logic for cancelled runs (dangling toolUse, orphaned toolResult, partial completion) |

## Imports

```python
# Internal models (new)
from nora.acp.models import AcpMessage, Run, Session
from nora.services import SessionService, RunService

# Legacy models (backward compat)
from nora.models import Thread, Message, Plugin
from nora.services import AgentService, ThreadService
from nora.widgets import ChatMessage, LoadingWidget
from nora.screens import DiffModal, SwitchModal
from nora.config import DEFAULT_MODEL_ID

# Backward compat
from nora.core import create_agent, CancellationHook
from nora.storage import save_thread, load_thread
```

## References

- Strands: https://strandsagents.com/latest/documentation/docs/
- Bedrock: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-bedrock/
- Agent Client Protocol: https://agentclientprotocol.com
- ACP GitHub: https://github.com/agentclientprotocol/agent-client-protocol
