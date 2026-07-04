# Omni-Stack — AGENTS.md

## Planning Mode Resolution

Planning mode is resolved **at thread creation time** and stamped on `threads.planning_mode`.

**Source locations:**
- **Resolution:** `src/db/threads.rs` — `resolve_thread_planning_mode_with_content()` (core logic), `classify_complexity_for_planning()` (threshold logic), `resolve_cron_planning_mode()`, `resolve_max_plan()`
- **Max iterations:** `src/db/threads.rs` — `max_iterations_for_planning_mode()` maps mode → iteration cap
- **Prompt injection:** `src/prompt_builder.rs` — planning instructions injected based on `thread.planning_mode`
- **Table columns:** `threads.planning_mode` (runtime truth), `channels.planning_mode` (per-channel override), `cron_jobs.planning_mode` (per-job override)

**Modes:**

| Value | Meaning |
|-------|---------|
| `prompt_only` | No planning — LLM responds immediately |
| `auto_plan` | Single planning step before responding |
| `auto_subtasks` | Full subtask decomposition (only when explicitly configured — see below) |
| `always` | Legacy alias for `auto_subtasks` |

**When is `auto_subtasks` available?**

`auto_subtasks` (full subtask decomposition) is **not** the default. It is only available when explicitly configured in one of these ways:

- **Global `PLANNING_MODE` env var** set to `auto_subtasks` or `plan with subtasks`
- **Channel** `planning_mode` set to `auto_subtasks` or `always`
- **Cron job** `planning_mode` set to `plan_with_subtasks` or `auto_subtasks`
- **Kanban tasks** — always use the max plan mode derived from the global `PLANNING_MODE` (so if global is `auto_subtasks`, kanban gets `auto_subtasks`)
- **Task-level explicit override** (for cron jobs and kanban tasks)

If none of these explicitly enables it, the complexity-based classification caps at `auto_plan` — it will never spontaneously promote to `auto_subtasks`.

**Priority chain** (first non-empty wins):

1. **Cron task** `planning_mode` — highest priority, overrides channel and global
   - Valid values: empty (→ complexity-based default), `no_plan` (→ `prompt_only`), `simple_plan` (→ `auto_plan`), `plan_with_subtasks` (→ `auto_subtasks`), `max_plan` (→ `resolve_max_plan(global_mode)`), or direct canonical values
2. **Channel** `planning_mode` — override for the entire channel
   - Valid values: empty (→ default), `prompt_only`, `auto_plan`, `auto_subtasks`, `never` (→ `prompt_only`), `always` (→ `auto_subtasks`)
3. **Kanban tasks** — always `resolve_max_plan(global_mode)` (no complexity classification)
4. **User / Cron default** — `classify_complexity_for_planning()` via content heuristics (see below)

**Complexity classification (`classify_complexity_for_planning`):**

The classifier evaluates prompt content against threshold heuristics and returns a canonical planning mode. The outcome is **capped by the resolved planning mode context** — `auto_subtasks` is only returned when the global `PLANNING_MODE` or an explicit task/channel setting has enabled it.

| Complexity Level | Criteria | Resulting Mode |
|---|---|---|
| **Simple** | `char_len < SIMPLE_MAX (60)` or `word_count ≤ 3 + greeting` | `prompt_only` — no planning needed |
| **Standard** | Everything between Simple and Complex | `auto_plan` — single planning step |
| **Complex** | `char_len > STANDARD_MAX (200)` or action keywords match | `auto_subtasks` **iff** the resolved planning mode context permits it (global `PLANNING_MODE` is `auto_subtasks`, or an explicit task/channel/cron setting enables it); otherwise caps at `auto_plan` |

**Env vars:** `PLANNING_MODE`, `PLANNING_COMPLEXITY_SIMPLE_MAX_CHARS`, `PLANNING_COMPLEXITY_STANDARD_MAX_CHARS`, `PLANNING_COMPLEXITY_KEYWORDS` — all adjustable via `/settings` endpoint.

**Iteration caps** per mode (configured in `AgentConfig`):
- `prompt_only` → `max_iterations_no_plan` (default 5)
- `auto_plan` → `max_iterations_simple_plan` (default 10)
- `auto_subtasks`/`always` → `max_iterations_complex_plan` (default 25)

