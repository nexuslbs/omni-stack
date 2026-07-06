# Omni-Stack

Deployment, configuration, and plugin infrastructure for **OmniAgent** — a next-generation agent system built with Rust, PostgreSQL + pgvector, and MCP tool support.

This repository contains everything needed to run the OmniAgent stack in production or development: docker-compose files, plugin definitions (MCP servers, platforms, providers), CI/CD, backup infrastructure, and profile/template management.

> **OmniAgent itself** lives at [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent).  
> **Omni-Dashboard** lives at [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard).

---

## Repository Structure

```
omni-stack/
├── docker-compose.yml         # Production stack
├── docker-compose.dev.yml     # Development overrides
├── .env.example               # Environment template
├── .github/workflows/         # CI/CD
│   └── publish.yml            # Build & push images to GHCR
│
├── plugins/
│   ├── mcp/                   # MCP server definitions (external subprocess tools)
│   │   ├── cron/              #   Cron job management
│   │   ├── kanban/            #   Kanban task management
│   │   ├── memory/            #   Memory tools (promote, list, review)
│   │   ├── fetch/             #   HTTP fetching
│   │   ├── filesystem/        #   File read/write
│   │   ├── docker-compose/    #   Docker Compose orchestration
│   │   ├── git/               #   Git operations
│   │   ├── skills/            #   Skill management
│   │   ├── search/            #   Search tools
│   │   ├── subtasks/          #   Thread subtask management
│   │   ├── query/             #   Database querying
│   │   ├── metrics/           #   System metrics
│   │   ├── plugin-manager/    #   Plugin lifecycle
│   │   ├── hindsight/         #   Hindsight memory population
│   │   ├── actions/           #   Built-in actions (kanban dispatcher, etc.)
│   │   └── ...                #   Test/dev tools
│   │
│   ├── platforms/             # Platform plugins (communication backends)
│   │   ├── mattermost/        #   Mattermost (Rust, full setup + websocket)
│   │   └── telegram/          #   Telegram plugin config
│   │
│   └── providers/             # LLM provider plugins
│       ├── opencode-go/       #   OpenCode Go provider
│       ├── deepseek/          #   DeepSeek provider
│       ├── openai/            #   OpenAI provider
│       └── anthropic/         #   Anthropic provider
│
├── profiles/
│   └── default/               # Default profile (config, memories, skills, wiki)
│       ├── config.json        #   Profile configuration
│       ├── memories/          #   MEMORY.md, SOUL.md
│       ├── skills/            #   Knowledge pipeline, workspace development
│       ├── templates/         #   Prompt templates (blog, knowledge pipeline, etc.)
│       └── wiki/              #   Wiki content (reference docs, research)
│
├── toolbox/                   # Toolbox container (maintenance scripts)
│
├── platforms.yml              # Platform plugin config
├── providers.yml              # Provider plugin config
├── tools.yml                  # Tool plugin config
├── actions.yml                # Saved action definitions
└── AGENTS.md                  # Operational guide for the LLM agent
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose v2
- An LLM API key (OpenCode Go, DeepSeek, OpenAI, or Anthropic)

### Setup

1. **Clone the repos** (side by side):
   ```bash
   git clone https://github.com/nexuslbs/omni-stack.git
   git clone https://github.com/nexuslbs/omniagent.git   # optional, for local builds
   ```

2. **Configure environment**:
   ```bash
   cd omni-stack
   cp .env.example .env
   ```
   Edit `.env` and set at minimum:
   - `LLM_API_KEY` — your LLM provider API key
   - `OMNIAGENT_IMAGE` — set to `ghcr.io/nexuslbs/omniagent:latest` (or `omniagent:local` for local builds)
   - `POSTGRES_PASSWORD` — secure password for PostgreSQL

3. **Start the stack** (production):
   ```bash
   docker compose up -d
   ```

   For **development** (overrides the project name to `omnidev`):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --project-name omnidev up -d
   ```

The docker-compose file has `name: omni` at the top level, so production containers/volumes/networks are prefixed with `omni_` (e.g., `omni_omniagent_1`, `omni_postgres_data`). In dev mode `--project-name omnidev` overrides this to `omnidev_`, keeping dev and prod resources separate.

