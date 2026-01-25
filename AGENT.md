# Nora - Agent Context

## Project Overview

CLI tool using Strands Agents SDK with AWS Bedrock (Claude Opus 4.5).

## Tech Stack

- **Framework**: Strands Agents (`strands-agents`)
- **Model**: `us.anthropic.claude-opus-4-5-20251101-v1:0` via AWS Bedrock
- **CLI**: Typer
- **TUI**: Textual
- **Package Manager**: uv

## Project Structure

```
src/nora/
├── __init__.py          # Public API exports
├── cli/
│   ├── commands.py      # Main chat command handler
│   └── config.py        # Config subcommands (get, set)
├── core/
│   ├── agent.py         # Agent initialization
│   └── settings.py      # Settings management (~/.nora/settings.json)
├── models/
│   ├── thread.py        # Thread Pydantic model
│   └── message.py       # Message Pydantic model
├── storage/
│   ├── threads.py       # Thread persistence (save, load, list)
│   ├── plans.py         # Plan storage for act mode
│   └── plugins.py       # Plugin persistence and loading
├── tui/
│   ├── app.py           # Main ChatApp class
│   ├── events.py        # Input event handlers
│   ├── commands.py      # Command execution
│   └── widgets/
│       ├── chat.py      # ChatMessage, ToolCallBlock, ToolIndicator
│       ├── autocomplete.py  # AutocompleteWidget
│       └── add_plugin_modal.py # Plugin creation modal
│       ├── loading.py   # LoadingWidget
│       ├── input.py     # MarkdownInput widget
│       ├── diff_modal.py    # Inline diff viewer for file changes
│       ├── confirmation.py  # Tool confirmation modal
│       ├── modal.py         # Base modal class
│       ├── model_modal.py   # Model selector modal
│       └── threads_modal.py # Thread list modal
├── tools/
│   └── file_ops.py      # File tools (Read, Write, Edit, Explore)
└── utils/
    └── files.py         # File scanning and gitignore handling
```

## Key Implementation Details

### Model Configuration

```python
from strands.models import BedrockModel
import boto3

# With profile
model = BedrockModel(
    model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
    boto_session=boto3.Session(profile_name="profile-name")
)

# Default credentials
model = BedrockModel(model_id="us.anthropic.claude-opus-4-5-20251101-v1:0")
```

### Agent Usage

```python
from nora.core import create_agent

agent = create_agent(existing_messages, profile="optional", mode="vibe")
agent("prompt")  # Streams response to terminal
agent.messages   # Access full conversation history
```

### Modes

| Mode | Tools Available |
|------|-----------------|
| **vibe** | Read, Write, Edit, Explore |
| **plan** | Read, Explore (read-only) |
| **act** | Read, Write, Edit, Explore |

### File Tools

| Tool | Description |
|------|-------------|
| `Read` | Read file contents |
| `Write` | Create/overwrite file (shows diff, requires approval) |
| `Edit` | Replace text in file (shows diff, requires approval) |
| `Explore` | List directory contents |
| `Search` | Grep for text patterns recursively |
| `Subagent` | Spawn a sub-agent for complex research tasks (read-only) |

### Subagent System

Subagents are spawned for complex research tasks requiring multiple tool calls:

- **Read-only access**: Subagents can only use `Read`, `Search`, `Explore`, `Fetch`
- **Concise output**: Uses a specialized prompt that encourages minimal output during research
- **Parallel execution**: Multiple subagents can run concurrently, each tracked by `toolUseId`
- **Collapsible UI**: Subagent blocks start collapsed, toggle with `Ctrl+O`
- **Nested display**: Shows tool calls and output in a tree structure:
  ```
  ✓ Subagent("research files")
    ├─ Read(src/main.py)
    ├─ Search("pattern")
    └─ Result summary...
  ```

Implementation details:
- `src/nora/tools/subagent.py` - Tool implementation with `tool_use_id` routing
- `src/nora/tui/widgets/chat.py` - `SubagentBlock` widget with collapse/expand
- `src/nora/core/settings.py` - `SUBAGENT_PROMPT` for concise behavior

Write and Edit tools use interrupts to show a diff viewer before applying changes.