The per-`process_message` cap was previously hardcoded to 12 (`remaining.clamp(0, 12)`). It now uses the full remaining budget from the MAX_ITERATIONS_* settings directly (`remaining.max(0)`), so a single user message can consume all remaining iterations for the thread.

**When the iteration limit is reached**, the thread is marked `interrupted` (not `failed`). Instead of a hardcoded message, the executor calls the LLM to generate a summary that includes:
- The iteration count (`{current_iter}/{iter_limit}`)
- What was accomplished
- What remains to be done

The LLM summary is saved as the only post-loop message (type `summary`, subtype `interrupted`, `is_summary=true`).

## Actions Feature (Saved Tool Invocations)

The term "actions" is used in two distinct contexts — do not confuse them:

### 1. Saved Actions (Dashboard Pages / HTTP API)

Saved Actions are parameterized tool invocations stored in `{data_dir}/actions.yml`. They let users save a tool name + arguments as a reusable function that can be triggered from the dashboard or associated with a cron job.

**HTTP API** (proxied through dashboard → omniagent, backed by YAML file):
| Method | Route (dashboard proxy) | Description |
|--------|------------------------|-------------|
| `GET` | `/api/actions` | List all saved actions |
| `POST` | `/api/actions` | Create a new action |
| `PUT` | `/api/actions/{id}` | Update an action |
| `DELETE` | `/api/actions/{id}` | Delete an action |
| `POST` | `/api/actions/{id}/run` | Execute a saved action |

The dashboard server proxies `/api/actions*` to `omniagent:8080/actions*` (see `repo/server/index.ts:131-133`).

**YAML format** (`actions.yml` — managed by omniagent via HTTP API):
```yaml
actions:
  a6:
    enabled: true
    tool_name: delete_subtask
    params:
      subtask_id: 1
  builtin_kanban_dispatcher:
    enabled: true
    tool_name: kanban_dispatcher
    params: {}
    description: Pick up pending kanban tasks and create agent threads
    is_builtin: true
```

**Cron job integration:** Cron jobs can reference a saved action via `action_id`. When `mode=action`, the scheduler executes the saved action's tool directly instead of creating an agent thread.

### 2. "actions" MCP Toolset (External MCP Server)

Located at `plugins/mcp/actions/`. This is an external stdio MCP server providing 4 built-in tools commonly used within saved actions:
- `kanban_dispatcher`
- `hindsight_populator`
- `relevance_indexer`
- `setup_knowledge_pipeline`

The name "actions" for this toolset is arbitrary — it just means the tools are designed to be called from saved actions or cron jobs. These are implemented as a separate Rust binary, not built into omniagent.

**Config:** `plugins/mcp/actions/mcp-config.json` — spawns `/app/target/release/mcp-server-actions`.

## Cron Schedule Format

Cron expressions use **5-field Linux format** (`min hour day month weekday`). The scheduler prepends `"0 "` (second=0) for the `cron` crate (which expects 6-field). Both `create_cron_job` and `update_cron_job` MCP tools validate exactly 5 fields.

Examples:
- `0 * * * *` — every hour
- `*/15 * * * *` — every 15 minutes
- `0 9 * * 1-5` — weekdays at 9am

## Available MCP Tools (You Have NO Shell)

**You have NO shell/terminal tool.** You can ONLY use the registered MCP tools. Do NOT write shell commands or expect to execute arbitrary docker/podman/git commands directly — use the appropriate MCP tool instead.

| Task | Available Tool | Parameter Pattern |
|------|---------------|-------------------|
| Run docker compose commands | `compose` | `command="up -d", project_dir="<host-abs-path>"` |
| Exec commands inside a service | `compose` | `command="exec", service="name", args="cmd"` |
| Query PostgreSQL | `query_database` | `operation="select", query="SELECT..."` |
| Read/write files | `filesystem_read`/`filesystem_write` | `path="<cont-abs-path>"` |
| HTTP requests | `fetch` | `url="http://...", method="GET"` |

## Docker & Deployment Pitfalls

### ⚠️ You have NO shell — use MCP tools only

You cannot run `docker stop`, `rm`, `exec`, `ps`, `git`, `curl`, `ls`, or any other shell command directly. All Docker operations must go through the `compose` MCP tool. All file operations must go through the `filesystem_*` tools.

