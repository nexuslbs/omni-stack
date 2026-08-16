# Paperclip Service + Integration (Implementation Spec)

**Status:** Planned
**Date:** 2026-08-16
**Scope:** omni-stack (compose service), omni-plugins (thin MCP wrapper plugin), omniagent/omni-stack (config wiring), omni-deployer (tests)

## Goal

Add a `paperclip` service to the omni-stack compose file (profiles `paperclip`
and the full-stack umbrella), pinned to the last fixed version from
`ghcr.io/paperclipai/paperclip`, and wire the omniagent to USE paperclip
through the official `@paperclipai/mcp-server` as an external MCP tool plugin.

## What paperclip is (verified 2026-08-16)

- Open-source "app everyone uses to manage agents at work" (paperclipai/paperclip,
  master branch, active). Ships a Node server (port 3100) + UI + embedded DB.
- Releases are CalVer tags: newest release **v2026.722.0** (2026-07-22, commit
  `e55d702916c4d3ddbcac49b697f879808b160f59`). GHCR has NO semver tags — only
  `latest`, `canary`/`nightly`/`beta`, and `sha-<7>` (1162 tags, one per build).
  `sha-e55d702` EXISTS on GHCR and matches release v2026.722.0.
  ⚠️ `latest` currently points to a NEWER build (created 2026-08-10) than the
  newest release — do NOT use `latest` (mutable); pin the sha tag matching the
  newest release and document it.
- Dockerfile: single container, `node server/dist/index.js`, EXPOSE 3100,
  data under `/paperclip` (embedded postgres + uploads + workspaces).
  Required env: `BETTER_AUTH_SECRET` (vendor enforces). Also used:
  `HOST=0.0.0.0`, `PAPERCLIP_HOME=/paperclip`, `PAPERCLIP_DEPLOYMENT_MODE`
  (`authenticated`|`local_trusted`), `PAPERCLIP_DEPLOYMENT_EXPOSURE`
  (`private`|`public`), `PAPERCLIP_PUBLIC_URL`, `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`
  (optional, needed for agents to work), `PAPERCLIP_TOOL_ACTION_SIGNING_SECRET`.
  Official compose reference: `docker/docker-compose.quickstart.yml` in the repo
  (single container, embedded DB). Health route exists: `server/src/routes/health.ts`.

## Integration decision — use the OFFICIAL paperclip MCP server (verified)

Paperclip publishes **`@paperclipai/mcp-server`** (npm, bin `paperclip-mcp-server`,
Node stdio). It is a thin MCP wrapper over the REST API with:

- **30+ typed tools**: `paperclipMe`, `paperclipListAgents`, `paperclipGetAgent`,
  `paperclipListIssues`, `paperclipGetIssue`, `paperclipCreateIssue`,
  `paperclipUpdateIssue`, `paperclipCheckoutIssue`, `paperclipReleaseIssue`,
  `paperclipAddComment`, `paperclipSuggestTasks`, `paperclipAskUserQuestions`,
  `paperclipRequestConfirmation`, `paperclipUpsertIssueDocument`,
  `paperclipRestoreIssueDocumentRevision`, `paperclipControlIssueWorkspaceServices`,
  `paperclipCreateApproval`, `paperclipLinkIssueApproval`,
  `paperclipUnlinkIssueApproval`, `paperclipApprovalDecision`,
  `paperclipAddApprovalComment`, `paperclipListDocuments`/`GetDocument`,
  `paperclipListProjects`/`GetProject`, `paperclipListGoals`/`GetGoal`, etc.
- **Escape hatch**: `paperclipApiRequest` (limited to `/api` paths, JSON bodies) —
  meant for endpoints without a dedicated tool yet. This solves the
  "limited interface as paperclip expands" concern: new paperclip endpoints are
  reachable via the escape hatch immediately, and the official package is
  maintained by paperclip itself (no custom maintenance burden on new versions).

