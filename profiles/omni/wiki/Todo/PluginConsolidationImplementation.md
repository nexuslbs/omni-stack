# Plugin Consolidation: prompt dual, telegram/hindsight out, search merge, generic omniagent-API tool

**Status:** Planned (mirrors kanban task — see board)
**Date:** 2026-08-17
**Scope:** omniagent (core builtins + plugin crates) + omni-plugins (prompt/hindsight) + omni-stack (plugins.yml/remote.yml wiring)

## Goal

One consolidation pass over the plugin surface, per user direction (2026-08-17):

1. **prompt**: keep the Rust built-in in core AND keep/evolve the python port in
   omni-plugins as the experimental channel (dual-source coexistence).
2. **telegram**: remove from omniagent core (the python platform in omni-plugins
   is the real implementation; the core manifest is a stale shell).
3. **hindsight**: move to omni-plugins and remove from omniagent (may stay Rust
   for now — a Rust source can live in omni-plugins, or a python port).
4. **search + query + metrics** → merge into a single `search` plugin in
   omniagent, keeping the existing tools, mostly just renamed.
5. **fetch, skills, notes**: stay in omniagent (user-committed).
6. **cron + kanban + related** → merge into ONE generic fetch-like "omniagent
   API" tool **in core** (same family as `builtin_wait-task`, `builtin_read-task-logs`,
   etc.), plus `DELETE /schedule/{id}` in the core API, plus a skill `.md` doc.

## Verified facts (do not re-derive — greps from 2026-08-17)

- Repos: `/opt/workspace/omniagent`, `/opt/workspace/omni-plugins`,
  `/opt/workspace/omni-stack` (all main). Builtin (core, non-plugin) tools are
  built in `src/mcp/mod.rs` as `McpTool` structs with `builtin_*` names —
  `builtin_poll-task` (:387), `builtin_wait-task` (:411), `builtin_cancel-task`
  (:449), `builtin_read-task-logs` (:473), `builtin_read-attached-file` (:508),
  `builtin_fail-thread` (:871). `tool_qualify("builtin", name)` names them.
  THIS is where the new generic omniagent-API tool goes.

### 1. prompt — dual-source

- Core: `plugins/tools/prompt/` (Rust, 4698 ln main.rs + memory_store/notes/dump/
  chat_message/compact/prompt_builder) — enabled `source: built-in` (plugins.yml
  :87-94). This is the agent's prompt builder; must stay in core.
- omni-plugins: `tools/prompt/server.py` + `plugin.json` + `mcp-config.json`
  exist (python port, "Python equivalent of the Rust memory plugin" lineage).
  NOT wired in omni-stack (plugins.yml still built-in). The python port is the
  experimental channel — keep it, do NOT delete; wire it as an alternative
  (e.g. `tools.prompt.source: remote` is the switch; the task should document
  how to flip, and ensure the config keys match: char_budget_hard/soft,
  token_budget_hard/soft from plugins.yml :91-94).
