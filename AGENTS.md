# Omni-Stack: AGENTS.md

## Plugin System Rules & Production Architecture

### Source of Truth

In **production** there is no `omniagent` repo: only `omni-stack`. All plugins live under `/opt/workspace/omni-stack/plugins/` and must be self-contained.

### Plugin Categories: No Priority, No Fallback

A plugin's source is determined **solely by its physical location on disk**. There is no priority order between categories:

| Category | Physical Location | Identified By |
|----------|------------------|---------------|
| **Built-in** | `/app/plugins/{type}/{name}/` | `Cargo.toml` + `plugin.json` or `mcp-config.json` in omniagent workspace |
| **Bundled** | `plugins/{type}/{name}/` (omni-stack) | `plugin.json` at root |
| **Remote** | `plugins/{type}/.remote/{name}/{path}/` | `plugin.json` at subpath + entry in `remote.yml` |

The `source` field in `plugins.yml` is **authoritative**: it determines which source is active. Other sources for the same plugin name exist on disk but are marked `is_duplicated: true` and shown as disabled.

**No function should guess or fall back between sources.** When no YAML entry exists, all sources are discovered and shown as disabled: the user chooses which to enable.

### Display Rules (Dashboard Integration)

The dashboard `/tools`, `/platforms`, and `/providers` pages show **ALL discoverable plugins**, even those not in `plugins.yml`. Plugins without a YAML entry appear as `status: "disabled"`.

The omniagent plugin API (`/api/plugins`) groups by name and assigns a **primary source** via `pick_primary_source()`:

1. **YAML entry** with `source: X` → source X is primary (`is_duplicated=false`). Other same-name sources get `is_duplicated=true`.
2. **YAML entry exists** but source not on disk → fallback priority: built-in → bundled → remote.
3. **No YAML entry + 2+ sources** same name → no primary. All get `is_duplicated=true`.
4. **No YAML entry + single source** → `is_duplicated=false`.

**Key behavior:** When no YAML entry exists, `pick_primary_source` returns `None` and `is_duplicated` = `sources.len() > 1`. This prevents a default source being implicitly designated as primary. Enabling a source via the dashboard creates a YAML entry, making it the primary.

### Builtin Plugin Rules

- **Builtin tools are disabled by default** in YAML. They must have `enabled: true` and `builtin: true` to activate.
- If a tool is in YAML without `builtin: true`, the builtin source is ignored in favor of the bundled copy.
- Builtins with no YAML entry are shown as disabled. Enabling them creates a YAML entry with `builtin: true`.
- The builtin plugins live at `/app/plugins/{type}/{name}/` (inside the omniagent Docker image). They are workspace members in `/app/Cargo.toml` and have `Cargo.toml` + `src/` + `mcp-config.json`.

### Bundled Plugin Detection

Bundled plugins are discovered by scanning `plugins/{type}/{name}/plugin.json`. A directory is only considered a "local/repo plugin" if it has a `plugin.json` at the root. Library-only crates (like `util`) with no `plugin.json` or `mcp-config.json` are skipped entirely.

### Actions Plugin: Self-Contained MCP Server

The `actions` plugin (`plugins/mcp/actions/`) is a fully self-contained MCP server:

- **NO dependency on `omniagent` crate.** It is an independent binary.
- Connects directly to Postgres via `sqlx::PgPool`
- Uses `mcp-server-util` for the stdio JSON-RPC MCP protocol runtime
- Tools: `kanban_dispatcher`, `hindsight_populator`, `relevance_indexer`, `setup_knowledge_pipeline`
- **This plugin has NO builtin counterpart**: it only exists in omni-stack

**Do NOT add `omniagent` as a dependency** to actions or any other omni-stack plugin. In production, the omniagent repo does not exist: only omni-stack is deployed. Plugins must compile standalone.

### Bundled Plugins That Work Standalone

The following omni-stack plugins compile as standalone crates (no omniagent dependency):

| Plugin | Cargo.toml | Requires |
|--------|-----------|----------|
| `actions` | `plugins/mcp/actions/Cargo.toml` | `mcp-server-util`, `sqlx`, `tokio` |
| `fetch` | `plugins/mcp/fetch/Cargo.toml` | `mcp-server-util`, `reqwest` |
| `filesystem` | `plugins/mcp/filesystem/Cargo.toml` | `mcp-server-util`, `tokio` |
| `docker-compose` | `plugins/mcp/docker-compose/Cargo.toml` | `mcp-server-util` |
| `git` | `plugins/mcp/git/Cargo.toml` | `mcp-server-util`, `reqwest` |
| `skills` | `plugins/mcp/skills/Cargo.toml` | `mcp-server-util` |
| `test-rust-tool` | `plugins/mcp/test-rust-tool/Cargo.toml` | (various) |