### Why this beats the three candidate approaches (user question)

| Option | Verdict |
|--------|---------|
| 1. Custom Python paperclip plugin in omni-plugins | REJECTED — duplicates what the official MCP server already does (30+ typed tools); every paperclip expansion needs manual plugin maintenance (user's own con). |
| 2. Skill in omni-stack using the fetch plugin | REJECTED as primary — agent must hand-build every URL/body; boilerplate in every call (user's own con). Fine as interim/manual fallback. |
| 3. Thin plugin wrapping fetch with base URL (agent defines path/params/body) | GOOD FALLBACK — essentially re-implements `paperclipApiRequest`; but the official MCP server already IS this (thin REST wrapper) with typed tools on top, vendor-maintained. |
| **4. Thin wrapper plugin around the OFFICIAL `@paperclipai/mcp-server`** | **RECOMMENDED** — typed tools for everything current (direct = option 1's pro), `paperclipApiRequest` for future endpoints (versatile = option 2/3's pro), vendor-maintained (no maintenance con), config is only API URL + API key. |

**Primary path**: omni-plugins `tools/paperclip/` plugin whose mcp-config.json
runs the official `paperclip-mcp-server` binary (Node stdio) with
`PAPERCLIP_API_URL`/`PAPERCLIP_API_KEY` (+ optional COMPANY_ID/AGENT_ID/RUN_ID)
from the plugin config. Installation: `npm install @paperclipai/mcp-server`
at a version matching the pinned paperclip release (verify on npm), following
the reference-server install pattern already used for mcp-fetch/mcp-everything
(remote.yml git installs + build step). The omniagent container has
node v20.19.2; verify npm/npx availability, vendor node_modules at install time.

**Fallback path** (only if the official server cannot be installed/run in the
omniagent container): user's option 3 — thin fetch-based plugin with base URL
config; agent supplies path/params/body. Mirror `paperclipApiRequest` semantics.

## Compose service (the required deliverable)

Add to `docker-compose.yml` (main file, matching the mattermost pattern:
`expose` internal + host port in the dev overlay):

```yaml
  paperclip:
    image: ghcr.io/paperclipai/paperclip:sha-e55d702   # last fixed version (verify)
    profiles: ["paperclip", "all"]                     # user said "full" -> repo umbrella is "all" (mapping, see below)
    restart: unless-stopped
    expose:
      - "3100"
    environment:
      HOST: "0.0.0.0"
      PAPERCLIP_HOME: "/paperclip"
      PAPERCLIP_DEPLOYMENT_MODE: "authenticated"
      PAPERCLIP_DEPLOYMENT_EXPOSURE: "private"
      PAPERCLIP_PUBLIC_URL: "${PAPERCLIP_PUBLIC_URL:-http://paperclip:3100}"
      BETTER_AUTH_SECRET: "${BETTER_AUTH_SECRET:?BETTER_AUTH_SECRET must be set}"
      # OPENAI_API_KEY / ANTHROPIC_API_KEY: operator-provided via env/secrets (NON-GOAL to hardcode)
    volumes:
      - paperclip-data:/paperclip
```

- **Dev overlay** (`docker-compose.dev.yml`): host port mapping for the UI
  (e.g. `"3101:3100"`), matching the mattermost host-port pattern.
- **Profile mapping (explicit)**: the user specified profiles `paperclip` and
  `full`. The omni-stack ecosystem umbrella profile is named **`all`** (11
  services use `["<name>", "all"]`; README: `COMPOSE_PROFILES=all`). Map
  user's `full` → repo's `all` so `COMPOSE_PROFILES=all` includes paperclip.
  Do NOT invent a `full` profile unless the operator confirms.
- **Secrets**: `BETTER_AUTH_SECRET` (required) + `PAPERCLIP_TOOL_ACTION_SIGNING_SECRET`
  generated via `openssl rand -hex 32`, sourced from env/credentials, NEVER
  hardcoded in the repo. LLM keys optional, operator-provided.
- **Volume**: named `paperclip-data` → `/paperclip` (persistence: embedded DB,
  uploads, workspaces).
- **Healthcheck** (optional but recommended): `curl -f http://localhost:3100/api/health`.

## API key flow (needed for the MCP plugin)

The official MCP server requires `PAPERCLIP_API_KEY` (bearer token for `/api`).
After the service is up: create an API key via the paperclip UI
(Settings → API keys / agent API keys; server has `agent_api_keys` +
`board_api_keys` tables) or the documented bootstrap flow. Store the key as a
secret and wire it into the plugin config (`$secret:` ref). Executor documents
the exact method used.

## Config wiring (3 repos)

- **omni-stack** `config/plugins.yml` (or `config/remote.yml` if it follows the
  git-install reference-server pattern): register `paperclip` tool plugin,
  enabled with config `{PAPERCLIP_API_URL: http://paperclip:3100,
  PAPERCLIP_API_KEY: $secret:PAPERCLIP_API_KEY, ...}`.
- **omni-stack** `profiles/omni/config.json` `allowed_tools`: add the paperclip
  qualified tool names (actual registered names, e.g. `paperclip_paperclipMe`,
  `paperclip_paperclipListIssues`, ... — list ALL from the live tools listing,
  including `paperclip_paperclipApiRequest`).
- **omniagent** (only if a code change is needed for the plugin install path —
  likely NOT; the reference-server pattern already exists). NON-GOAL: no
  omniagent core changes for this task unless the executor proves one needed.
- **omni-plugins** `tools/paperclip/`: `plugin.json` (type mcp, config_schema
  for the env vars) + `mcp-config.json` (stdio `paperclip-mcp-server`, env from
  config) + package.json pinning `@paperclipai/mcp-server` version.

## Verification gates (executor)

- `docker compose config` shows the paperclip service with both profiles and
  no env-template errors; `COMPOSE_PROFILES=paperclip docker compose up -d`
  brings it up healthy; `docker compose ps` shows `paperclip` running.
- Paperclip UI reachable (host port in dev); `/api/health` returns OK.
- API key created; plugin registers; `/mcp/tools` lists the paperclip_* tools;
  `profiles/omni/config.json` allowed_tools contains them.
- Live tool call: `paperclipMe` (or the most read-only tool) returns the
  authenticated user — proves API key + URL + plugin wiring end-to-end.
- `cargo check --workspace --all-targets` / `cargo test` green IF omniagent
  changed (likely no-op); deploy runs fully green (exit 0, no errors/skips).
- omnistable frozen: NO migrations/rebuilds/restarts on omnistable stacks;
  changes reach omnistable only via next CI build from main.

## Constraints / non-goals

- NO hardcoded secrets in the repo (BETTER_AUTH_SECRET, API keys, LLM keys all
  via env/$secret:).
- NO `latest` tag — pin the fixed sha (verify `sha-e55d702` vs any newer
  released tag; document the choice).
- Do NOT invent a `full` profile — use the ecosystem `all`.
- Do NOT change existing services/ports/volumes; only ADD the paperclip
  service + its volume.
- If the official MCP server can't run in the omniagent container, implement
  the documented fallback (thin fetch plugin) and say so explicitly — do not
  silently ship a half-working integration.

## Open items for executor

- Exact GHCR sha to pin (verify digest of `sha-e55d702` vs `latest`; pick the
  newest RELEASED fixed tag; record the digest + release version).
- npm availability in the omniagent container + exact `@paperclipai/mcp-server`
  version to install (match the pinned release).
- API key creation method (UI vs bootstrap) — document it.
- `PAPERCLIP_DEPLOYMENT_MODE`: `authenticated` (default, requires login) vs
  `local_trusted` — pick for a private LAN stack and document.
