# 🚀 Nora Performance Optimization Report

## Executive Summary

After a deep-dive analysis of every source file in the project, I identified **32 distinct optimization opportunities** spanning the tool layer, TUI, service/repository layers, and ACP protocol. The issues range from **O(n²) algorithmic problems** and **redundant full-directory-tree walks on every tool call** to missing caches and excessive DOM mutations.

The single biggest win — caching gitignore patterns — would eliminate a full recursive directory walk on **every Read/Write/Edit tool invocation**, likely saving 100ms–10s+ per tool call depending on repo size.

---

## Optimizations: Highest → Lowest ROI

### 🔴 TIER 1 — Critical (High impact, low-to-medium effort)

---

#### 1. Cache `load_gitignore()` — called on every file tool invocation
**Files:** `src/nora/utils/files.py`, `src/nora/tools/file_ops.py`
**Impact:** 🔥🔥🔥🔥🔥 | **Effort:** Low

Every call to `Read`, `Write`, `Edit`, or `is_path_valid()` calls `_validate_path()` → `load_gitignore()` → **`os.walk()` over the entire project directory tree**, reading every `.gitignore` file and compiling pathspec patterns. In a monorepo with `node_modules`, this can take **seconds per tool call**.

```python
# Current: full tree walk on EVERY tool call
def _validate_path(path: str) -> Path:
    spec = load_gitignore(cwd)  # os.walk entire tree!
```

**Fix:** Add a module-level cache with explicit invalidation on file writes:

```python
_gitignore_cache: dict[str, Optional[pathspec.PathSpec]] = {}

def clear_gitignore_cache() -> None:
    _gitignore_cache.clear()

def load_gitignore(cwd: Path) -> Optional[pathspec.PathSpec]:
    key = str(cwd)
    if key in _gitignore_cache:
        return _gitignore_cache[key]
    # ... existing walk logic ...
    _gitignore_cache[key] = spec
    return spec
```

Then call `clear_gitignore_cache()` after every successful `write_file` and `edit_file` (both the client and local write paths). This ensures the next read gets fresh patterns if a `.gitignore` was modified or new files/directories were created.

**Expected gain:** Eliminates ~100ms–10s of I/O per tool call after the first invocation. With a typical agent run invoking 5–20 file tools, this saves **0.5s–200s per conversation turn**.

---

#### 2. Fix O(n²) string concatenation in shell output streaming
**File:** `src/nora/tools/shell.py` (3 locations)
**Impact:** 🔥🔥🔥🔥 | **Effort:** Low

All three streaming functions (`_execute_command_streaming`, `async_execute_command`, `async_execute_shell_command`) rebuild the **entire accumulated output** on every line:

```python
output_lines.append(line)
on_output("".join(output_lines))  # O(n) per line → O(n²) total
```

For a command producing 10,000 lines, this does ~50 million character copies.

**Fix:** Change the callback contract to accept deltas and have the widget append, or at minimum track a running string instead of re-joining from the list every time:

```python
accumulated = ""
for line in ...:
    accumulated += line
    on_output(accumulated)
```

This is still O(n²) in theory but avoids the list→join overhead. The ideal fix is to change `on_output` to accept a delta (the new line only) and have `ShellBlock` append rather than replace.

---

#### 3. Cache plugin loading — reads all plugin files from disk on every user message
**Files:** `src/nora/services/plugin_service.py`, `src/nora/repositories/plugin_repository.py`
**Impact:** 🔥🔥🔥🔥 | **Effort:** Low

Every user message triggers `match_plugins()` → `load_all()` → reads + YAML-parses **every plugin file** from disk. Then runs `fuzz.partial_ratio()` for every keyword of every plugin. With 20 plugins × 30 keywords = 600 fuzzy comparisons per message, all preceded by N file reads and YAML parses.

```python
# Current: N file reads + N YAML parses + N*K fuzzy comparisons PER message
def match_plugins(self, text, threshold):
    plugins = self._repository.load_all()  # Reads all files every time!
```

**Fix:** Cache with directory mtime invalidation:

