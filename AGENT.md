# Nora - Agent Context

## Overview

CLI tool using Strands Agents SDK with AWS Bedrock (Claude Opus 4.5).

## Tech Stack

- **Framework**: Strands Agents
- **Model**: Claude Opus 4.5 via AWS Bedrock
- **CLI**: Typer | **TUI**: Textual | **Package**: uv

## Architecture

Service Layer Pattern: `Presentation → Services → Repositories → File System`

## Structure

```
src/nora/
├── cli/           # CLI commands
├── config/        # Constants, prompts
├── models/        # Pydantic data models
├── repositories/  # Data persistence
├── services/      # Business logic
├── screens/       # TUI modals (re-exports)
├── widgets/       # TUI widgets (re-exports)
├── tui/           # TUI app + widgets
├── tools/         # Agent tools
├── utils/         # Utilities
├── core/          # Backward compat
└── storage/       # Backward compat
```

## Services

```python
from nora.services import (
    SettingsService,    # Singleton - settings
    ThreadService,      # Thread CRUD
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
| plan | Read-only | Planning |
| act | All | Execute plans |
| subagent | Read-only | Research |

## Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `Read` | `path`, `start_line?`, `end_line?` | Read file contents (optionally specific line range) |
| `Write` | `path`, `content`, `reason` | Write file (shows diff) |
| `Edit` | `path`, `old_text`, `new_text`, `reason` | Find & replace (shows diff) |
| `Explore` | `path` | List directory contents |
| `Search` | `pattern`, `path` | Grep for text |
| `Subagent` | `prompt` | Spawn read-only research agent |
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

### Write/Edit Reason Parameter

The `reason` parameter is required for `Write` and `Edit` tools. It provides a one-line summary of the change purpose, displayed in the diff modal header:

```
[bold]path/to/file.py[/bold] · Reason for the change
```

The diff modal shows: **filepath** `·` reason (middle dot separator).

## Storage

- Settings: `~/.nora/`
- Threads: `$CWD/.nora/threads/`
- Plugins: `$CWD/.nora/plugins/`
- Plans: `$CWD/.nora/plans/`

## Imports

```python
# New flat structure
from nora.services import AgentService, ThreadService
from nora.models import Thread, Message, Plugin
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
