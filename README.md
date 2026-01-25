# Nora

AI CLI tool built with AWS Bedrock and Strands Agents framework.

## Features

- **Interactive TUI** - Chat with file autocomplete (`@`), commands (`/`), diff viewer
- **Three Modes**: `vibe` (full access), `plan` (read-only), `act` (execute plans)
- **Subagents** - Parallel research agents with read-only access
- **Plugin System** - Keyword-based activation of custom instructions
- **Thread Persistence** - Save and resume conversations

## Architecture

Service Layer Pattern: `Presentation → Services → Repositories → File System`

| Layer | Purpose |
|-------|---------|
| `config/` | Constants, prompts |
| `models/` | Pydantic data models |
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

```bash
nora chat                    # Interactive chat
nora chat "prompt"           # Start with prompt
nora chat --headless "msg"   # One-shot mode
nora chat -p aws-profile     # Use AWS profile
```

### Commands

`/new` `/switch` `/model` `/add-plugin` `/exit`

### Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit |
| `Shift+Enter` | Newline |
| `Ctrl+C` | Cancel/Exit |
| `Shift+Tab` | Cycle mode |
| `Ctrl+E` | Execute plan |
| `Ctrl+O` | Toggle subagent |

### Tools

`Read` `Write` `Edit` `Explore` `Search` `Subagent` `Fetch`

## Configuration

```bash
nora config set --defaultProfile my-profile
nora config get
```

### Storage

- Settings: `~/.nora/settings.json`
- Threads: `$CWD/.nora/threads/`
- Plugins: `$CWD/.nora/plugins/`
- Plans: `$CWD/.nora/plans/`

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
from nora.services import AgentService, ThreadService, PluginService

agent = AgentService().create_agent(messages, profile, mode, model_id)

thread_service = ThreadService()
thread = thread_service.create()
thread_service.save(thread)

matched = PluginService().match_plugins("user input")
```

## Requirements

- Python 3.12+
- AWS credentials with Bedrock access
- Access to Claude models

## License

MIT