| All of these depend on `mcp-server-util = { path = "../util" }` (the shared util crate at `plugins/mcp/util/`).

### Uninstall Must Stop the MCP Server

When uninstalling or removing a plugin (both `DELETE /api/plugins/:name?mode=uninstall` and the default remove), the handler MUST stop the running MCP server:

```rust
crate::mcp::external::client::clear_server_pools(&name);
crate::mcp::external::client::remove_server_config(&name);
state.tool_registry.write().unwrap().remove_by_server(&name);
```

Without this, the MCP server process keeps running and the tools remain registered in the `/mcp/tools` endpoint even though YAML says `enabled: false`. The plugin appears "disabled" in API responses but tools still work.

**Fix applied July 2026:** All three code paths in `delete_plugin_handler` (remote uninstall, non-remote uninstall, default remove) now stop the MCP server.

### Download Handler Must Preserve Enabled State

The `download_plugin_handler` (`POST /api/plugins/:name/download`) previously hardcoded `enabled: false` when rewriting the YAML entry after re-cloning from git. This caused every download to disable the plugin.

**Fix applied July 2026:** Now reads the current `enabled` state from the existing YAML entry before writing:

```rust
let current_enabled = plugins_yaml::get_entry(data_dir, &yaml_type, &name)
    .ok().flatten()
    .map(|e| e.enabled)
    .unwrap_or(true);
```

### Test Verification Requirements

The integration test at `omni-stack/scripts/tests.py` MUST verify that plugin lifecycle operations actually took effect, not just that the API returned `success: true`:

| Operation | Verification |
|-----------|-------------|
| `install_plugin` | Check API response fields (status=enabled, source=remote, needs_build=false, binary exists) AND verify MCP tool registered via `call_tool(name, "echo")` |
| `download_plugin` | Check API success AND remote.yml preserved |
| `uninstall_plugin` | Check API success AND `get_plugin` returns status=disabled (for remote) AND `target/` directory removed AND MCP tool NOT registered via `call_tool(name, "echo", expect_success=False)` AND `.remote/` source directory preserved |
| `enable_plugin` | Check API success AND `plugins.yml` has `enabled: true` |
| `remove_plugin` | Check API success AND `.remote/` directory preserved |

**Run from inside the omniagent container:**

```bash
docker cp scripts/tests.py omni-omniagent-1:/tmp/tests.py
docker exec omni-omniagent-1 python3 /tmp/tests.py
```

Running from the host (Hermes container) will produce false failures because `/opt/omni/` filesystem checks target the local Hermes data, not the omniagent container's data.

### G13/G14 Debugging: Noop Provider & Test Substring Pitfalls

The G13 (non-blocking tasks) and G14 (cancel task) tests use the `test-tool-caller` model in the noop provider to simulate LLM-driven multi-step tool execution. This section documents hard-learned debugging findings.

#### How test-tool-caller Works

1. The first user message is parsed as a JSON array of tool call definitions (name, tool, arguments)
2. `$`{name.field} placeholders in arguments are resolved from prior step outputs
3. Each turn: the model counts completed assistant tool calls, returns the next unsolved step as tool_calls, or a summary when all steps complete
4. The summary format is: `"All **N** tool call batch(es)."` (with markdown bold)

#### Root Cause: G13/G14 Were Always Passing on the Backend

The noop provider and omniagent **were working correctly** : the summary was being produced and posted to Mattermost. The bug was a **substring mismatch** in the test assertions:

- **Summary text:** `All **4** tool call batch(es) completed.`
- **Test check:** `"4 tool call" in msg` → **False** because the `**` markdown bold syntax sits between `4` and ` tool call`
- **Fix:** Changed to `"**4** tool call batch" in msg`

Same for G14 (checking `"**3** tool call batch" in msg`).

#### Documented Rule for Test Checks

**Always match the actual message text, not a mental model of it.** When verifying LLM-generated text in tests:
1. First capture the actual message being posted (via Mattermost API or logs)
2. Copy-paste the exact substring that identifies it
3. If the LLM uses markdown formatting (`**bold**`, `_italic_`, `` `code` ``), include those characters in your check
4. When debugging: query the actual Mattermost posts before assuming the backend is broken

```python
# ❌ WRONG : missing markdown chars
if "4 tool call" in msg:
    ...

# ✅ CORRECT : matches actual text including bold markers  
if "**4** tool call batch" in msg:
    ...
```

