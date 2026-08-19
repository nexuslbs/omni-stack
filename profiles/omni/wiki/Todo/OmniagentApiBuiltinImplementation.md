# Builtin omniagent-api Tool + Fetch allow_unsafe_methods Config

> Status: **IMPLEMENTED 2026-08-19** (omnidev board task,
> task_18cd33ba814357d3) — omniagent `0ecb985` + omni-deployer `a287ffe`
> (GROUP 44, 3/3 PASS) + omni-stack `f85f9bb` (skill omniagent-api.md)
> Scope: omniagent core (src/mcp/mod.rs), plugins/tools/fetch, Dockerfile

## Goal

Let omniagent call its OWN HTTP API directly (create kanban tasks, enable
plugins, trigger reviews, run cron, plugin CRUD) through ONE generic builtin
tool — internal self-API fetch with NO host/scheme/port to configure — plus
give the fetch plugin an `allow_unsafe_methods` config so non-GET HTTP calls
(needed for the plugin API) are possible.

## Implementation (threads 41/42/43 — executor, tester PASS, reviewer APPROVE)

- **omniagent `0ecb985`** `feat(api): builtin omniagent-api 30s timeout +
  fetch allow_unsafe_methods config + in-image API reference`:
  - `src/mcp/mod.rs`: the `omniagent_api_tool()` builtin (registered at
    :819, fn at :873) gains a **30s reqwest timeout** and correct non-2xx
    handling (status >= 400 → tool error) + body serialization; base URL
    `http://localhost:8080` is derived internally — never passed in the
    prompt.
  - `plugins/tools/fetch/plugin.json` + `src/main.rs`: new
    `allow_unsafe_methods` config key (default false) — when set true the
    fetch tool accepts non-GET methods (e.g. POST), which the plugin API
    needs (`/api/plugins/.../config` with
    `{"config":{"allow_unsafe_methods":"true"}}`).
  - **Dockerfile**: copies the repo-root `api-reference.md` into the release
    image → `/opt/omni/docs/api.md` (canonical, fallback `/app/docs/api.md`)
    — always present, so agents can read the route table inside the image.
- **omni-deployer `a287ffe`**: GROUP 44 — test-tool-caller omniagent-api
  e2e + plugin enable; **3/3 PASS** against a live omniagent built from the
  executor commit; fetch unit tests **5/5 PASS**.
- **omni-stack `f85f9bb`**: skill `profiles/omni/skills/omniagent-api.md`
  updated (builtin tool usage, full endpoint map, in-image docs location).

## Usage

The consolidated `builtin_omniagent-api` tool replaces the old `kanban_*` /
`cron_*` plugin tools: `method` (GET/POST/PATCH/DELETE) + `path` +
optional `body` against the core API. Returns `HTTP <status>\n<body>`.
Full endpoint map and examples: skill `omniagent-api.md` (this page is the
implementation record; the skill is the living reference).

## Notes

- Prior consolidation spec: `PluginConsolidationImplementation.md` (cron+kanban
  → ONE generic core builtin omniagent-api tool + DELETE /schedule/{id}).
- The `/api` prefix applies to plugin endpoints (`/api/plugins/...`); kanban,
  schedule, hooks, actions, channels, settings do not carry it.
