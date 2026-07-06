# Omni-Stack — AGENTS.md

## Plugin System Rules & Production Architecture

### Source of Truth

In **production** there is no `omniagent` repo — only `omni-stack`. All plugins live under `/opt/workspace/omni-stack/plugins/` and must be self-contained.

### Plugin Categories

| Category | Source Location | Build Method |
|----------|----------------|-------------|
| **Bundled** | `plugins/{type}/{name}/` | Standalone `cargo build` from plugin's own `Cargo.toml` |
| **Built-in** | `/app/plugins/{type}/{name}/` (omniagent workspace) | Workspace build from `/app/Cargo.toml` |
| **Remote** | `plugins/{type}/.remote/{name}/` | Git clone then standalone build |

### Actions Plugin — Self-Contained MCP Server

The `actions` plugin (`plugins/mcp/actions/`) is a fully self-contained MCP server:

- **NO dependency on `omniagent` crate.** It is an independent binary.
- Connects directly to Postgres via `sqlx::PgPool`
- Uses `mcp-server-util` for the stdio JSON-RPC MCP protocol runtime
- Tools: `kanban_dispatcher`, `hindsight_populator`, `relevance_indexer`, `setup_knowledge_pipeline`

**Do NOT add `omniagent` as a dependency** to actions or any other omni-stack plugin. In production, the omniagent repo does not exist — only omni-stack is deployed. Plugins must compile standalone.

### Bundled Plugins That Work Standalone

The following omni-stack plugins compile as standalone crates (no omniagent dependency):

| Plugin | Cargo.toml | Requires |
|--------|-----------|----------|
| `actions` | `plugins/mcp/actions/Cargo.toml` | `mcp-server-util`, `sqlx`, `tokio` |
| `fetch` | `plugins/mcp/fetch/Cargo.toml` | `mcp-server-util`, `reqwest` |
| `filesystem` | `plugins/mcp/filesystem/Cargo.toml` | `mcp-server-util`, `tokio` |
| `git` | `plugins/mcp/git/Cargo.toml` | `mcp-server-util`, `reqwest` |
| `skills` | `plugins/mcp/skills/Cargo.toml` | `mcp-server-util` |
| `test-rust-tool` | `plugins/mcp/test-rust-tool/Cargo.toml` | (various) |

All of these depend on `mcp-server-util = { path = "../util" }` (the shared util crate at `plugins/mcp/util/`).

### Erroneous Plugin Copies

The following directories in `plugins/mcp/` are **erroneous copies** of built-in plugins, containing only binaries (no source code):
- `cron`, `kanban`, `search`, `memory`, `metrics`, `query`, `plugin-manager`, `subtasks`, `hindsight`

These are dead entries — they have `plugin.json` but no `Cargo.toml` or `src/`. Do NOT attempt to install or compile them. The actual source for these plugins is in the omniagent workspace at `/app/plugins/mcp/<name>/`.

These will be removed in a future cleanup.

### Build Tips

- First build takes time (dependency compilation). Subsequent builds use cache.
- Run `cargo build --release` from the plugin's own directory.
- Each plugin has its own `target/` directory.
