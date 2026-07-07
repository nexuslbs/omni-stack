# Omni-Stack — AGENTS.md

## Plugin System Rules & Production Architecture

### Source of Truth

In **production** there is no `omniagent` repo — only `omni-stack`. All plugins live under `/opt/workspace/omni-stack/plugins/` and must be self-contained.

### Plugin Categories — No Priority, No Fallback

A plugin's source is determined **solely by its physical location on disk**. There is no priority order between categories:

| Category | Physical Location | Identified By |
|----------|------------------|---------------|
| **Built-in** | `/app/plugins/{type}/{name}/` | `Cargo.toml` + `plugin.json` or `mcp-config.json` in omniagent workspace |
| **Bundled** | `plugins/{type}/{name}/` (omni-stack) | `plugin.json` at root |
| **Remote** | `plugins/{type}/.remote/{name}/{path}/` | `plugin.json` at subpath + entry in `remote.yml` |

The `source` field in `plugins.yml` is **authoritative** — it determines which source is active. Other sources for the same plugin name exist on disk but are marked `is_duplicated: true` and shown as disabled.

**No function should guess or fall back between sources.** When no YAML entry exists, all sources are discovered and shown as disabled — the user chooses which to enable.

### Display Rules (Dashboard Integration)

The dashboard `/tools`, `/platforms`, and `/providers` pages show **ALL discoverable plugins**, even those not in `plugins.yml`. Plugins without a YAML entry appear as `status: "disabled"`.

The omniagent plugin API (`/api/plugins`) groups by name and assigns a **primary source**:

1. YAML has `remote` → primary = `remote`
2. YAML has `builtin: true` → primary = `built-in`
3. YAML entry exists but no remote/builtin flag → primary = `bundled`
4. No YAML entry → primary = `built-in` (so Install/Enable buttons are available)

Non-primary sources get `is_duplicated: true` and are shown with a yellow "duplicated" badge in the dashboard.

### Builtin Plugin Rules

- **Builtin tools are disabled by default** in YAML. They must have `enabled: true` and `builtin: true` to activate.
- If a tool is in YAML without `builtin: true`, the builtin source is ignored in favor of the bundled copy.
- Builtins with no YAML entry are shown as disabled. Enabling them creates a YAML entry with `builtin: true`.
- The builtin plugins live at `/app/plugins/{type}/{name}/` (inside the omniagent Docker image). They are workspace members in `/app/Cargo.toml` and have `Cargo.toml` + `src/` + `mcp-config.json`.

### Bundled Plugin Detection

Bundled plugins are discovered by scanning `plugins/{type}/{name}/plugin.json`. A directory is only considered a "local/repo plugin" if it has a `plugin.json` at the root. Library-only crates (like `util`) with no `plugin.json` or `mcp-config.json` are skipped entirely.

### Actions Plugin — Self-Contained MCP Server

The `actions` plugin (`plugins/mcp/actions/`) is a fully self-contained MCP server:

- **NO dependency on `omniagent` crate.** It is an independent binary.
- Connects directly to Postgres via `sqlx::PgPool`
- Uses `mcp-server-util` for the stdio JSON-RPC MCP protocol runtime
- Tools: `kanban_dispatcher`, `hindsight_populator`, `relevance_indexer`, `setup_knowledge_pipeline`
- **This plugin has NO builtin counterpart** — it only exists in omni-stack

**Do NOT add `omniagent` as a dependency** to actions or any other omni-stack plugin. In production, the omniagent repo does not exist — only omni-stack is deployed. Plugins must compile standalone.

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

All of these depend on `mcp-server-util = { path = "../util" }` (the shared util crate at `plugins/mcp/util/`).

### Erroneous Plugin Copies (Binary-Only)

The following directories in `plugins/mcp/` are **erroneous copies** of built-in plugins, containing only binaries (no source code — no `Cargo.toml`, no `src/`):
- `cron`, `kanban`, `search`, `memory`, `metrics`, `query`, `plugin-manager`, `subtasks`, `hindsight`

These have `plugin.json` and a compiled binary but no source code. They show with `is_duplicated=true, has_source_code=false` in the dashboard. The actual source for these plugins is only in the **omniagent workspace** at `/app/plugins/mcp/<name>/`.

**These will be removed in a future cleanup.** Do NOT attempt to install or compile them from omni-stack.

**Install/Reinstall with Builtin Fallback:** The omniagent install/reinstall handlers now automatically fall back to the builtin source when a bundled directory exists but has no source code. So even if these binary-only copies are present, installing or reinstalling will succeed by compiling from `/app/plugins/mcp/<name>/` instead.

### No-Source and Binary-Only Plugins

- Binary-only plugins (only `plugin.json`, no Cargo.toml) have `has_source_code = false` — Install/Reinstall buttons are hidden in the dashboard
- The "no source" badge appears in yellow (`badge-warning`) with a tooltip
- These can still be enabled/disabled if they have a working binary, but binary-only entries in omni-stack that point to `mcp-server-<name>` are non-functional — the binary doesn't exist in the omni-stack path

### Build Tips

- First build takes time (dependency compilation). Subsequent builds use cache.
- Run `cargo build --release` from the plugin's own directory.
- Each plugin has its own `target/` directory.
