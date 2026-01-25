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

`Read` `Write` `Edit` `Explore` `Search` `Subagent` `Fetch`

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
