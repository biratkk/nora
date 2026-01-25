# Nora

A custom AI CLI tool using AWS Bedrock and the Strands Agents framework.

## Installation

```bash
uv sync
uv tool install .
```

## Usage

### Interactive TUI Mode

```bash
# Launch interactive chat (new thread)
nora chat

# Start with a message, then enter interactive mode
nora chat "your prompt here"

# One-shot mode (no TUI)
nora chat --headless "your prompt"
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Ctrl+J` | New line in input |
| `Ctrl+C` | Cancel current operation (or double-press to quit) |
| `Ctrl+O` | Toggle subagent output visibility |
| `Esc` | Close autocomplete / Exit app |
| `@` | Trigger file autocomplete |
| `/` | Trigger command autocomplete |

### TUI Commands

| Command | Description |
|---------|-------------|
| `/threads` | List all conversation threads |
| `/switch` | Switch to another thread (with keyboard navigation) |
| `/model` | Select AI model |
| `/new` | Start a new thread |
| `/add-plugin` | Create a new plugin |
| `/exit` | Exit the TUI |
| `Escape` | Exit the TUI |

### TUI Autocomplete

| Trigger | Description |
|---------|-------------|
| `/` | Autocomplete commands |
| `@` | Autocomplete file paths from current directory |

Navigation: `↑`/`↓` or `Ctrl+p`/`Ctrl+n`, `Enter` to select, `Escape` to dismiss.

File references are stored internally as markdown links `[filename](path)` but displayed as just the filename. Pressing backspace immediately before a file reference deletes the entire link at once.

### Diff Viewer

When the agent makes file changes (Write/Edit), an inline diff viewer appears:

| Key | Action |
|-----|--------|
| `Ctrl+Y` | Accept the change |
| `Ctrl+N` | Reject and stop agent |
| `Ctrl+D` / `Ctrl+U` | Scroll down/up |
| `Enter` | Submit suggestion for improvement |
| `Escape` | Cancel (agent continues) |

The diff viewer shows:
- Red highlighted lines with `-` prefix for deletions
- Green highlighted lines with `+` prefix for additions
- Line numbers on the left
- Context lines that expand to fill available screen height

### Modes

Nora has three operating modes (cycle with mode indicator):

| Mode | Description |
|------|-------------|
| **vibe** | Full access to read, write, edit, and explore tools |
| **plan** | Read-only mode for planning (no file modifications) |
| **act** | Full access, used when executing plans |

### Subagents

In **vibe** and **act** modes, Nora can spawn subagents for complex research tasks:

- Subagents have **read-only** access (Read, Search, Explore, Fetch)
- Multiple subagents can run in parallel
- Output is collapsed by default - press `Ctrl+O` to expand/collapse all
- Expanded view shows a tree of tool calls and results:
  ```
  ✓ Subagent("research the codebase")
    ├─ Read(src/main.py)
    ├─ Search("config")
    └─ Found 3 configuration files...
  ```

### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--headless` | | One-shot mode without TUI |
| `--profile` | `-p` | AWS profile name for credentials |

## Plugins

Plugins let you add custom instructions that activate based on keywords in your prompts.

### Creating a Plugin

Use `/add-plugin` to create a plugin:
1. Enter a name (no spaces, `/`, or `\`)
2. Write instructions (Ctrl+D when done)
3. Toggle "Load at startup" with Space, then Enter to create

Description and keywords are auto-generated.

### Plugin Storage

Plugins are stored in `$CWD/.nora/plugins/` as markdown files:

```markdown
---
name: my-plugin
description: Auto-generated description
keywords: keyword1, keyword2, keyword3
load_on_startup: yes
---
Your instructions here...
```

### How Plugins Work

- Plugins with `load_on_startup: yes` are loaded when you start a chat
- When you type a message, Nora fuzzy-matches your words against plugin keywords
- Matching plugins are silently injected into the conversation
- The agent uses the instructions without mentioning them

## Configuration

Settings are stored in `~/.nora/settings.json`.

```bash
# Set default AWS profile
nora config set --defaultProfile "your-profile"

# View current settings
nora config get
```

Profile precedence: `--profile` flag → `defaultProfile` setting → AWS SDK defaults

## Thread Storage

Threads are stored in `$CWD/.threads/` directory as JSON files with format `thread_YYYYMMDD_HHMMSS.json`.

## Project Structure

```
src/nora/
├── cli/           # CLI commands (chat, config)
├── core/          # Agent and settings
├── models/        # Thread and Message models
├── storage/       # Thread persistence
├── tui/           # Textual TUI app and widgets
│   └── widgets/   # UI components (diff viewer, modals, etc.)
├── tools/         # File operation tools (read, write, edit, explore)
└── utils/         # File scanning utilities
```

## Requirements

- Python 3.12+
- AWS credentials with Bedrock access to Claude models