#### How to Debug G13/G14 Test Failures

1. **Check Mattermost posts directly** to see if the response was actually delivered:
   ```python
   posts = json.loads(urllib.request.urlopen(
       f"{MM}/api/v4/channels/{channel_id}/posts",
       headers={"Authorization": f"Bearer {admin_token}"}
   ).read())
   for pid, post in posts.get("posts", {}).items():
       print(post.get("message", "")[:200])
   ```

2. **Check noop provider logs** : the noop provider logs every request with `[noop-debug]`:
   ```bash
   docker compose logs noop-provider | grep "noop-debug"
   ```
   Key log lines: `_parse_script: found N items`, `_count: M/N completed`, `_generate: finish=stop`

3. **Check omniagent logs** for deliver requests:
   ```bash
   docker compose logs omniagent | grep "method=deliver"
   ```

4. **Check the output of `_count_completed_and_outputs`** to verify tool call counting. The counting maps assistant tool_call IDs to tool result IDs positionally (step 0 → tc_ids[0], etc.).

5. **If a test times out** but `_parse_script` shows the script was found and `_count` shows all steps completed, the issue is likely in how the test checks for the response : not in the provider or agent.

#### Placaholder Resolution (`${name.field}`)

The noop provider resolves `${step_name.field_name}` placeholders by looking up `outputs[step_name][field_name]`. The `outputs` dict is built from tool results:

```python
# In _count_completed_and_outputs:
outputs["long_run"] = tool_result  # e.g. {"task_id": "task_34_3", ...}
```

**Critical:** If the tool result is plain text (not JSON), it's stored as `{"text": raw_string}`. This means `${long_run.task_id}` would look for `outputs["long_run"]["task_id"]` : which exists only if the tool returned JSON with that key. For `test-python-tool_lorem`, the initial response IS JSON (with `task_id`), so resolution works for the 4-step G13 script.

#### Avoiding the Loop Bug

When omniagent calls the model and receives a `finish_reason: "stop"` response with content, it posts that content to the channel and **should not call the model again** until a new user message arrives. If it does call again (fresh context), the noop re-executes from step 0, creating an infinite loop. The noop has a guard (`_generate` checks if the last assistant message already has the summary) but this only triggers when the conversation context is preserved : not on fresh calls.

If you see infinite noop loops, check whether:
- Planning phase is disabled for test-tool-caller (`"plan": False` in the channel PATCH)
- Omniagent is making redundant model calls after receiving `finish_reason: "stop"`

### Erroneous Plugin Copies (Binary-Only)

The following directories in `plugins/mcp/` are **erroneous copies** of built-in plugins, containing only binaries (no source code: no `Cargo.toml`, no `src/`):
- `cron`, `kanban`, `search`, `memory`, `metrics`, `query`, `plugin-manager`, `subtasks`, `hindsight`

These have `plugin.json` and a compiled binary but no source code. They show with `is_duplicated=true, has_source_code=false` in the dashboard. The actual source for these plugins is only in the **omniagent workspace** at `/app/plugins/mcp/<name>/`.

**These will be removed in a future cleanup.** Do NOT attempt to install or compile them from omni-stack.

**Install/Reinstall with Builtin Fallback:** The omniagent install/reinstall handlers now automatically fall back to the builtin source when a bundled directory exists but has no source code. So even if these binary-only copies are present, installing or reinstalling will succeed by compiling from `/app/plugins/mcp/<name>/` instead.

### No-Source and Binary-Only Plugins

- Binary-only plugins (only `plugin.json`, no Cargo.toml) have `has_source_code = false`: Install/Reinstall buttons are hidden in the dashboard
- The "no source" badge appears in yellow (`badge-warning`) with a tooltip
- These can still be enabled/disabled if they have a working binary, but binary-only entries in omni-stack that point to `mcp-server-<name>` are non-functional: the binary doesn't exist in the omni-stack path

### Build Tips

- First build takes time (dependency compilation). Subsequent builds use cache.
- Run `cargo build --release` from the plugin's own directory.
- Each plugin has its own `target/` directory.

### Test Cleanup: Use `git checkout` Only, Never `git clean`

The `_git_discard_all()` function MUST restore tracked files via `git checkout -- .` but MUST NOT run `git clean -fd`. The clean step deletes compiled binary directories (like `target/` for the mattermost platform plugin). Only tracked files should be restored : build artifacts and compiled binaries must be preserved.

