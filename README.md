# Omni-Stack

Deployment, configuration, and plugin infrastructure for **OmniAgent**: a next-generation agent system built with Rust, PostgreSQL + pgvector, and MCP tool support.

This repository contains the Docker Compose stack, service definitions, plugin infrastructure, and profile/template management for **OmniAgent**.

> **OmniAgent itself** lives at [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent).  
> **Omni-Dashboard** lives at [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard).

---

## Repository Structure

```
omni-stack/
├ docker-compose.yml         # Production stack
├ docker-compose.dev.yml     # Development overrides
├ .env.example               # Environment template
│
├ plugins/
│   ├ platforms/             # Platform plugins (communication backends) — seed: empty
│   │   └ ...
│   │
│   ├ providers/             # LLM provider plugins — seed: empty
│   │   └ ...
│   │
│   └ tools/                 # MCP server definitions (external subprocess tools) — seed: empty
│       └ ...
│
├ profiles/
│   └ omni/                  # Default profile (config, memories, skills, wiki)
│       ├ config.json        #   Profile configuration
│       ├ memories/          #   MEMORY.md, SOUL.md
│       ├ skills/            #   Practical wiki
│       ├ templates/         #   Prompt templates
│       └ wiki/              #   Wiki content (basically, a long term memory in human readable format)
│
├ services/toolbox/          # Toolbox container (maintenance scripts)
│
├ actions.yml                # Saved action definitions
└ AGENTS.md                  # Operational guide for the LLM agent
```

---

## Quick Start

### Minimal `.env` (necessary)

```env
# ── Required ──
POSTGRES_PASSWORD=***  # PostgreSQL — everything else derivable
TUNNEL_TOKEN=***                         # Cloudflare tunnel to reach the dashboard
COMPOSE_PROFILES=tunnel                  # Which optional services to enable

# ── S3 Backup/Restore (optional, for restoring from backup) ──
S3_ACCESS_KEY=<key_id>
S3_SECRET_KEY=<application_key>
S3_ENDPOINT=https://s3.<region>.backblazeb2.com
S3_REGION=<region>
S3_BUCKET=<bucket_name>
```

`POSTGRES_PASSWORD` is the **only** truly required secret. `DATABASE_URL` is auto-derived from it in `docker-compose.yml`.

> **Provider plugins** (DeepSeek, OpenAI, OpenCode Go, Noop) are built into the omniagent Docker image. No manual setup needed in this repo — just add your API key via the dashboard Settings page after starting.

> If you're **restoring from an existing S3 backup**, include the `S3_*` variables. The `omni-restore.sh` script pulls your previous `.env` (including all secrets, Mattermost config, provider keys) and restores the full PostgreSQL database. After restore, `docker compose restart` to pick up the restored configuration.

### Start

```bash
docker compose up -d
```

This starts the core stack:
- **postgres** — message storage with pgvector
- **omniagent** — the agent API
- **dashboard** — web UI on port 3001 (behind the tunnel)
- **toolbox** — utility container (cron, backup, maintenance)
- **cloudflared** — tunnel to the dashboard (if `COMPOSE_PROFILES` includes `tunnel`)

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
| Dashboard | `http://localhost:12346` | Direct on host |

### Fresh Start vs Restore

**Fresh start:** After the stack starts, open the dashboard. Configure your LLM provider API key (Settings → Secrets). Mattermost setup can be run from the Platforms page if you have the `mattermost` profile enabled.

**Restore from S3:** After starting the stack, run:
```bash
bash /opt/hermes-repo/scripts/omni-restore.sh
```
This downloads your previous `.env`, PostgreSQL dumps, and state. Then restart to apply:
```bash
docker compose restart
```

---

## Usage

### Cron Jobs

Cron schedules use **5-field Linux format** (`min hour day month weekday`). The scheduler internally prepends `0` (second=0) for the `cron` crate. Both `create_cron_job` and `update_cron_job` MCP tools validate exactly 5 fields.

Examples:
- `0 * * * *`: every hour
- `*/15 * * * *`: every 15 minutes
- `0 9 * * 1-5`: weekdays at 9am

### Profiles

Profiles bundle model configuration, provider, and tools. Managed via the Dashboard UI or direct SQL.

### Channels

Channels represent communication endpoints (Telegram, Mattermost, API, cron). Each channel has its own profile and model configuration. Messages are processed sequentially within a channel, in parallel across channels.

### Plugins

Plugins are configured via YAML files in the repository root (`platforms.yml`, `providers.yml`, `tools.yml` — created by forked repos that add plugins). Each plugin directory under `plugins/` contains a `plugin.json` manifest.

OmniAgent uses a **three-source** plugin system:

| Source | Location | Description |
|--------|----------|-------------|
| **Bundled** | `plugins/{type}/{name}/` | Standalone crates added by forked repos (same structure as built-in, with `plugin.json` and source code) |
| **Built-in** | `/app/plugins/{type}/{name}/` | Workspace crates inside the omniagent Docker image |
| **Remote** | `plugins/{type}/.remote/{name}/` | Git-cloned from external repositories |

**Display priority (dashboard):**
- YAML with `remote` → primary = remote
- YAML with `builtin: true` → primary = built-in
- YAML entry without flags → primary = bundled (if present in forked repo)
- No YAML entry → primary = built-in

**Builtin plugins** (cron, kanban, memory, metrics, plugin-manager, query, search, subtasks, hindsight) are workspace members of omniagent at `/app/plugins/{type}/{name}/`. They require `builtin: true` in YAML to activate and are disabled by default.

**Bundled plugins** — forked repos can add standalone plugin crates under `plugins/{type}/{name}/` with a `plugin.json` manifest. These compile independently of omniagent.

For detailed internal documentation, see [AGENTS.md](AGENTS.md).

### Provider Plugins

Provider plugins declare which API format they use via `plugin.json` (in forked repos' `plugins/providers/<name>/plugin.json`):

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

## Development

### Using docker-compose.dev.yml

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --project-name omnidev up -d
```

The dev compose adds:
- Local image builds instead of pulling from GHCR
- Mounted source directories for live development
- Additional debug ports or logging

---

## CI/CD

CI/CD workflows now live in [nexuslbs/omni-deployer](https://github.com/nexuslbs/omni-deployer).

The `publish.yml` workflow builds and publishes Docker images to GHCR on:
- **Push to `stable`**: tags `omniagent:latest`, `omni-dashboard:latest`, `toolbox:latest`
- **Push to `v*` tags**: tags each image with the semver tag (e.g., `omniagent:1.2.3`)

Three parallel jobs build:
1. **omniagent**: from [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent) (multi-stage Rust build)
2. **omni-dashboard**: from [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard) (Svelte + Vite)
3. **toolbox**: from this repo (`services/toolbox/Dockerfile`, alpine-based maintenance container)

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

## Related Repositories

| Repository | Description |
|-----------|-------------|
| [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent) | Core agent (Rust API, MCP framework, LLM execution) |
| [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard) | Web dashboard (Svelte SPA) |
| [nexuslbs/omni-deployer](https://github.com/nexuslbs/omni-deployer) | Deployment orchestration, tests, CI/CD |
| [nexuslbs/omni-workspace](https://github.com/nexuslbs/omni-workspace) | Workspace projects directory |
| **nexuslbs/omni-stack** (this repo) | Docker Compose, plugins, profiles |
