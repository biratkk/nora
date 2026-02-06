# Nora

AI CLI tool built with AWS Bedrock and Strands Agents framework.
Implements the [Agent Communication Protocol (ACP)](https://agentcommunicationprotocol.dev) v0.2.0 for agent interoperability.

## Features

- **Interactive TUI** - Chat with file autocomplete (`@`), commands (`/`), diff viewer
- **ACP Server** - Expose Nora as a standard ACP agent via REST API
- **Three Modes**: `vibe` (full access), `plan` (read-only), `act` (execute plans)
- **Subagents** - Parallel research agents with read-only access
- **Plugin System** - Keyword-based activation of custom instructions
- **Session Persistence** - Save and resume conversations in ACP-standard format

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
| `acp/` | ACP protocol: models, server, runner, converter, migration |
| `config/` | Constants, prompts |
| `models/` | Pydantic data models (ACP + legacy) |
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

### ACP Server

Start Nora as an [ACP](https://agentcommunicationprotocol.dev)-compliant HTTP server that any ACP client can interact with:

```bash
nora acp                     # Start on 0.0.0.0:8000
nora acp --port 9000         # Custom port
nora acp --host 127.0.0.1    # Localhost only
nora acp --profile my-aws    # Use AWS profile
```

Once running, interact via standard HTTP:

```bash
# Health check
curl http://localhost:8000/ping

# Discover the agent
curl http://localhost:8000/agents

# Get Nora's manifest
curl http://localhost:8000/agents/nora

# Send a prompt (synchronous)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "nora",
    "input": [{"role": "user", "parts": [{"content": "List the files in src/"}]}],
    "mode": "sync"
  }'

# Send a prompt (streaming via SSE)
curl -N -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "nora",
    "input": [{"role": "user", "parts": [{"content": "Read README.md"}]}],
    "mode": "stream"
  }'

# Continue a conversation (session)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "nora",
    "session_id": "<uuid-from-previous-run>",
    "input": [{"role": "user", "parts": [{"content": "Now refactor that file"}]}],
    "mode": "sync"
  }'

# Cancel a running request
curl -X POST http://localhost:8000/runs/<run-id>/cancel

# Check run status
curl http://localhost:8000/runs/<run-id>
```

#### ACP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ping` | Health check |
| `GET` | `/agents` | List available agents |
| `GET` | `/agents/{name}` | Get agent manifest |
| `POST` | `/runs` | Create a run (sync, async, or stream) |
| `GET` | `/runs/{run_id}` | Get run status and output |
| `GET` | `/runs/{run_id}/events` | List run events |
| `POST` | `/runs/{run_id}/cancel` | Cancel a run |
| `GET` | `/sessions/{session_id}` | Get session details |

#### Run Modes

| Mode | Behavior |
|------|----------|
| `sync` | Blocks until the agent finishes, returns completed `Run` |
| `async` | Returns `202` immediately, poll `GET /runs/{id}` for status |
| `stream` | Returns Server-Sent Events as the agent works |

### Other Commands

```bash
nora manifest                # Print Nora's ACP agent manifest as JSON
nora migrate                 # Migrate legacy threads to ACP session format
nora config set --defaultProfile my-profile
nora config get
```

### TUI Commands

`/new` `/switch` `/model` `/add-plugin` `/exit`

### TUI Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit |
| `Shift+Enter` | Newline |
| `Ctrl+C` | Cancel/Exit |
| `Shift+Tab` | Cycle mode |
| `Ctrl+E` | Execute plan |
| `Ctrl+O` | Toggle subagent |

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
| `Shell` | `program`, `args`, `reason` | Execute shell command |

The `reason` parameter provides a one-line summary shown in the diff modal header.

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

**Scope**: Press `s` for session-only (current thread) or `t` for permanent trust.

**Storage**: Trust policies are stored in `$CWD/.nora/trust/<program>.json`

**Security**: Direct execution via `subprocess` — no shell interpretation. Chaining operators are only dangerous when running shell programs with `-c` flag.

**Async Execution**: All shell commands execute asynchronously — the UI remains responsive during execution. Trusted commands stream output line-by-line to the `ShellBlock` widget. Approved commands (via interrupt flow) use `asyncio` subprocess to avoid blocking the event loop. Commands can be cancelled with `Ctrl+C`.

## Storage

| Data | Location |
|------|----------|
| Settings | `~/.nora/settings.json` |
| Sessions (ACP) | `$CWD/.nora/sessions/<uuid>/` |
| Threads (legacy) | `$CWD/.nora/threads/` |
| Plugins | `$CWD/.nora/plugins/` |
| Plans | `$CWD/.nora/plans/` |
| Trust policies | `$CWD/.nora/trust/` |

### ACP Session Format

Each session is a directory containing a `session.json` and a `runs/` folder:

```
$CWD/.nora/sessions/<uuid>/
├── session.json              # Session metadata (name, mode, timestamps)
└── runs/
    ├── <run-uuid>.json       # ACP Run (input/output messages, status)
    └── <run-uuid>.strands.json  # Strands SDK native messages (agent re-init)
```

Run `nora migrate` to convert legacy `threads/` to the new `sessions/` format.

## Plugins

Markdown files in `$CWD/.nora/plugins/`:

```markdown
---
name: my-plugin
keywords: word1, word2
load_on_startup: yes
---
Instructions for the agent.
```

## Development

```bash
uv sync
uv run nora chat
```

### Service Layer

```python
# ACP models (new)
from nora.acp.models import AcpMessage, Run, RunStatus, Session, AgentManifest
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

- [Agent Communication Protocol](https://agentcommunicationprotocol.dev)
- [ACP OpenAPI Spec](https://github.com/i-am-bee/acp/blob/main/docs/spec/openapi.yaml)
- [Strands Agents](https://strandsagents.com/latest/documentation/docs/)
- [AWS Bedrock](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-bedrock/)

## License

MIT