### Cancellation System

Uses Strands' `BeforeToolCallEvent` hook for proper cancellation:

```python
from nora.core.hooks import CancellationHook

# CancellationHook is a HookProvider that cancels tools when triggered
hook = CancellationHook()
agent = create_agent(messages, hooks=[hook])

# To cancel:
hook.cancel()  # Sets event.cancel_tool on next BeforeToolCallEvent

# To reset for next request:
hook.reset()
```

**Key files:**
- `core/hooks.py`: `CancellationHook` implementation
- `tui/app.py`: Ctrl+C handling, passes hook to agent

**Behavior:**
- Ctrl+C during processing cancels current agent turn
- Agent retains context (files read, conversation history) after cancellation
- Double Ctrl+C (when not processing) exits the app
- "Ctrl+C to cancel" hint shown below input during processing
- Input is disabled while agent is processing

### Diff Viewer

When Write/Edit is called, an inline diff modal appears:
- `Ctrl+Y`: Accept change
- `Ctrl+N`: Reject and stop agent (tool marked as failed in red)
- `Enter`: Submit improvement suggestion
- `Escape`: Cancel (agent continues)

Features:
- Line numbers on left
- Red background with `-` prefix for deletions
- Green background with `+` prefix for additions
- Context lines expand to fill screen height

### Thread Storage

```python
from nora.models import Thread, Message
from nora.storage import save_thread, load_thread, list_threads

# Create new thread
thread = Thread.create()

# Add messages
thread.messages.append(Message(role="user", content="Hello"))
thread.messages.append(Message(role="assistant", content="Hi!"))

# Save/load/list
save_thread(thread)
thread = load_thread("20260112_120000")
threads = list_threads()
```

- Location: `$CWD/.threads/thread_YYYYMMDD_HHMMSS.json`
- Format: JSON with `id`, `name`, `created`, `updated`, `messages`, `mode` fields

### Configuration Storage

### Plugin System

Plugins are project-specific rule files stored in `$CWD/.nora/plugins/` as markdown files.

**Plugin File Format:**
```markdown
---
name: PluginName
description: Brief description
keywords: word1, word2, word3
load_on_startup: yes
---
Instructions for the agent when this plugin is activated.
```

**Key Components:**
- `storage/plugins.py`: Plugin persistence (save, load, parse)
- `tui/widgets/add_plugin_modal.py`: Multi-step creation modal
- Fuzzy keyword matching via `thefuzz` library

**How Plugins Work:**
1. Plugins with `load_on_startup: yes` are loaded when chat starts
2. When user sends a message, keywords are fuzzy-matched against loaded plugins
3. Matching plugins are injected BEFORE the user's message as `<PluginDetails>` tags
4. Agent uses plugin instructions silently without announcing them

**Creating Plugins:**
- Use `/add-plugin` command
- Steps: name → instructions (Ctrl+D to continue) → advanced options (Space to toggle startup)
- Description and keywords are auto-generated by an agent

**Plugin Name Rules:**
- No spaces, `/`, or `\` characters
- Name becomes the filename

- Location: `~/.nora/settings.json`
- Pydantic model: `Settings` with `defaultProfile: str | None`
- Auto-initialized on first run

### TUI Implementation

```python
from nora.tui import run_tui
from nora.models import Thread

thread = Thread.create()
run_tui(thread, profile="optional-aws-profile")
```

- Built with Textual framework
- Commands: `/new`, `/switch`, `/model`, `/add-plugin`, `/exit`
- Keybindings: `Escape` to quit, `Ctrl+C Ctrl+C` to force quit
- Autocomplete: `/` for commands, `@` for files (respects `.gitignore`, excludes files >1MB)
- File references: stored as `[filename](path)` internally, displayed as just filename; backspace before a reference deletes the entire link
- Messages rendered with Markdown widget (syntax highlighting, links, etc.)
- Loading indicator shown while waiting for response
- Tool calls shown with status indicators (✓ success, ✗ failed/rejected)

## Strands Agents Reference

- Docs: https://strandsagents.com/latest/documentation/docs/
- Bedrock provider: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-bedrock/
