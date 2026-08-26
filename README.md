# OmniAgent Deployment Stack

Deployment, configuration, and plugin infrastructure for **OmniAgent**: a next-generation agent system built with Rust, PostgreSQL + pgvector, and MCP tool support.

This repository contains the Docker Compose stack, service definitions, plugin infrastructure, and profile/template management for **OmniAgent**. It also carries the OMNI_DIR YAML config (`config/*.yml`) that defines channels, kanban boards, workflows, hooks, models, plugins, actions and settings.

**OmniAgent itself** lives at [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent).  
**Omni-Dashboard** lives at [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard).  
**omni-plugins** (plugin-less provider definitions, `models.yml`) lives at [nexuslbs/omni-plugins](https://github.com/nexuslbs/omni-plugins).

---

## Repository Structure

```
<repo>/
├ docker-compose.yml         # Production stack
├ docker-compose.dev.yml     # Development overrides (build from source, host ports 12345/12346)
├ .env.example               # Environment template
│
├ profiles/                  # RUNTIME-ONLY - not shipped by the seed.
│   └ omni/                  # The core auto-creates profiles/<default>/config.json
│                            # at startup ({ "allowed_tools": [] }) and the dir is
│                            # removed when a deploy ends. Forked data repos
│                            # (e.g. omni-root) commit their own profiles/ content
│                            # (config.json, memories, skills, templates, wiki).
│
├ services/
│   ├ cloudflared/           #   Cloudflare tunnel (Dockerfile + config.yaml)
│   ├ grafana/               #   Metrics dashboards (Dockerfile)
│   ├ loki/                  #   Log aggregation (Dockerfile + loki-config.yaml)
│   ├ noop/                  #   Test provider (Dockerfile + server.py)
│   ├ prometheus/            #   Metrics collection (Dockerfile + prometheus.yml)
│   ├ toolbox/               #   Maintenance container (Dockerfile + scripts/)
│   └ vector/                #   Log shipping (Dockerfile + sinks/sources/transforms.toml)
│
├ config/                    # OMNI_DIR yml config - see "Config directory" below
│   ├ actions.yml            #   Action plugin definitions
│   ├ boards.yml             #   Kanban boards (default channel/profile/workflow/plan per board)
│   ├ channels.yml           #   Channels (map key = channel name = stable identifier)
│   ├ models.yml             #   Provider/model overrides (pure definition file, no plugin code)
│   ├ plugins.yml            #   Plugin registry (sources, enable/disable, $env:/$secret: refs)
│   ├ remote.yml             #   Remote plugin sources (git-cloned)
│   ├ settings.yml           #   Global settings incl. default_*_channel selects
│   ├ tasks.yml              #   Hook/cron task templates
│   └ workflows.yml          #   Kanban workflows (roles: executor/tester/reviewer, auto_approve, review_on_fail)
│
├ plugins/                   # Bundled plugins - see "Plugins" below
│   ├ providers/             #   Provider plugins (DeepSeek, OpenAI, ...)
│   ├ platforms/             #   Platform plugins (Mattermost, Telegram, ...)
│   └ tools/                 #   MCP tool plugins
│
└ AGENTS.md                  # Operational guide for the LLM agent
```

---

## Quick Start

### Minimal `.env` (necessary)

```env
# ── Required ──
POSTGRES_PASSWORD=***                  # PostgreSQL - everything else derivable
TUNNEL_TOKEN=***                       # Cloudflare tunnel to reach the
 dashboard
COMPOSE_PROFILES=tunnel                # Which optional services to enable

# ── S3 (backup / checkpoint - optional) ──
# Only needed if you enable the backup/checkpoint cron schedules in docker-compose.yml.
S3_ACCESS_KEY=<key_id>
S3_SECRET_KEY=<application_key>
S3_ENDPOINT=https://s3.<region>.backblazeb2.com
S3_REGION=<region>
S3_BUCKET=<bucket_name>
```

`POSTGRES_PASSWORD` is the **only** truly required secret. `DATABASE_URL` is auto-derived from it in `docker-compose.yml`.

**Provider plugins** (DeepSeek, OpenAI, OpenCode Go, Noop) are built into the omniagent Docker image. No manual setup needed in this repo - just add your API key via the dashboard Settings page after starting. Provider **model lists / overrides** can be customized without touching plugins via `config/models.yml` (see [Models](#models-modelsyml)).

### Start

```bash
docker compose up -d
```

This starts the core stack:
- **postgres** - message storage with pgvector
- **omniagent** - the agent API
- **dashboard** - web UI on port 3001 (behind the tunnel)
- **toolbox** - utility container (cron, backup, maintenance)
- **cloudflared** - tunnel to the dashboard (if `COMPOSE_PROFILES` includes `tunnel`)

Optional services (gated by `COMPOSE_PROFILES`):

| Profile | Services | Purpose |
|---------|----------|---------|
| `tunnel` | cloudflared | Dashboard tunnel |
| `mattermost` | mattermost + mattermost-db | Chat platform |
| `memory` | qdrant, hindsight | Vector search + persistent memory |
| `noop` | noop-provider | Test provider |
| `logs` | vector, loki | Log aggregation |
| `monitor` | prometheus, grafana | Metrics & dashboards |
| `cadvisor` | cadvisor + prometheus | Container metrics |
| `all` | Everything | Full stack |

Combine profiles with commas: `COMPOSE_PROFILES=tunnel,mattermost,memory` or just `COMPOSE_PROFILES=all`.

### Access

| Service | URL | Notes |
|---------|-----|-------|
| Dashboard | Tunnel URL (from Cloudflare) | Authenticated via tunnel |
| OmniAgent API | `http://localhost:8080` | Direct on host |

### Fresh Start

After the stack starts, open the dashboard. Configure your LLM provider API key (Settings → Secrets). Mattermost setup can be run from the Platforms page if you have the `mattermost` profile enabled.

---

## Config directory (`config/`)

OMNI_DIR root-level YAML. `settings.yml`, `channels.yml`, `boards.yml`, `workflows.yml`, `models.yml`, `plugins.yml`, `remote.yml`, `actions.yml` and `tasks.yml` are all read at omniagent startup. See `config/README.md` for the detailed reference. Highlights:

- **settings.yml** - global settings. `default_schedule_channel` / `default_hook_channel` / `default_kanban_channel` control which channel each producer (cron, hooks, kanban) uses when no explicit channel is given. Token budgets live here too: `prompt_token_budget_soft` / `prompt_token_budget_hard`.
- **channels.yml** - the map **key is the channel NAME** (the stable identifier used in the API, `threads.channel_id`, `kanban_tasks.channel_id`, ...). Entries without a `platform:` key are `cli` channels (kanban/cron system channels are platform-less).
- **boards.yml** - kanban boards (feature-gated: active only while the file exists).
- **workflows.yml** - kanban role workflows.
- **models.yml** - provider/model overrides (plugin-less providers, model lists, per-model token budgets).
- **plugins.yml / remote.yml / actions.yml** - plugin registry, remote git sources, action plugins.
- **tasks.yml** - hook and cron task templates (the `hooks:` and `schedules:` sections).

## Usage

### Kanban Boards (`boards.yml`)

A board groups kanban tasks and carries **default execution options** (channel, profile, workflow, plan). The feature is active only while `boards.yml` exists. Resolution order for a thread created from a kanban task:

```
Workflow Role > Workflow > Kanban Task > Board > Channel > Global Settings
```

Boards fields act as the task's fallback when the task does not set the option itself. When `boards.yml` is present, the Kanban API **requires a board** on task create/edit (a task without a board is rejected). The dashboard exposes the board select in the create/edit modals.

```yaml
boards:
  omnidev:
    channel: mm-kanban
    profile: omni
    workflow: omniagent-dev
    plan: true
```

### Kanban Workflows (`workflows.yml`)

Workflows drive the **multi-role kanban lifecycle**: a task moves through steps (`running` → `review`/`testing` → ...) with a distinct template/mode/retries per role.

```yaml
workflows:
  omniagent-dev:
    profile: null
    provider: null
    model: null
    plan_mode: null
    retries: 3
    clear_executions_on_review: true
    auto_approve: false          # true = skip reviewer, executor is the gate
    review_on_fail: false        # true = executor failure moves task to review instead of blocked
    roles:
      executor:
        template: dev-executor
        mode: agent              # agent = LLM thread, action = fixed action_id
        action_id: null
        retries: 3
      reviewer:
        template: dev-reviewer
        mode: agent
        plan_mode: on
        retries: 9
      tester:
        template: dev-tester
        mode: agent
        plan_mode: on
        retries: 3
```

Key semantics:
- **`auto_approve: true`** - no reviewer step; the workflow is executor-only and executor success completes the task (`dev-executor` workflow).
- **`review_on_fail: true`** - a failed step routes the task to `review` (reviewer gets a second look) instead of straight to `blocked`.
- **`mode: agent` vs `mode: action`** - per-role Mode select; `action` runs a fixed `action_id` instead of an LLM thread.
- Per-role `profile`/`provider`/`model`/`plan_mode`/`retries` override the workflow defaults.

### Hooks

Hooks are **event-driven, fire-and-forget** notifications fired by the core engine on lifecycle events:
- `thread_started` (on new thread creation),
- `thread_finished` (on terminal thread transition),
- `new_message` (on each persisted message).

Hooks resolve their target channel via `settings.yml` → `default_hook_channel` (or the hook's own channel). The config ships a `hooks` channel (`channels.yml`) and `tasks.yml` hook task templates so you can route lifecycle events back into agent threads (e.g. a kanban-style `hooks` channel that turns events into tasks).

### Cron Jobs

Cron schedules use **5-field Linux format** (`min hour day month weekday`). The scheduler internally prepends `0` (second=0) for the `cron` crate. Both `create_cron_job` and `update_cron_job` MCP tools validate exactly 5 fields.

Examples:
- `0 * * * *`: every hour
- `*/15 * * * *`: every 15 minutes
- `0 9 * * 1-5`: weekdays at 9am

### Channels & Profiles

Channels represent communication endpoints (Telegram, Mattermost, API, cron, cli). Each channel has its own profile and model configuration. Messages are processed sequentially within a channel, in parallel across channels. Profiles bundle model configuration, provider, and allowed tools (managed via the dashboard or direct SQL).

### Models (`models.yml`)

`config/models.yml` is a **pure definition file** (no plugin code) for provider/model overrides:

- `providers.<name>.plugin` - `true`/plugin name → use the provider plugin (`plugins.yml`); `false` → builtin `chat_completions`/`anthropic` support (plugin-less providers, e.g. from omni-plugins' root `models.yml`).
- `providers.<name>.models` - replaces the plugin's `default_model.allowed_values` in selectors (channels page, providers page, `/models`).
- Provider-level fields (`api_mode`, `supports_reasoning`, `default_base_url`, `refresh_url`, `default_model`, `api_key`, `token_budget_*`, `max_tokens*`) override the plugin config.
- `model_config.<model>` - per-model overrides, highest precedence.

Token budget / max_tokens precedence for each of soft/hard independently:
`model_config.<model> > providers.<name> > global settings` (defaults `prompt_token_budget_soft` 100000 / `prompt_token_budget_hard` 500000).

`api_key` supports `$env:VAR` and `$secret:NAME` (same expansion as `plugins.yml`).

### Plugins

Plugins extend OmniAgent with new providers, platforms, and MCP tools. They can be added to this repository under `plugins/{type}/{name}/` (each containing a `plugin.json` manifest) and configured via YAML files in the `config/` directory (`config/plugins.yml`, `config/actions.yml`, `config/remote.yml`, `config/settings.yml`, `config/workflows.yml`). The only gitignored content under `plugins/` is `.remote/` (auto-generated clones from remote installs) - everything else a deployment adds is tracked by default, never silently excluded. During test runs plugins may be added to the bind-mounted `plugins/` dir transiently, but they must be removed after the tests.

Plugins can be **installed and enabled on the fly in the running omniagent** - via the dashboard or the plugin API - without rebuilding or restarting the container.

OmniAgent uses a **three-source** plugin system:

| Source | Location | Description |
|--------|----------|-------------|
| **Bundled** | `plugins/{type}/{name}/` | Standalone crates added to this repository (same structure as built-in, with `plugin.json` and source code) |
| **Built-in** | `/app/plugins/{type}/{name}/` | Workspace crates inside the omniagent Docker image |
| **Remote** | `plugins/{type}/.remote/{name}/` | Git-cloned from external repositories |

**Display priority (dashboard):**
- YAML with `remote` → primary = remote
- YAML with `builtin: true` → primary = built-in
- YAML entry without flags → primary = bundled (if present in this repo)
- No YAML entry → primary = built-in

**Builtin plugins** (cron, kanban, memory, metrics, plugin-manager, query, search, subtasks, hindsight) are workspace members of omniagent at `/app/plugins/{type}/{name}/`. They require `builtin: true` in YAML to activate and are disabled by default.

**Bundled plugins** - standalone plugin crates under `plugins/{type}/{name}/` with a `plugin.json` manifest. These compile independently of omniagent and ship with the deployment.

**Remote plugins** - defined in `config/remote.yml` as a git URL + path (e.g. `https://github.com/...` or a local `file://` checkout). Installing a remote plugin clones its source into `plugins/{type}/.remote/{name}/`. Defining remote plugins in `config/remote.yml` can be **preferable for organization and separation of concerns**: the plugin source lives in its own repository, is versioned independently, and can be updated without touching this repo.

For detailed internal documentation, see [AGENTS.md](AGENTS.md).

### Provider Plugins

Provider plugins declare which API format they use via `plugin.json` (in `plugins/providers/<name>/plugin.json`):

- **`api_mode`**: the default API format for all models. One of:
  - `"chat_completions"`: OpenAI-compatible `/v1/chat/completions` (default)
  - `"anthropic_messages"`: Anthropic Messages API `/v1/messages`
- **`api_modes`** (optional): per-model overrides, keyed by the API mode with wildcard patterns as values. The first matching pattern wins.

```json
{
  "name": "opencode-go",
  "type": "provider",
  "api_mode": "chat_completions",
  "api_modes": {
    "anthropic_messages": ["minimax-*", "claude-*-thinking"]
  }
}
```

Wildcards (`*`) match any sequence of characters. A pattern like `"minimax-*"` matches model IDs starting with `"minimax-"`, while a bare `"minimax"` (no `*`) only matches the exact string `"minimax"`.

This replaces the old `"dynamic"` api_mode: no hardcoded model-to-mode mappings needed in omniagent.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | N/A | PostgreSQL password (the only truly required secret) |
| `COMPOSE_PROFILES` | `` | Enable optional services (tunnel, mattermost, memory, etc.) |
| `TUNNEL_TOKEN` | N/A | Cloudflare tunnel token (required with `tunnel` profile) |
| `OMNIAGENT_IMAGE` | `omniagent-dev:latest` | OmniAgent image reference (use `ghcr.io/nexuslbs/omniagent:latest` for prod) |
| `DASHBOARD_IMAGE` | `ghcr.io/nexuslbs/omni-dashboard:latest` | Dashboard image reference |
| `TOOLBOX_IMAGE` | `ghcr.io/nexuslbs/omni-stack-toolbox:latest` | Toolbox image reference |
| `POSTGRES_IMAGE` | `pgvector/pgvector:pg16` | PostgreSQL image reference |
| `CLOUDFLARED_IMAGE` | `cloudflare/cloudflared:2026.7.1` | Cloudflare tunnel image reference |

---

## Git Plugin Cache

When remote plugins are added via `install-git` or updated via Download (Update), the agent creates a **shared bare-mirror cache** at `.git-cache/<sha256(url)>/` in this repo's root directory.

**How it works:**
- The first plugin from a given git URL triggers a one-time `git clone --mirror` into `.git-cache/<sha256(url)>/`
- Each subsequent plugin from the same URL uses `git clone --reference <cache>`: an **instant, zero-network** local clone that hardlinks objects from the cache
- On Update, the cache is refreshed with `git remote update --prune` before the per-plugin fetch+reset

**Benefits:**
- Adding N plugins from the same repo: 1 network clone (the cache), N instant local clones
- Per-plugin update preserves cargo `target/` (incremental rebuilds)
- Cache lives in `.git-cache/` (gitignored), persists across container restarts

**To clear the cache:**
```bash
rm -rf .git-cache/
```

---

## Bootstrap a Fresh Machine (Vagrant / Cloud VM)

The stack can be brought up on a fresh Linux box two ways:

- **Local VM**: `vagrant up` (see [Vagrantfile](Vagrantfile)) - installs Docker,
  clones the configured repo into `/opt/omni`, then runs
  `docker compose pull` + `docker compose build` for the core (non-profiled)
  services only. Profiled services (mattermost, paperclip, noop, observability)
  are operator opt-in later via `COMPOSE_PROFILES` / `.env`.
- **Cloud VM**: `sudo bash scripts/bootstrap-remote.sh` - the cloud equivalent
  of the Vagrantfile provisioning: installs Docker + the compose plugin
  (apt/yum/dnf detection), reads the repo URL from `config.yml` (`repo` key,
  falling back to `config.example.yml`), clones it into `/opt/omni`, and
  pull/builds the core services. Prints the next steps (create `.env`, run
  services).

Both read `config.yml` (a gitignored copy of
[config.example.yml](config.example.yml)) for the `repo` URL and VM settings.

## Related Repositories

| Repository | Description |
|-----------|-------------|
| [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent) | Core agent (Rust API, MCP framework, LLM execution) |
| [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard) | Web dashboard (Vite + TypeScript SPA) |
| [nexuslbs/omni-plugins](https://github.com/nexuslbs/omni-plugins) | Plugin-less provider definitions (`models.yml`) |
| **This repository** | Docker Compose, plugins, config (profiles/ is runtime-only - forks commit their own) |
