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
/opt/workspace/omni-stack       /opt/data        ← AGENTS.md, wiki, skills
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