```python
class PluginService:
    _cache: list[Plugin] | None = None
    _cache_mtime: float = 0

    def _get_plugins(self) -> list[Plugin]:
        mtime = self._repository.plugins_dir.stat().st_mtime
        if self._cache is None or mtime != self._cache_mtime:
            self._cache = self._repository.load_all()
            self._cache_mtime = mtime
        return self._cache
```

Invalidate on `save()` and `delete()` by setting `self._cache = None`.

---

#### 4. Cache trust policies — disk read on every shell command
**File:** `src/nora/services/trust_service.py`
**Impact:** 🔥🔥🔥🔥 | **Effort:** Low

`is_command_trusted()` reads and JSON-parses a policy file for **every shell command**. During build/test flows, the agent may invoke `git`, `npm`, `python` dozens of times — each one hits disk.

```python
# Current: file read + JSON parse on every shell invocation
def is_command_trusted(self, program, args, session_id):
    policy_file = self._repository.load(program)  # Reads from disk!
```

**Fix:** In-memory cache invalidated on `save_policy()`:

```python
class TrustService:
    _policy_cache: dict[str, TrustPolicyFile] = {}

    def is_command_trusted(self, program, args, thread_id):
        if program not in self._policy_cache:
            self._policy_cache[program] = self._repository.load(program)
        return self._policy_cache[program].find_matching_policy(args, thread_id) is not None

    def save_policy(self, ...):
        self._policy_cache.pop(program, None)  # Invalidate
        ...
```

---

