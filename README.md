# Nora

AI CLI tool built with AWS Bedrock and Strands Agents framework.
Implements the [Agent Client Protocol](https://agentclientprotocol.com) (JSON-RPC 2.0) for IDE/editor interoperability.

## Features

- **Interactive TUI** - Chat with file autocomplete (`@`), commands (`/`), diff viewer
- **ACP Agent** - Expose Nora via Agent Client Protocol (stdio or HTTP)
- **Three Modes**: `vibe` (full access), `plan` (read-only), `edit` (auto-approved file writes)
- **Subagents** - Parallel research agents with read-only access
- **Plugin System** - Keyword-based activation of custom instructions
- **Session Persistence** - Save and resume conversations

## Architecture

```
Presentation (TUI / ACP Server)
    ↓
Services (Session, Run, Agent, Plugin, Plan, Trust)
    ↓
Repositories (Session, Run, Thread, Plugin, Plan, Trust)
    ↓
File System ($CWD/.nora/)
```

| Layer | Purpose |
|-------|---------|
| `acp/` | Agent Client Protocol: JSON-RPC, protocol handler, transports |
| `config/` | Constants, prompts |
| `models/` | Pydantic data models (internal + legacy) |
| `repositories/` | Data persistence |
| `services/` | Business logic |
| `widgets/`, `screens/` | TUI components |
| `tools/` | Agent tools |

## Installation

```bash
uv sync
uv tool install .
```

## Usage

### Interactive Chat (TUI)

```bash
nora chat                    # Interactive chat
nora chat "prompt"           # Start with prompt
nora chat --headless "msg"   # One-shot mode
nora chat -p aws-profile     # Use AWS profile
```

### ACP Agent (Agent Client Protocol)

Start Nora as an Agent Client Protocol agent that any ACP-compatible
editor (Zed, JetBrains, etc.) can connect to:

```bash
nora acp                     # stdio transport (default — for IDE integration)
nora acp --port 8000         # HTTP transport (JSON-RPC over HTTP)
nora acp --profile my-aws    # Use AWS profile
```

#### stdio Transport (Default)

The default mode. The IDE spawns Nora as a subprocess and communicates
via newline-delimited JSON-RPC 2.0 on stdin/stdout. Logs go to stderr.

```bash
nora acp
```

#### HTTP Transport

For remote or testing scenarios. Accepts JSON-RPC 2.0 POST requests:

```bash
nora acp --port 8000
nora acp --port 8000 --host 127.0.0.1  # Localhost only
```

```bash
# Initialize
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": 1,
      "clientInfo": {"name": "curl-test"},
      "clientCapabilities": {}
    }
  }'

# Create session
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 2,
    "method": "session/new",
    "params": {"cwd": "/path/to/project"}
  }'

# Send prompt
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 3,
    "method": "session/prompt",
    "params": {
      "sessionId": "<session-id>",
      "prompt": [{"type": "text", "text": "List the files in src/"}]
    }
  }'

# Health check (convenience endpoint)
curl http://localhost:8000/ping
```

#### JSON-RPC Methods

| Method | Direction | Description |
|--------|-----------|-------------|
| `initialize` | Client → Agent | Version & capability negotiation |
| `session/new` | Client → Agent | Create new session |
| `session/load` | Client → Agent | Resume session (replays history) |
| `session/prompt` | Client → Agent | Send prompt, get streaming updates |
| `session/cancel` | Client → Agent | Cancel in-progress prompt |
| `session/update` | Agent → Client | Streaming notifications |

### Other Commands

```bash
nora manifest                # Print agent info as JSON
nora migrate                 # Migrate legacy threads to session format
nora config set --defaultProfile my-profile
nora config get
```

### TUI Commands

`/new` `/switch` `/model` `/exit`

### TUI Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit |
| `Shift+Enter` | Newline |
| `Ctrl+C` | Cancel run / Double-press to exit |
| `Shift+Tab` | Cycle mode |
| `Ctrl+E` | Execute plan |
| `Ctrl+L` | Clear input |
| `Ctrl+O` | Toggle subagent |

### Cancellation (`Ctrl+C`)

Pressing `Ctrl+C` during an active agent run **instantly** cancels execution and returns to a ready state:

- **Completed tool calls are preserved** — if the agent ran tools A and B before being interrupted during C, A and B's results remain in conversation history
- **Fresh agent instance** — the agent is replaced with a new instance to avoid stale SDK locks, with history rebuilt from saved runs
- **Dangling tool calls repaired** — any in-progress tool call without a result gets a synthetic error result injected automatically
- **Double `Ctrl+C`** exits the application when not processing

### Shell Passthrough (`!` prefix)

Run shell commands directly without AI involvement by prefixing with `!`:

```
! ls -la
! git status
! npm install
```

- Input box turns **red** when `!` is detected
- Commands execute **asynchronously** — the UI stays responsive during execution
- Output **streams line-by-line** into the chat as it arrives
- Supports pipes, redirects, and all shell features
- **No trust policy** — all commands are trusted (user-initiated)
- **Not sent to AI** — commands are saved in thread history but excluded from agent context
- **Cancellable** via `Ctrl+C`

### Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `Read` | `path`, `start_line?`, `end_line?` | Read file contents (optionally specific line range) |
| `Write` | `path`, `content`, `reason` | Write file (shows diff) |
| `Edit` | `path`, `old_text`, `new_text`, `reason` | Find & replace (shows diff) |
| `Explore` | `path` | List directory contents |
| `Search` | `pattern`, `path` | Grep for text |
| `Subagent` | `prompt`, `reason` | Spawn read-only research agent |
| `Fetch` | `url` | Fetch webpage HTML |
| `Shell` | `program`, `args`, `reason`, `dir?` | Execute shell command |
| `ReadPlugin` | `name` | Read a plugin's full content by name |
| `WritePlugin` | `name`, `instructions`, `load_on_startup?` | Create a new plugin (auto-generates metadata) |
| `EditPlugin` | `name`, `instructions?`, `load_on_startup?` | Partial update of an existing plugin |
| `DeletePlugin` | `name` | Delete a plugin by name |
| `SearchPlugin` | `keyword` | Fuzzy-search plugins by keyword |

The `reason` parameter provides a one-line summary shown in the diff modal header.

Plugin tools are available in **vibe**, **plan**, and **edit** modes (not subagent).

### Shell Trust Policy

Shell commands require user approval. When approving, you choose a trust level:

| Level | Example | Trusts |
|-------|---------|--------|
| Base only | `git log` | Exact base command |
| Base + any args | `git log *` | Base with any arguments |
| Partial | `git log -n` | First N arguments |
| Partial + any | `git log -n *` | First N args + anything |
| Exact | `git log -n 5` | Exact full command |
| Exact + any | `git log -n 5 *` | Exact + any additional |

**Working Directory (`dir`)**: An optional `dir` parameter allows executing commands in a specific directory. Accepts relative or absolute paths — relative paths are resolved from cwd. The current working directory is dynamically injected into the tool's parameter description so the model knows the cwd without needing `pwd`. The approval modal displays the target directory when set.

**Scope**: Press `s` for session-only (current thread) or `t` for permanent trust.

**Storage**: Trust policies are stored in `$CWD/.nora/trust/<program>.json`

**Security**: Direct execution via `subprocess` — no shell interpretation. Chaining operators are only dangerous when running shell programs with `-c` flag.

**Async Execution**: All shell commands execute asynchronously — the UI remains responsive during execution. Trusted commands stream output line-by-line to the `ShellBlock` widget. Approved commands (via interrupt flow) use `asyncio` subprocess to avoid blocking the event loop. Commands can be cancelled with `Ctrl+C`.

## Storage

| Data | Location |
|------|----------|
| Settings | `~/.nora/settings.json` |
| Sessions | `$CWD/.nora/sessions/<uuid>/` |
| Threads (legacy) | `$CWD/.nora/threads/` |
| Plugins | `$CWD/.nora/plugins/` |
| Plans | `$CWD/.nora/plans/` |
| Trust policies | `$CWD/.nora/trust/` |

### Session Storage Format

Each session is a directory containing a `session.json` and a `runs/` folder:

```
$CWD/.nora/sessions/<uuid>/
├── session.json              # Session metadata (name, timestamps)
└── runs/
    ├── <run-uuid>.json       # Run (input/output messages, status)
    └── <run-uuid>.strands.json  # Strands SDK native messages (agent re-init)
```

Run `nora migrate` to convert legacy `threads/` to the new `sessions/` format.

## Plugins

Markdown files in `$CWD/.nora/plugins/`:

```markdown
---
name: my-plugin
description: Brief description (auto-generated)
keywords: word1, word2 (auto-generated)
load_on_startup: yes
---
Instructions for the agent.
```

Plugins are managed through agent tools — ask the agent to create, edit, or delete plugins:

- **WritePlugin** creates a new plugin with auto-generated description and keywords
- **EditPlugin** partially updates an existing plugin (regenerates metadata if instructions change)
- **DeletePlugin** removes a plugin
- **ReadPlugin** reads a plugin's full content
- **SearchPlugin** fuzzy-searches across plugin keywords

Plugins with `load_on_startup: yes` are automatically loaded. All plugins are fuzzy-matched against user messages — when a match is found, a **🔌 Plugin Activated** indicator appears in the chat and the plugin's instructions are injected into the agent's context.

## Development

```bash
uv sync
uv run nora chat
```

### Service Layer

```python
# Internal models
from nora.acp.models import AcpMessage, Run, RunStatus, Session
from nora.services import SessionService, RunService

# Legacy models (backward compat)
from nora.services import AgentService, ThreadService, PluginService

session_service = SessionService()
session = session_service.create()
session_service.save(session)

run_service = RunService()
run = run_service.create("nora", [AcpMessage.user("hello")], session.id)
```

## Requirements

- Python 3.12+
- AWS credentials with Bedrock access
- Access to Claude models

## References

- [Agent Client Protocol](https://agentclientprotocol.com)
- [ACP GitHub](https://github.com/agentclientprotocol/agent-client-protocol)
- [Strands Agents](https://strandsagents.com/latest/documentation/docs/)
- [AWS Bedrock](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-bedrock/)

## License

MIT