This starts:

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| **omniagent** | `ghcr.io/nexuslbs/omniagent` | 8080 | The agent API |
| **postgres** | `pgvector/pgvector:pg16` | — | Message storage with vector embeddings |
| **qdrant** | `qdrant/qdrant:v1.18.2` | — | Vector similarity search |

### Verify

```bash
curl http://localhost:8080/health
# → ok
```

---

## Usage

### Cron Jobs

Cron schedules use **5-field Linux format** (`min hour day month weekday`). The scheduler internally prepends `0` (second=0) for the `cron` crate. Both `create_cron_job` and `update_cron_job` MCP tools validate exactly 5 fields.

Examples:
- `0 * * * *` — every hour
- `*/15 * * * *` — every 15 minutes
- `0 9 * * 1-5` — weekdays at 9am

### Profiles

Profiles bundle model configuration, provider, and tools. Managed via the Dashboard UI or direct SQL.

### Channels

Channels represent communication endpoints (Telegram, Mattermost, API, cron). Each channel has its own profile and model configuration. Messages are processed sequentially within a channel, in parallel across channels.

### Plugins

Plugins are configured via YAML files (`platforms.yml`, `providers.yml`, `tools.yml`). Each plugin directory under `plugins/` contains a `plugin.json` manifest.

OmniAgent uses a **three-source** plugin system:

| Source | Location | Description |
|--------|----------|-------------|
| **Bundled** | `plugins/{type}/{name}/` | Standalone crates — actual source code in this repo |
| **Built-in** | `/app/plugins/{type}/{name}/` | Workspace crates inside the omniagent Docker image |
| **Remote** | `plugins/{type}/.remote/{name}/` | Git-cloned from external repositories |

**Display priority (dashboard):**
- YAML with `remote` → primary = remote
- YAML with `builtin: true` → primary = built-in
- YAML entry without flags → primary = bundled
- No YAML entry → primary = built-in

**Bundled plugins** (fetch, filesystem, git, skills, actions, docker-compose, test-rust-tool) compile as standalone Rust crates. They depend on `mcp-server-util = { path = "../util" }` and external crates, never on `omniagent`.

**Builtin plugins** (cron, kanban, memory, metrics, plugin-manager, query, search, subtasks, hindsight) are workspace members of omniagent at `/app/plugins/mcp/<name>/`. They only have mcp-config.json, not plugin.json. They require `builtin: true` in YAML to activate and are disabled by default.

**Erroneous binary-only copies** (cron, kanban, memory, metrics, plugin-manager, query, search, subtasks, hindsight also exist as binary-only directories here) — these will be removed in a future cleanup. The dashboard shows them as duplicated with a yellow badge. Install/Reinstall falls back to the builtin source automatically.

For detailed internal documentation, see [AGENTS.md](AGENTS.md).

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

The `.github/workflows/publish.yml` workflow builds and publishes Docker images to GHCR on:
- **Push to `stable`** — tags `omniagent:latest`, `omni-dashboard:latest`, `toolbox:latest`
- **Push to `v*` tags** — tags each image with the semver tag (e.g., `omniagent:1.2.3`)

Three parallel jobs build:
1. **omniagent** — from [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent) (multi-stage Rust build)
2. **omni-dashboard** — from [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard) (Svelte + Vite)
3. **toolbox** — from this repo (`toolbox/Dockerfile`, alpine-based maintenance container)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | — | LLM provider API key |
| `OMNIAGENT_IMAGE` | `ghcr.io/nexuslbs/omniagent:latest` | OmniAgent image reference |
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `MEMORY_MAX_CHARS` | `5000` | Max characters in MEMORY.md |
| `USER_MAX_CHARS` | `1000` | Max characters for user memory |
| `PLANNING_MODE` | `auto_plan` | Global planning mode |

---

## Related Repositories

| Repository | Description |
|-----------|-------------|
| [nexuslbs/omniagent](https://github.com/nexuslbs/omniagent) | Core agent (Rust API, MCP framework, LLM execution) |
| [nexuslbs/omni-dashboard](https://github.com/nexuslbs/omni-dashboard) | Web dashboard (Svelte SPA) |
| [nexuslbs/omni-workspace](https://github.com/nexuslbs/omni-workspace) | Workspace projects directory |
| **nexuslbs/omni-stack** (this repo) | Deployment, plugins, profiles, CI/CD |