To stop a container that belongs to a compose project:
```
compose(project_dir="<project-dir>", command="stop", service="web")
compose(project_dir="<project-dir>", command="down")  # stops all services
```
The `compose` tool supports: `up`, `down`, `ps`, `logs`, `build`, `restart`, `stop`, `exec`, `pull`.

### ⚠️ Container filesystem path mismatch

The `filesystem` and `compose` tools operate in different path namespaces due to volume mounts:
```
Host path                       Container path
/opt/workspace/omni-workspace   /opt/workspace   ← filesystem writes go here
/opt/workspace/omni-stack       /opt/omni        ← AGENTS.md, wiki, skills
```

**Critical effect:** Writing to `/opt/workspace/playground/...` via `filesystem_write` places bytes at `/opt/workspace/omni-workspace/playground/...` on the HOST. But `compose(project_dir="/opt/workspace/playground/...")` uses the actual host path — which does NOT contain those files.

**Rule:** Before writing files for later docker deployment, verify the mount map. Write to paths where the container `Destination` corresponds to a host path that `compose` can reach.

### ⚠️ Port checking via `fetch` is container-scoped

`fetch("http://localhost:PORT/")` only checks ports INSIDE this container's network namespace. A container like `repo-web-1` may have `0.0.0.0:12347->5173/tcp` on the HOST but be unreachable from inside this container's localhost. **`fetch` will return connection refused even when the port is occupied on the host.**

**Always check port availability via:**
```
compose(project_dir="<project-dir>", command="ps")
```
Or query running containers via `query_database` on Docker metadata if available.

### ⚠️ Writing compose file !== deploying

Writing a `docker-compose.yml` via `filesystem_write` does NOT deploy it. You must ALWAYS follow up with:
```
compose(project_dir="<verified-host-path>", command="up", args="-d")
```

### ⚠️ No infrastructure upgrades during deployment tasks

When a task says "deploy X", do NOT upgrade X's infrastructure (e.g., changing from Python HTTP to nginx, adding features, restructuring the compose file). Deploy what exists. Infrastructure improvements belong in their own task.

## Plugin Configuration Architecture

All plugins receive their configuration via **environment variables** passed to the subprocess. This is the standard Unix mechanism — configuration is available from process start, no protocol handshake needed.

**How it works:**
1. `platforms.yml` (or `tools.yml`/`providers.yml`) defines config values per plugin, using `$env:VAR` references for secrets
2. `plugins_yaml.rs` resolves `$env:` references against the omniagent process environment
3. `merge_yaml_config_into_env()` derives environment variable names from config keys: `{PLUGINNAME}_{KEY_UPPERCASE}` (e.g., `server_url` → `MATTERMOST_SERVER_URL`)
4. The plugin subprocess receives these as environment variables at spawn time
5. The plugin reads its config via `std::env::var()` — available immediately, no wait required

**The `env` block in `plugin.json`:**
- Defines additional environment variables for the subprocess
- Supports `${VAR}` substitution against the omniagent process environment
- Should only contain vars the plugin actually reads (e.g., `RUST_LOG`)
- Config-derived vars (from `merge_yaml_config_into_env`) do NOT need env block entries — they're automatically derived from config keys

**Key principles:**
- Plugins MUST have access to their config from the beginning — this is why env vars are the right mechanism
- Protocol-based config delivery ("configure" messages) is unnecessary and violates the principle of config-at-start
- If a plugin needs a config value, it reads it from an env var — that env var is set by the omniagent framework automatically from the YAML config
- The config schema in `plugin.json` documents which env vars the plugin uses; the `env` block resolves their values at manifest load time

## Mattermost Setup Flow

The Mattermost platform setup is triggered via `POST /api/plugins/mattermost/setup` and is fully self-contained — the setup logic runs inside the Rust plugin binary itself, no external scripts needed.

### What the setup does (in order):

1. **Authenticate** — Uses the `access_token` from config if valid; otherwise falls back to admin credentials (`admin_user`/`admin_password`) for bootstrap (creates first admin user on fresh Mattermost). The plugin's Rust code handles all authentication fallbacks — admin login, token-based auth, and fresh-DB user creation — without external scripts.

2. **Create or find team** — Creates team from `setup_team` config value (resolved from `$env:MM_TEAM`). Uses direct API lookup (`GET /api/v4/teams/name/{name}`) to find existing teams. If team exists, uses it; otherwise creates it.

