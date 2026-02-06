# Nora - Agent Context

## Overview

CLI tool using Strands Agents SDK with AWS Bedrock (Claude Opus 4.5).
Implements the **Agent Communication Protocol (ACP) v0.2.0** for agent interoperability.

## Tech Stack

- **Framework**: Strands Agents
- **Model**: Claude Opus 4.5 via AWS Bedrock
- **Protocol**: ACP v0.2.0 (Agent Communication Protocol)
- **CLI**: Typer | **TUI**: Textual | **HTTP**: FastAPI + Uvicorn | **Package**: uv

## Architecture

Service Layer Pattern: `Presentation → Services → Repositories → File System`

ACP Layer: `HTTP (FastAPI) → ACP Runner → Strands Agent → Tools`

## Structure

```
src/nora/
├── acp/           # ACP protocol implementation
│   ├── models/    # ACP data models (Message, Run, Session, AgentManifest)
│   ├── server.py  # FastAPI ACP server (nora acp)
│   ├── runner.py  # Bridges ACP Runs → Strands Agent execution
│   ├── convert.py # ACP ↔ Strands message conversion
│   └── migrate.py # Legacy thread → ACP session migration
├── cli/           # CLI commands (chat, acp, manifest, migrate)
├── config/        # Constants, prompts
├── models/        # Pydantic data models (legacy + ACP re-exports)
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

## ACP Protocol

Nora implements ACP v0.2.0 (https://agentcommunicationprotocol.dev).

### CLI Commands

```bash
nora chat              # TUI chat (default)
nora acp               # Start ACP HTTP server
nora acp --port 9000   # Custom port
nora manifest          # Print agent manifest as JSON
nora migrate           # Migrate legacy threads to ACP sessions
```

### ACP Server Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ping` | Health check → `{}` |
| `GET` | `/agents` | List agents → `{agents: [manifest]}` |
| `GET` | `/agents/nora` | Get Nora's manifest |
| `POST` | `/runs` | Create run (sync/async/stream) |
| `GET` | `/runs/{run_id}` | Get run status |
| `GET` | `/runs/{run_id}/events` | List run events |
| `POST` | `/runs/{run_id}/cancel` | Cancel a run |
| `GET` | `/sessions/{session_id}` | Get session |

### ACP Data Models

```python
from nora.acp.models import (
    AcpMessage,        # ACP message with parts
    MessagePart,       # Content part with MIME type
    TrajectoryMetadata, # Tool call metadata
    CitationMetadata,  # Citation metadata
    Run, RunStatus,    # Run lifecycle
    Session,           # Conversation context (replaces Thread)
    AgentManifest,     # Agent discovery
    AcpError,          # Error model
)
```

### ACP Storage Format

```
$CWD/.nora/sessions/<uuid>/
├── session.json              # Session metadata
└── runs/
    ├── <uuid>.json           # ACP Run (input + output messages)
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

## Services

```python
from nora.services import (
    SettingsService,    # Singleton - settings
    ThreadService,      # Thread CRUD (legacy)
    SessionService,     # ACP Session CRUD (new)
    RunService,         # ACP Run lifecycle (new)
    PluginService,      # Plugin matching
    PlanService,        # Plan operations
    AgentService,       # Agent creation
    CancellationHook,   # Cancellation
)
```

## Modes

| Mode | Tools | Description |
|------|-------|-------------|
| vibe | All | Full access |
| plan | Read-only + Subagent | Planning with research |
| act | All | Execute plans |
| subagent | Read-only | Research (no nested subagents) |

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
- Sessions (ACP): `$CWD/.nora/sessions/` (new)
- Threads (legacy): `$CWD/.nora/threads/`
- Plugins: `$CWD/.nora/plugins/`
- Plans: `$CWD/.nora/plans/`

## Imports

```python
# ACP models (new)
from nora.acp.models import AcpMessage, Run, Session, AgentManifest
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
- ACP: https://agentcommunicationprotocol.dev
- ACP OpenAPI: https://github.com/i-am-bee/acp/blob/main/docs/spec/openapi.yaml