- Requirement: core Rust prompt stays the default; omni-plugins python prompt
  coexists (source switch documented; both implement the same MCP tool names
  `prompt_*` so switching doesn't break the agent).

### 2. telegram — remove from omniagent

- Core: `plugins/platforms/telegram/` — MANIFEST ONLY (stale): points at
  `./target/release/telegram-platform` binary that doesn't exist in the
  workspace. plugins.yml :16-19 `source: built-in`.
- omni-plugins: `platforms/telegram/platform.py` + plugin.json + README +
  tests/mock_telegram_api.py — the real python platform (landed via
  task_18cc564faa030eac, commit ddbc385). plugins.yml should switch telegram
  to `source: remote` (or the manifest delete + remote wiring together).
- Requirement: delete `plugins/platforms/telegram/` from omniagent + remove
  from Cargo workspace members; omni-stack telegram → `source: remote` with
  remote.yml entry `platforms/telegram`. Do NOT delete the python platform.

### 3. hindsight — move to omni-plugins, remove from omniagent

- Core: `plugins/tools/hindsight/src/main.rs` (454 ln) — DISABLED in plugins.yml
  (:48-55 `enabled: false`, hindsight_bank/budget/limit/url config).
- Functionality is superseded by the `hindsight_populator` action (moving to
  python in the actions task) + the core MCP memory integration.
- Requirement: create `omni-plugins/tools/hindsight/` — may stay Rust for now
  (copy the crate source + plugin.json/mcp-config.json into omni-plugins as a
  remote Rust plugin, or port to python following tools/memory pattern; user:
  "may be kept in rust for now"). Wire `source: remote` in omni-stack (keep
  `enabled: false` — it stays disabled, just remote-homed). Remove the crate
  from omniagent + Cargo workspace members.

### 4. search + query + metrics → single "search" plugin

- `search` (358 ln): tools `search_messages`, `search_wiki` (main.rs:307, 330).
- `query` (929 ln): tools `query_database`, `query_search_messages`,
  `query_thread_messages`, `query_channel_prompts`, `query_channels`
  (main.rs:776-898). Config: database_url ($env:DATABASE_URL).
- `metrics` (401 ln): tool `get_metrics` (main.rs:358).
- All three are DB/read-only search utilities. Requirement: merge into ONE
  plugin `plugins/tools/search/` (new crate or fold query+metrics code into
  the search crate). Keep ALL existing tools, mostly renamed to the `search_`
  prefix: `search_messages` (from search), `search_wiki` (from search),
  `search_database` (from query_database), `search_messages_v2`?? — NO: keep
  names meaningful and stable; the tool names after merge should be
  `search_messages`, `search_wiki`, `search_database`, `search_thread_messages`,
  `search_channel_prompts`, `search_channels`, `search_metrics`. Update any
  references (actions.yml tool_name entries, workflow templates, skills md
  that call `query_*`/`get_metrics`). plugins.yml: one `search:` entry (drop
  `query:` and `metrics:`), keep database_url config on it.

### 5. fetch, skills, notes — stay

- No change. `fetch` (GET-only, 96 ln), `skills` (create/list/view, 765 ln),
  `notes` (5 note_* tools, 227+280 ln) remain built-in in omniagent.

### 6. cron + kanban + related → generic "omniagent API" tool in core

- `cron` plugin (410 ln) reads/writes `tasks.yml` directly; the CORE server
  already exposes the identical CRUD at `/schedule` (list/get/create/update/
  toggle/threads/subtasks/run — schedule.rs) + `/run-cron/{id}` (mod.rs:257).
  **Gap: NO `DELETE /schedule/{id}`** (verified — dashboard never had a delete
  button; git history has zero delete-schedule commits).
- `kanban` plugin (669 ln) is ALREADY a thin HTTP client to the core kanban API
  (main.rs:22-25 comment: "no SQL is issued from this plugin"; all 7 tools map
  1:1 to `/kanban/*` endpoints incl. `/review`).
- Requirement:
  a. Add `DELETE /schedule/{id}` handler to `src/server/schedule.rs`
     (remove from tasks.yml, ~20 ln, mirror delete_cron_job semantics).
  b. Build ONE generic **core builtin** tool in `src/mcp/mod.rs` (like
     `builtin_wait-task`): `builtin_omniagent-api` (or `builtin_api-call`) —
     a fetch-like tool that does HTTP method+path+json-body against the core
     API (localhost:8080), auth not needed (localhost, same as kanban plugin).
     This replaces cron+kanban as MCP tools.
  c. A skill `.md` (profiles/omni/skills/omniagent-api.md or similar) documenting
     the endpoints (kanban CRUD, schedule CRUD incl. DELETE, run-cron, review,
     plugins, actions) so the agent knows how to drive the API.
  d. Disable/remove the `cron` and `kanban` built-in plugins from plugins.yml
     (source: built-in → disabled) after the generic tool + skill land. The
     plugins can stay in the omniagent repo (crates) but not be registered, or
     be removed — user said "merge", so removal from registration is required;
     crate deletion optional (keep for reference unless clean-removal is
     trivial). Do NOT remove the CORE kanban/schedule API or the scheduler.

## Requirements (ordered)

1. Add `DELETE /schedule/{id}` to core schedule.rs (+ tests: 404 unknown id,
   200 removes from tasks.yml).
2. Add core builtin `omniagent-api` tool in src/mcp/mod.rs (method/path/body,
   JSON response, error surface; mirror wait-task tool pattern).
3. Add the skill md documenting the API surface.
4. Merge search+query+metrics into one `search` plugin (keep tools, rename to
   search_*; update plugins.yml + any references).
5. hindsight: create omni-plugins/tools/hindsight (Rust or python), wire
   remote, keep disabled, remove from omniagent.
6. telegram: delete stale core manifest + workspace member; omni-stack →
   remote (python platform already exists).
7. prompt: keep core Rust default; document/keep the omni-plugins python port
   as the experimental switch (no behavior change to the core prompt builder).
8. cron+kanban: after (1)-(3), disable their plugins.yml entries (they become
   dead weight); verify agent still creates tasks/jobs via the generic tool.

## Non-goals / DO NOT CHANGE

- Do NOT touch the core kanban/schedule HTTP APIs or the scheduler — only ADD
  DELETE /schedule/{id}.
- Do NOT change prompt behavior (the core prompt builder is the agent's brain).
- Do NOT port docker/filesystem/git/ssh/plugin-manager/mattermost to python or
  merge them (security/execution-sensitive — stay Rust built-in; user agreed).
- Do NOT delete the omni-plugins python prompt port.
- Do NOT touch `fetch`/`skills`/`notes` behavior.
- No db-migrations change (kanban/schedule tables untouched).

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo clippy --workspace
  --all-targets -- -D warnings` clean; `cargo test --workspace --release`
  (baseline ~433+ / 0 failed); `cargo fmt --check` clean.
- DELETE /schedule/{id}: unit test + live curl (create → delete → GET 404).
- Generic tool: live call `builtin_omniagent-api` GET /kanban/tasks and
  POST /schedule via the tool; verify identical result to direct curl.
- Merged search plugin: all 7 tools listed under `search_*`; query/metrics
  plugins gone from GET /plugins; actions.yml references updated.
- hindsight remote + disabled; telegram remote (python) loads, no stale
  builtin; prompt still built-in Rust with python port present in omni-plugins.
- Grep audit: no `plugins/tools/telegram` / `plugins/tools/hindsight` /
  `plugins/tools/query` / `plugins/tools/metrics` in omniagent; no
  `mcp-server-cron`/`mcp-server-kanban` in plugins.yml enabled.
- Live (omnidev, isolated): GET /plugins shows the consolidated surface;
  agent-driven kanban task create + cron schedule create/delete via the
  generic tool succeed end-to-end.

## Deliverable

Commit + push to origin/main. Repos: omniagent (DELETE endpoint, generic
builtin tool, search merge, telegram+hindsight crate removal, cron/kanban
registration removal), omni-plugins (hindsight home + prompt port kept),
omni-stack (plugins.yml consolidation, remote.yml hindsight/telegram, skill
md). Report commit SHAs, the tool-name mapping (old query_*/metrics → search_*),
the generic-tool schema, DELETE endpoint diff, plugin inventory before/after,
and live-check evidence. Do NOT claim done until all gates pass.