3. **Add bot to team** — After team resolution, adds the bot user as a team member.

4. **Create or find channel** — Creates channel from `setup_channel` config value under the team.

5. **Create 3 users** (if they don't exist):
   - Admin user (`admin_user`) — created as system admin
   - Test user (`test_user`) — regular user
   - Bot user (`bot_user`) — created as user then converted to bot account
   Each user is added to the team and channel as a member.

6. **Generate bot access token** — Uses admin credentials (or bot PAT as fallback) to create a new personal access token for the bot user.

7. **Save bot token to .env** — Writes `MATTERMOST_ACCESS_TOKEN=<token>` to the .env file on disk. Refreshes the process environment via `std::env::set_var()` so the new token is immediately available for `$env:` resolution.

8. **Hot-reload the Mattermost plugin** — Calls `reload_platform_plugin()` which refreshes the process env from .env, then signals the running platform client to respawn. The respawned subprocess reads `platforms.yml` with `access_token: "$env:MATTERMOST_ACCESS_TOKEN"`, resolves it from the refreshed env, and authenticates with the new token.

9. **Create omniagent channel** — Creates (or updates) an omniagent channel record:
   - `name: mm-{MM_CHANNEL}` (e.g., `mm-setup`)
   - `platform: mattermost`
   - `resource_identifier: <mattermost_channel_id>`
   - `external_id: <mattermost_channel_id>`
   - `cause: "setup"`

### Idempotency

Existing teams, channels, and users are detected and reused. A new bot token is generated each time. The omniagent channel is updated via `ON CONFLICT DO UPDATE`.

### Key design decisions

- **`$env:` in platforms.yml** — Secrets never appear in YAML config files. The access_token, admin_password, test_password, etc. use `"$env:VAR_NAME"` references resolved at runtime.

- **Plugins are env-var agnostic** — The plugin binary receives config values via the `configure` JSON-RPC message with original field names (e.g. `access_token`, `server_url`). It never reads `MATTERMOST_ACCESS_TOKEN` or similar env vars. The `$env:` indirection is omniagent's concern, not the plugin's.

- **Setup runs entirely in Rust** — No Python scripts. The plugin binary is invoked with the `setup` argument, runs the full setup flow (authenticate, create users, team, channel, generate token), and exits. The legacy `mm-setup.py` has been removed.

- **Token saved to .env not platforms.yml** — Writing to .env (then refreshing process env) keeps the config file environment-agnostic and ensures the token is available to all `$env:` resolvers.

- **No omniagent restart required** — The hot-reload mechanism refreshes the process env from .env and signals the platform client to respawn. No container restart needed.

### Mattermost Plugin: `max_download_bytes` Parameter

The Mattermost plugin now has a configurable `max_download_bytes` parameter controlling file attachment size thresholds:

- **Config field:** Added to `PluginConfig` struct at `plugins/platforms/mattermost/src/main.rs:955`
  - `#[serde(default = "default_max_download_bytes", deserialize_with = "deserialize_u64_from_string_or_number")]`
  - Default: 10 MB (`10 * 1024 * 1024`)
- **plugin.json** (`config_schema`): Integer field, min 1 KB, max 1 GB, default 10 MB
- **Behavior change:** Files under the threshold are downloaded and base64-encoded inline (as before). Files exceeding the threshold have `content: None` — the omniagent can fetch them on demand via the `read_attached_file` MCP tool

**Call path propagation:** `server_url` and `max_download_bytes` are now threaded through all inbound paths:
- `send_inbound_notification(client, post, ch_id, server_url, max_download_bytes)` — constructs file attachments with size check
- `poll_channel(... server_url, max_download_bytes)` — polling mode
- `process_channel_event(... server_url, max_download_bytes)` — WebSocket debounced processing
- `ws_event_loop(... max_download_bytes)` — WebSocket main loop

All four `poll_channel` call sites and the `process_channel_event` call site in the WS event handler were updated to pass through these parameters. The `server_url` is also included in the notification metadata so the omniagent can construct file fetch URLs without re-parsing the plugin config.

- **Plugin uses direct team lookup** — `find_team_by_name` uses `GET /api/v4/teams/name/{name}` instead of listing all teams (which filters by membership). This ensures the bot can find the team before being added as a member.