```python
# CORRECT : restores tracked files only, preserves build artifacts
def _git_discard_all(repo_dir):
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_dir, capture_output=True)
    # Do NOT add git clean -fd : it deletes compiled binaries

# WRONG : git clean -fd deletes target/ and other build artifacts
def _git_discard_all(repo_dir):
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "clean", "-fd"], cwd=repo_dir, capture_output=True)  # ❌
```

### Mattermost Platform Plugin Binary

- Source tracked in omni-stack at `plugins/platforms/mattermost/`
- Compiled binary at `plugins/platforms/mattermost/target/release/mattermost-platform`
- `_ensure_mm_platform_binary()` checks if binary exists and compiles if missing : called at start of `test_mm9_e2e`
- The binary survives `git checkout -- .` cleanup (only tracked files are restored)
- Compiling takes ~2.5 min on first build, faster with cached deps

### Plugin Config via `configure` Message (Not Env Vars)

Plugins receive their configuration via the MCP `configure` message after initialization : NOT from environment variables. The `mcp-server-util` library provides `run_server_with_config()` which accepts an `on_configure` callback that receives the plugin's resolved config values from `plugins.yaml`:

```rust
use mcp_server_util::*;

let tools = vec![...];
let on_configure = Some(move |params: Value| {
    // params contains resolved config keys/values
    let new_config = MyPluginConfig::from_json(&params);
    // store in shared state for tools to use
});

run_server_with_config(server_info, tools, on_configure).await
```

**Key rules:**
- Plugins define their config schema in `plugin.json` under `config_schema` (type, default, description)
- Users set values in `plugins.yaml` under the plugin's `config:` section
- Users MAY use `$env:VAR_NAME` in `plugins.yaml` values to source from env vars
- Plugins themselves NEVER read `std::env::var()` for config values (only bootstrap vars like `DATABASE_URL` and `OMNI_DIR` are acceptable)
- Each config key in `plugin.json` config_schema gets sent as a key/value pair in the `configure` params

### Prompt Plugin Config Reference

The `prompt` plugin (`mcp-server-prompt`) has the following config_schema fields in `plugins/tools/prompt/plugin.json`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `planning_complexity_max_chars` | integer | 60 | Max char count for simple prompts (greetings, short commands): these get no plan |
| `planning_complexity_keywords` | string | (long comma-separated list) | Keywords that trigger planning mode |
| `prompt_plan_max_tokens` | integer | 2048 | Max tokens for the planning LLM call |
| `memory_max_chars` | integer | 5000 | Max characters for the memory section in the system prompt |
| `soul_max_chars` | integer | 1000 | Max characters for the user profile section in the system prompt |
| `tokenizer_encoding` | string | "" | Tokenizer encoding for budget calculations (e.g. `cl100k_base`). Empty = use char counts |
| `char_budget_soft` | integer | 350000 | Soft char budget: triggers condensation when exceeded + enough iterations elapsed |
| `char_budget_hard` | integer | 500000 | Hard char budget: condensation triggers immediately when exceeded |
| `token_budget_soft` | integer | 200000 | Soft token budget (used when tokenizer_encoding is set) |
| `token_budget_hard` | integer | 350000 | Hard token budget (used when tokenizer_encoding is set) |
| `old_message_char_budget` | integer | 100000 | Threshold for trimming old assistant messages during condensation |
| `condense_keep_turns` | integer | 4 | Number of most recent assistant turns to preserve when condensing |

The `tokenizer_encoding` field controls whether budgets are in characters (when empty/`None`) or tokens (when set to an encoding like `cl100k_base`). When using tokens, the character count is divided by 4 as a rough token estimate.

These values are read from `plugins.yaml` under the prompt plugin's config, NOT from environment variables. Example:

```yaml
plugins:
  tools:
    - name: prompt
      enabled: true
      config:
        char_budget_soft: 250000
        char_budget_hard: 400000
        tokenizer_encoding: "cl100k_base"
```

### Run Tests Inside the Container (as Root)

The test runner MUST run inside the omniagent container, which runs as root. Running from the host causes false failures:

```bash
docker exec -e PYTHONUNBUFFERED=1 omni-omniagent-1 \
    python3 -u /opt/workspace/omni-stack/scripts/tests.py
```

**Host vs container differences that cause false failures:**
- `git checkout -- .` hits "Permission denied" on root-owned files if run from the host
- When `git checkout -- .` fails (even silently), no tracked files are restored : the working tree remains dirty
- Do NOT run `git checkout -- .` or any git operations on omni-stack from the host for cleanup
- If the repo needs cleaning, do it from inside the container or use `docker exec` to run git commands as root