#### 5. `scan_files()` does 2 full directory traversals
**File:** `src/nora/utils/files.py`
**Impact:** 🔥🔥🔥 | **Effort:** Low (if fix #1 is applied first)

`scan_files()` calls `load_gitignore()` (full `os.walk`) then does `cwd.rglob("*")` (another full traversal). Two complete directory tree walks for one file scan.

With fix #1 applied (gitignore caching), the second call to `scan_files()` in the same session only does 1 traversal (`rglob`) since `load_gitignore()` returns from cache. But the first call still does 2.

**Fix:** Integrate gitignore pattern collection into a single walk, or accept the 1-traversal cost after caching is in place. A more aggressive fix would combine `os.walk` and file collection into one pass.

---

#### 6. Session switch modal loads ALL session histories from disk per keystroke
**File:** `src/nora/tui/widgets/switch_modal.py`
**Impact:** 🔥🔥🔥🔥 | **Effort:** Low

`_get_session_search_text()` calls `self._session_service.get_history(session)` for **every session** during fuzzy filtering. Fuzzy filtering runs on **every keystroke** via `on_input_changed`. With 50 sessions, each with 100+ messages on disk, this reads the entire conversation history of every session for each character typed.

```python
# Current: called for EVERY session on EVERY keystroke
def _get_session_search_text(self, session: Session) -> str:
    history = self._session_service.get_history(session)  # Reads all runs from disk!
    for msg in history:
        text = msg.get_text()
        ...
```

**Fix:** Cache search text when the modal opens:

```python
def on_mount(self):
    self.query_one("#session-search", Input).focus()
    self._search_text_cache = {
        s.id: self._get_session_search_text(s) for s in self.sessions
    }

def _get_session_search_text(self, session: Session) -> str:
    if hasattr(self, '_search_text_cache') and session.id in self._search_text_cache:
        return self._search_text_cache[session.id]
    # ... existing disk-reading logic as fallback ...
```

---

### 🟡 TIER 2 — Important (Medium impact, low-to-medium effort)

---

#### 7. `_render_session_history()` mounts widgets one-by-one
**File:** `src/nora/tui/app.py`
**Impact:** 🔥🔥🔥 | **Effort:** Low

Each `chat.mount(ChatMessage(...))` triggers a DOM mutation + layout reflow. For sessions with 50+ messages, this creates cascading reflows at startup and session switch.

**Fix:** Collect all widgets into a list and batch mount:

```python
def _render_session_history(self, chat: VerticalScroll) -> None:
    widgets = []
    for run in runs:
        for msg in run.input:
            widgets.append(self._create_widget_for(msg))
        for msg in run.output:
            widgets.append(self._create_widget_for(msg))
    chat.mount_all(widgets)  # Single reflow
```

---

#### 8. `_init_agent()` called on every mode cycle, model change, and session switch
**File:** `src/nora/tui/app.py`
**Impact:** 🔥🔥🔥 | **Effort:** Medium

Every call loads full session history from disk (`load_all_strands_messages` — reads N run JSON files + N strands JSON files) and creates a new `BedrockModel` + `Agent`. This is triggered by a **single keypress** (`Shift+Tab` to cycle mode).

Call sites: `on_mount`, `action_cycle_mode`, `_on_model_selected`, `_on_session_selected`, `_start_new_session`, `action_execute_plan`, `action_ctrl_c`.

**Fix:** Cache strands history and only reload when runs have changed (e.g., after a new run completes):

```python
def _init_agent(self) -> None:
    if self._cached_session_id != self.session.id or self._history_stale:
        self._cached_history = self._session_service.get_strands_history(self.session)
        self._cached_session_id = self.session.id
        self._history_stale = False
    self.agent = self._agent_service.create_agent(self._cached_history, ...)
```

---

#### 9. `RunRepository.load_all_strands_messages()` — N+1 file reads
**File:** `src/nora/repositories/run_repository.py`
**Impact:** 🔥🔥🔥 | **Effort:** Medium

Calls `list_for_session()` (glob + read + deserialize N `.json` files), then for each run calls `load_strands_messages()` (read another `.strands.json` file). That's **2N + 1** file operations per history load.

The full `Run` model is deserialized just to get the `run_id` and `created_at` ordering — the ACP message content is thrown away.

**Fix:** Read strands files directly using glob, sorted by filename (which contains the UUID), without loading full Run models:

```python
def load_all_strands_messages(self, session_id: UUID) -> list[dict]:
    runs_dir = self._get_runs_dir(session_id)
    if not runs_dir.exists():
        return []
    all_messages = []
    for path in sorted(runs_dir.glob("*.strands.json")):
        messages = json.loads(path.read_text())
        all_messages.extend(messages)
    return self._validate_tool_pairing(all_messages)
```

Note: This requires strands files to sort chronologically by filename, which they do since UUIDs are generated in order. If not, pair with the run JSON's `created_at`.

---

#### 10. `_tool_kind()` creates 6 sets on every call
**File:** `src/nora/acp/protocol.py`
**Impact:** 🔥🔥 | **Effort:** Trivial

Called once per tool invocation during streaming. Allocates 6 new `set` objects each time.

```python
# Current: 6 new sets on every call
def _tool_kind(tool_name: str) -> str:
    read_tools = {"read_file", "explore_dir", "search_files", ...}
    edit_tools = {"write_file", "edit_file", ...}
    # ... 4 more sets
```

**Fix:** Use a module-level constant dict:

```python
_TOOL_KINDS: dict[str, str] = {
    "read_file": "read", "explore_dir": "read", "search_files": "read",
    "read_plugin": "read", "search_plugin": "read",
    "write_file": "edit", "edit_file": "edit",
    "write_plugin": "edit", "edit_plugin": "edit",
    "delete_plugin": "delete",
    "run_shell": "execute",
    "fetch_url": "fetch",
    "run_subagent": "think",
}

def _tool_kind(tool_name: str) -> str:
    return _TOOL_KINDS.get(tool_name, "other")
```

---

#### 11. Handler dict rebuilt on every JSON-RPC request
**File:** `src/nora/acp/protocol.py`
**Impact:** 🔥🔥 | **Effort:** Trivial

```python
# Current: new dict on every request
async def handle_request(self, request_id, method, params):
    handlers: dict[str, Callable] = {
        "initialize": self._handle_initialize,
        "session/new": self._handle_session_new,
        ...
    }
```

**Fix:** Move to `__init__`:

```python
def __init__(self, ...):
    ...
    self._handlers = {
        "initialize": self._handle_initialize,
        "session/new": self._handle_session_new,
        ...
    }
```

---

#### 12. `AutocompleteWidget.cache_files()` — synchronous rglob on mount
**File:** `src/nora/tui/widgets/autocomplete.py`
**Impact:** 🔥🔥🔥 | **Effort:** Low

`scan_files()` does a synchronous recursive glob of the entire project directory on `on_mount()`, blocking the Textual event loop.

```python
# Current: blocks event loop
def cache_files(self) -> None:
    self._file_cache = scan_files(Path.cwd())
```

**Fix:** Run in a worker thread:

```python
async def cache_files(self) -> None:
    self._file_cache = await asyncio.to_thread(scan_files, Path.cwd())
```

Or use Textual's `run_worker`.

---

#### 13. Autocomplete `_render_items()` — full DOM rebuild on arrow key
**File:** `src/nora/tui/widgets/autocomplete.py`
**Impact:** 🔥🔥 | **Effort:** Medium

Every arrow key press in the autocomplete calls `_render_items()`, which does `container.remove_children()` followed by N `mount()` calls — a full DOM teardown and rebuild just to move a highlight.

```python
# Current: full rebuild per keypress
def move_selection(self, delta: int) -> None:
    self.selected_index = (self.selected_index + delta) % len(self.items)
    self._render_items()  # remove_children() + N mount() calls
```

**Fix:** Keep existing children, toggle CSS classes:

```python
def move_selection(self, delta: int) -> None:
    items = list(self.query(".item"))
    if items:
        items[self.selected_index].remove_class("selected")
    self.selected_index = (self.selected_index + delta) % len(self.items)
    if items:
        items[self.selected_index].add_class("selected")
```

---

#### 14. `ShellBlock.set_output()` — teardown-rebuild on every output chunk
**File:** `src/nora/tui/widgets/chat.py`
**Impact:** 🔥🔥🔥 | **Effort:** Medium

Every streaming output chunk removes all line widgets and re-creates them:

```python
# Current: full teardown + rebuild per chunk
def set_output(self, output: str) -> None:
    for widget in self._output_lines:
        widget.remove()
    self._output_lines.clear()
    ...
    for i, line in enumerate(display_lines):
        widget = Static(...)
        nested.mount(widget)
```

Combined with fix #2 (the O(n²) string join), this compounds: each chunk triggers both a full string rebuild AND a full widget rebuild.

**Fix:** Append-only strategy — only mount new lines, update the last existing line's prefix from `└─` to `├─`.

---

#### 15. Cache `SettingsService.get_mode_prompt()` — reads file from disk on every agent creation
**File:** `src/nora/services/settings_service.py`
**Impact:** 🔥🔥 | **Effort:** Trivial

Mode prompts are static markdown files that never change during a session, yet `get_mode_prompt()` reads from disk every time. This is called on every `_init_agent()`, which happens on mode cycle, model change, session switch, etc.

**Fix:**

```python
class SettingsService:
    def __init__(self, ...):
        self._prompt_cache: dict[str, Optional[str]] = {}

    def get_mode_prompt(self, mode: str) -> Optional[str]:
        if mode not in self._prompt_cache:
            self._prompt_cache[mode] = self._repository.load_mode_prompt(mode)
        return self._prompt_cache[mode]
```

---

#### 16. `_get_tools_for_mode()` rebuilds 4 tool lists on every agent creation
**File:** `src/nora/services/agent_service.py`
**Impact:** 🔥🔥 | **Effort:** Trivial

Creates 4 new lists (`plugin_tools`, `readonly_tools`, `plan_tools`, `full_tools`) every time `create_agent()` is called. The tool references are static — they never change.

```python
# Current: 4 new lists on every create_agent() call
def _get_tools_for_mode(self, mode: str) -> List:
    from nora.tools import (...)
    plugin_tools = [read_plugin, write_plugin, ...]
    readonly_tools = [read_file, explore_dir, ...]
    plan_tools = readonly_tools + [run_subagent] + plugin_tools
    full_tools = [read_file, write_file, ...] + plugin_tools
    ...
```

**Fix:** Cache as instance attributes on first call, or use `@functools.lru_cache`:

```python
def _get_tools_for_mode(self, mode: str) -> List:
    if not hasattr(self, '_tool_sets'):
        from nora.tools import (...)
        self._tool_sets = {
            "subagent": [read_file, explore_dir, search_files, fetch_url],
            "plan": [...],
            "vibe": [...],
        }
        self._tool_sets["edit"] = self._tool_sets["vibe"]
    return self._tool_sets.get(mode, self._tool_sets["vibe"])
```

---

#### 17. Every `ChatMessage` uses a full `Markdown` widget
**File:** `src/nora/tui/widgets/chat.py`
**Impact:** 🔥🔥 | **Effort:** Medium

Textual's `Markdown` widget parses a full markdown AST and creates a deep widget subtree (`MarkdownBlock`, `MarkdownHeader`, `MarkdownParagraph`, etc.) for every message. For short plain-text messages like "Done" or "Hello", this is 10–50x more expensive than a `Static` widget. A long session with 100+ messages creates 100+ Markdown widget trees.

```python
# Current: full Markdown AST for every message
def compose(self) -> ComposeResult:
    yield Markdown(self.content, classes="message-content")
```

**Fix:** Detect whether content contains markdown syntax. If not, use `Static`:

```python
def compose(self) -> ComposeResult:
    if self._has_markdown(self.content):
        yield Markdown(self.content, classes="message-content")
    else:
        yield Static(self.content, classes="message-content")
```

---

#### 18. Add response size limit on HTTP fetch
**File:** `src/nora/tools/fetch.py`
**Impact:** 🔥🔥 (safety) | **Effort:** Trivial

No size limit — `response.read()` loads the entire HTTP response into memory. A malicious or very large URL could cause OOM.

```python
# Current: unbounded read
return response.read().decode("utf-8", errors="replace")
```

**Fix:**

```python
MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB
content = response.read(MAX_RESPONSE_SIZE)
if len(content) == MAX_RESPONSE_SIZE:
    return content.decode("utf-8", errors="replace") + "\n\n... (truncated at 1MB)"
return content.decode("utf-8", errors="replace")
```

---

### 🟢 TIER 3 — Nice-to-have (Lower impact or higher effort)

---

#### 19. Pretty-printed JSON everywhere (`indent=2`)
**Files:** All repositories (`session_repository.py`, `run_repository.py`, `thread_repository.py`, etc.)
**Impact:** 🔥 | **Effort:** Trivial

`model_dump_json(indent=2)` and `json.dumps(indent=2)` adds ~30% size overhead and measurable serialization time. Strands sidecar files can be megabytes of conversation history with tool results.

**Fix:** Use compact JSON for sidecar/internal files, keep pretty-print only for human-readable files like `session.json`.

---

#### 20. `list_all()` anti-pattern — full deserialization for listing
**Files:** `src/nora/repositories/session_repository.py`, `thread_repository.py`, `plan_repository.py`
**Impact:** 🔥🔥 | **Effort:** Medium

Every repository's `list_all()` fully deserializes every file. `ThreadRepository.list_all()` loads `raw_messages` (potentially megabytes) just to display a list of thread names.

**Fix:** Store a lightweight index file, or use lazy loading that only deserializes metadata fields. For `PlanRepository.list_all()`, skip `path.read_text()` since listing only needs `id` and `description` (derivable from filename).

---

#### 21. Redundant `mkdir(exist_ok=True)` on every save
**Files:** All repositories
**Impact:** 🔥 | **Effort:** Trivial

Each `_ensure_dirs()` call re-creates directories on every `save()`. After the first call, these are wasted syscalls.

**Fix:** A class-level `_dirs_ensured: bool = False` flag, set to `True` after first call.

---

#### 22. Pydantic `model_validate_json()` runs full validation on trusted data
**Files:** All repositories
**Impact:** 🔥 | **Effort:** Low

Data written by the app itself is re-validated with full Pydantic schema validation on every load. For high-frequency loads (runs, sessions), this wastes cycles.

**Fix:** Use `model_construct()` for trusted data, or `TypeAdapter` with `strict=False`.

---

#### 23. New `ProtocolHandler` + repositories per HTTP request
**File:** `src/nora/acp/server.py`
**Impact:** 🔥🔥 | **Effort:** Medium

Each HTTP request creates fresh `ProtocolHandler`, `SessionRepository`, `RunRepository`, and `AgentService` instances. The stdio transport correctly reuses a single `ProtocolHandler`.

**Fix:** Create a shared handler at app startup and manage per-request state (e.g., notification callback) separately.

---

#### 24. `_LocalTerminal._append_output` — O(n²) byte-length check
**File:** `src/nora/acp/local_client.py`
**Impact:** 🔥🔥 | **Effort:** Trivial

Re-encodes the **entire accumulated output** to bytes just to check length, on every append:

```python
def _append_output(self, text: str) -> None:
    self.accumulated_output += text
    if self.output_byte_limit and len(self.accumulated_output.encode()) > self.output_byte_limit:
        self.truncated = True
```

**Fix:** Track byte count incrementally:

```python
def __init__(self, ...):
    ...
    self._byte_count = 0

def _append_output(self, text: str) -> None:
    if self.truncated:
        return
    self.accumulated_output += text
    self._byte_count += len(text.encode())
    if self.output_byte_limit and self._byte_count > self.output_byte_limit:
        self.truncated = True
```

---

#### 25. No output size limit on shell commands
**File:** `src/nora/tools/shell.py`
**Impact:** 🔥 (safety) | **Effort:** Low

Commands producing massive output (e.g., `find /`, `cat` of a huge file) accumulate unbounded output in `output_lines`. No truncation.

**Fix:** Add a configurable limit (e.g., 1MB) and truncate with a message.

---

#### 26. No timeout on subagent execution
**File:** `src/nora/tools/subagent.py`
**Impact:** 🔥 (safety) | **Effort:** Low

If a subagent hangs or enters an infinite tool-call loop, it blocks indefinitely. The `cancel_hook` provides manual cancellation, but there's no automatic timeout.

**Fix:** Wrap the `agent(prompt)` call with a timeout (e.g., 120 seconds).

---

#### 27. No concurrency limit on parallel subagents
**File:** `src/nora/tools/subagent.py`
**Impact:** 🔥 (safety) | **Effort:** Low

When the parent agent calls multiple subagents in parallel (via parallel tool use), there's no semaphore or limit. Each subagent creates its own Bedrock connection. 10 parallel subagents = 10 concurrent Bedrock API calls with no throttling.

**Fix:** Add `asyncio.Semaphore(3)` or a similar concurrency limit.

---

#### 28. Duplicated `_run_async()` across modules
**Files:** `src/nora/tools/file_ops.py`, `src/nora/tools/shell.py`
**Impact:** 🔥 (maintenance) | **Effort:** Trivial

Identical function in two files:

```python
def _run_async(invocation_state: dict[str, Any], coro: Any) -> Any:
    loop = invocation_state.get("event_loop")
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=...)
    return asyncio.run(coro)
```

**Fix:** Extract to `src/nora/utils/async_helpers.py`.

---

#### 29. Three nearly identical async shell execution functions
**File:** `src/nora/tools/shell.py`
**Impact:** 🔥 (maintenance) | **Effort:** Medium

`_execute_command_streaming`, `async_execute_command`, and `async_execute_shell_command` share ~90% of their logic (timeout handling, cancellation checking, output accumulation, error handling). This triplication increases maintenance burden and divergence risk.

**Fix:** Extract a parameterized base function that accepts a process factory.

---

#### 30. `action_toggle_subagent_output` — 4 separate DOM queries
**File:** `src/nora/tui/app.py`
**Impact:** 🔥 | **Effort:** Low

Four separate CSS selector queries, each scanning the full DOM, each toggling styles individually:

```python
for block in chat.query(SubagentBlock): ...
for block in chat.query(ShellBlock): ...
for block in chat.query(ToolIndicator): ...
for block in chat.query(DiffBlock): ...
```

**Fix:** Single pass with a combined query or a shared CSS class for all collapsible blocks.

---

#### 31. No debounce on file autocomplete keystrokes
**File:** `src/nora/tui/app.py`
**Impact:** 🔥 | **Effort:** Low

`get_file_matches()` scans and sorts the entire file cache on every keystroke. For large projects with thousands of files, this runs a linear scan + sort 10+ times per second while the user types.

**Fix:** Add a 50–100ms debounce timer so matching only runs after the user pauses typing.

---

#### 32. `_session_modes` dict leaks memory — no cleanup
**File:** `src/nora/acp/protocol.py`
**Impact:** 🔥 (long-running processes) | **Effort:** Trivial

Entries are added in `_handle_session_new` and `_handle_session_load` but **never removed**. For long-running stdio processes that create many sessions, this grows indefinitely.

**Fix:** Add cleanup when sessions are no longer active, or use a bounded LRU dict.

---

## Impact Summary

| # | Issue | File(s) | Impact | Effort |
|---|-------|---------|--------|--------|
| 1 | Cache `load_gitignore()` | `utils/files.py`, `tools/file_ops.py` | 🔥🔥🔥🔥🔥 | Low |
| 2 | Fix O(n²) shell streaming | `tools/shell.py` | 🔥🔥🔥🔥 | Low |
| 3 | Cache plugin loading | `services/plugin_service.py` | 🔥🔥🔥🔥 | Low |
| 4 | Cache trust policies | `services/trust_service.py` | 🔥🔥🔥🔥 | Low |
| 5 | Eliminate double dir traversal | `utils/files.py` | 🔥🔥🔥 | Low |
| 6 | Cache switch modal search text | `tui/widgets/switch_modal.py` | 🔥🔥🔥🔥 | Low |
| 7 | Batch mount session history | `tui/app.py` | 🔥🔥🔥 | Low |
| 8 | Cache strands history in `_init_agent` | `tui/app.py` | 🔥🔥🔥 | Medium |
| 9 | Fix N+1 in `load_all_strands_messages` | `repositories/run_repository.py` | 🔥🔥🔥 | Medium |
| 10 | `_tool_kind()` constant dict | `acp/protocol.py` | 🔥🔥 | Trivial |
| 11 | Handler dict in `__init__` | `acp/protocol.py` | 🔥🔥 | Trivial |
| 12 | Async `cache_files()` | `tui/widgets/autocomplete.py` | 🔥🔥🔥 | Low |
| 13 | Autocomplete CSS toggle | `tui/widgets/autocomplete.py` | 🔥🔥 | Medium |
| 14 | ShellBlock append-only output | `tui/widgets/chat.py` | 🔥🔥🔥 | Medium |
| 15 | Cache mode prompts | `services/settings_service.py` | 🔥🔥 | Trivial |
| 16 | Cache tool lists | `services/agent_service.py` | 🔥🔥 | Trivial |
| 17 | Static for plain-text messages | `tui/widgets/chat.py` | 🔥🔥 | Medium |
| 18 | Fetch response size limit | `tools/fetch.py` | 🔥🔥 | Trivial |
| 19 | Compact JSON for sidecar files | All repositories | 🔥 | Trivial |
| 20 | Lazy loading in `list_all()` | Multiple repositories | 🔥🔥 | Medium |
| 21 | Skip redundant `mkdir` | All repositories | 🔥 | Trivial |
| 22 | `model_construct()` for trusted data | All repositories | 🔥 | Low |
| 23 | Shared `ProtocolHandler` for HTTP | `acp/server.py` | 🔥🔥 | Medium |
| 24 | Incremental byte-length tracking | `acp/local_client.py` | 🔥🔥 | Trivial |
| 25 | Shell output size limit | `tools/shell.py` | 🔥 | Low |
| 26 | Subagent timeout | `tools/subagent.py` | 🔥 | Low |
| 27 | Subagent concurrency limit | `tools/subagent.py` | 🔥 | Low |
| 28 | Extract shared `_run_async` | `tools/file_ops.py`, `tools/shell.py` | 🔥 | Trivial |
| 29 | Deduplicate shell exec functions | `tools/shell.py` | 🔥 | Medium |
| 30 | Single-pass toggle query | `tui/app.py` | 🔥 | Low |
| 31 | Debounce autocomplete | `tui/app.py` | 🔥 | Low |
| 32 | Clean up `_session_modes` | `acp/protocol.py` | 🔥 | Trivial |

---

## Recommended Implementation Order

1. **Fix #1** (gitignore caching) — biggest single win, ~10 lines of code
2. **Fix #3** (plugin caching) — same pattern as #1
3. **Fix #4** (trust caching) — same pattern as #1
4. **Fix #2** (shell O(n²)) — algorithmic fix
5. **Fix #6** (switch modal caching) — UX-critical
6. **Fix #7** (batch mount) — UX-critical for session load
7. **Fixes #10, #11, #15, #16** — trivial effort, quick wins
8. **Fix #12** (async cache_files) — unblocks event loop on startup
9. **Fix #18** (fetch size limit) — safety
10. Remaining Tier 2 items in any order
11. Tier 3 items as time permits
