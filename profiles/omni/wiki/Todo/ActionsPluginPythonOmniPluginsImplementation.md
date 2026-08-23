# Action Plugin → omni-plugins (Python) + Remove Built-in

**Status:** IMPLEMENTED 2026-08-17 (omniagent `89c08f3`/`1285b50` — built-in Rust actions plugin removed, moved to omni-plugins Python `tools/actions/`; omni-stack `config/remote.yml` wires it (path: tools/actions); deploy-env registration verification in progress — see deploy-suite-debugging skill)
**Date:** 2026-08-17
**Scope:** omni-plugins (new Python action plugin) + omniagent (remove built-in actions plugin) + omni-stack (wiring)

## Goal

Move the action tools out of the omniagent core binary into a **Python plugin in
omni-plugins**, so they can be improved/removed/replaced without releasing a new
omniagent version. The sibling task "kanban dispatcher into core" moves
`kanban_dispatcher` INTO core; THIS task handles the remaining 3 action tools
(`hindsight_populator`, `relevance_indexer`, `setup_knowledge_pipeline`) by
porting them to Python in omni-plugins and **removing the built-in Rust actions
plugin** (`plugins/tools/actions/`) from omniagent.

## Verified facts (do not re-derive — greps from 2026-08-17)

- Repo: `/opt/workspace/omniagent` (branch main), `/opt/workspace/omni-plugins`
  (branch main), `/opt/workspace/omni-stack` (branch main). Dev env:
  omnidev-omniagent-1 container maps /app → omniagent, cargo at
  /usr/local/cargo/bin/cargo, CARGO_HOME=/usr/local/cargo. Non-login shell:
  `docker exec omnidev-omniagent-1 bash -c 'export PATH=/usr/local/cargo/bin:$PATH CARGO_HOME=/usr/local/cargo; cd /app && <cmd>'`.

### 1. Current actions plugin (omniagent built-in)

- **Location**: `plugins/tools/actions/` — Rust crate `mcp-server-actions`,
  Cargo workspace member (omniagent `Cargo.toml:18`).
- **Files**: `Cargo.toml`, `plugin.json`, `mcp-config.json`, `src/main.rs`
  (562 lines), `.sqlx/` cache. Depends on `omniagent = { path = "../../../" }`
  (uses `tasks_yaml`, `config_path`), `sqlx`, `reqwest`, `sql-forge`, `chrono`.
- **4 tools** registered in `src/main.rs` (tools vec at :386-422):
  1. `kanban_dispatcher` — being REMOVED by the sibling core-dispatcher task;
     NOT part of this task's port (do not port it).
  2. `hindsight_populator` (handler :132-174) — reads
     `{omni_dir}/hindsight_watermark.json` (`{"last_message_id": N,
     "last_run_at": ...}`), SELECTs `id FROM messages WHERE id > :last_id AND
     msg_type IN ('message','reasoning','plan','error','cause','tool',
     'tool-result') AND COALESCE(content,'') != '' ORDER BY id ASC LIMIT 200`,
     writes back a watermark with the max id. Returns summary string.
  3. `relevance_indexer` (handler :180-237 + `collect_md_files` :239) — scans
     `{omni_dir}/profiles/{profile}/wiki` recursively for `.md` files, scores by
     mtime recency (50/40/30/10 buckets: <1h/<24h/<7d/else), sorts desc, takes
     top 30 (≤1000 chars), writes `{wiki_dir}/relevant-index.md`.
     `default_profile_name()` = the omni profile (profile name resolution —
     port faithfully; check `crate::profile::default_profile_name` semantics).
  4. `setup_knowledge_pipeline` (handler :269-319) — idempotent: if
     `knowledge_pipeline` already in `tasks.yml` `schedules:`, returns "already
     exists". Else inserts a `ScheduleDef`:
     `enabled: true, channel: "cron-default", profile: "pipeline", plan: true,
     cron: <args.schedule or "0 */6 * * *">, prompt: <args.prompt or the
     knowledge-pipeline prompt>, skills: ["knowledge-pipeline"], silent: false,
     display_name: "Knowledge Pipeline"` and saves tasks.yml. NOTE: Rust uses
     `tasks_yaml::load_tasks_or_empty` + `save_tasks` — the Python port must
     edit `{omni_dir}/config/tasks.yml` directly (parse YAML, add/merge the
     schedule key, atomic write). Verify the ScheduleDef field names against
     `src/tasks_yaml.rs:63-100` (enabled, channel, profile, plan, cron, prompt,
     action, template, skills, silent, display_name) so the YAML shape matches
     what the Rust scheduler reads.
- **plugin.json**: id `mcp-server-actions`, name "Actions MCP Server",
  config_schema keys: `HINDSIGHT_URL`, `database_url` ($env:DATABASE_URL),
  `omni_dir` ($env:OMNI_DIR), `llm_provider` ($env:LLM_PROVIDER),
  `omniagent_url` ($env:OMNIAGENT_URL). `omniagent_url`/`llm_provider` are used
  ONLY by kanban_dispatcher (being removed) — decide whether to keep them in
  the python plugin's config_schema (probably drop; the 3 remaining tools need
  only `database_url` + `omni_dir` + optionally `HINDSIGHT_URL`).

### 2. Registration / wiring today

- **omni-stack plugins.yml**: `tools: actions: enabled: true, source:
  built-in, config: {}` (config/plugins.yml:21-24).
- **omni-stack actions.yml**: action entries mapping action ids to tool names:
  `builtin_relevance_indexer` → `actions_relevance-indexer` (:2-7),
  `builtin_kanban_dispatcher` → `actions_kanban-dispatcher` (:25-30, removed by
  sibling task), `builtin_setup_knowledge_pipeline` →
  `actions_setup-knowledge-pipeline` (:31-36, enabled: false),
  `builtin_hindsight_populator` → `actions_hindsight-populator` (:37-42).
- **Remote plugin pattern (the target)**: omni-plugins hosts python plugins;
  omni-stack `config/remote.yml` lists them by repo+path (e.g. `tools/memory`,
  `tools/paperclip` → `url: https://github.com/nexuslbs/omni-plugins.git,
  path: tools/...`); plugins.yml switches `source: remote` (see `paperclip` at
  config/plugins.yml:77-82 — enabled: true, source: remote). Installer clones
  to `{data_dir}/plugins/<type>/.remote/<name>/`
  (`src/plugin/installer.rs:5`, clone logic :277-339).

### 3. Python plugin reference (the pattern to copy)

- **omni-plugins/tools/memory/** — `plugin.json` (name/version/type mcp/
  description/config_schema with `$env:` defaults), `mcp-config.json`
  (servers[0]: transport stdio, command `python3`, args `["server.py"]`, env
  OMNI_DIR/DATABASE_URL, timeout_secs 900, max_retries 1, pool_size 3,
  allowed_tools ["*"]), `server.py` (MCP JSON-RPC over stdio: send_json/
  make_success/make_error, tool registry, psycopg2 optional import).
- **omni-plugins/tools/prompt/server.py** — same python MCP pattern.
- **omni-plugins/platforms/telegram/** — python platform plugin (protocol +
  mock tests), the prior python-port reference.
- omni-plugins git: main branch, remote `nexuslbs/omni-plugins.git`, recent
  commits `ae47260` (paperclip), `ddbc385` (telegram python).

## Requirements

1. **New plugin in omni-plugins**: `tools/actions/` — python MCP server
   (`plugin.json`, `mcp-config.json`, `server.py`, optional tests/README)
   implementing the 3 tools with the SAME tool names as today:
   - `hindsight_populator`
   - `relevance_indexer`
   - `setup_knowledge_pipeline`
   Port the exact behavior from the Rust handlers (queries, watermark file,
   recency scoring, tasks.yml schedule insert — see §1). Tool names stay
   `actions_hindsight-populator` / `actions_relevance-indexer` /
   `actions_setup-knowledge-pipeline` (match what actions.yml `tool_name`
   entries reference) — or, if the plugin registers tools under their bare
   names, update actions.yml tool_name values accordingly; document the mapping.
   Use `psycopg2` for the DB access (optional import like tools/memory).
   Config: `database_url` ($env:DATABASE_URL), `omni_dir` ($env:OMNI_DIR),
   and anything the 3 tools need. Do NOT port kanban_dispatcher.
2. **omni-stack wiring**: add `tools/actions` to `config/remote.yml`
   (`url: https://github.com/nexuslbs/omni-plugins.git, path: tools/actions`);
   switch plugins.yml `tools.actions` to `source: remote`; keep actions.yml
   entries (update tool_name values if the python tool names differ).
3. **Remove the built-in from omniagent**:
   - Delete `plugins/tools/actions/` (Rust crate, plugin.json, mcp-config.json,
     .sqlx, Cargo.toml) and remove `"plugins/tools/actions"` from the Cargo
     workspace members (omniagent `Cargo.toml:18`).
   - Grep for any remaining references to `mcp-server-actions` /
     `server-actions` / `plugins/tools/actions` in omniagent src/ and remove
     (e.g. `src/plugins_yaml.rs:849` mentions the binary name only as a
     comment example — check and adjust if it's an allowed-binary list).
   - Do NOT remove `builtin_kanban_dispatcher` from actions.yml here if the
     sibling core-dispatcher task hasn't landed yet — coordinate: this task
     runs AFTER the core-dispatcher task (serial chain), so that entry should
     already be gone; if not, remove it (it's dead without the plugin).
4. **Verify the stack loads the remote python plugin**: after wiring, the
   plugin installer clones omni-plugins and the core registers the 3 tools;
   `GET /plugins` shows `actions` as remote; the actions.yml actions resolve to
   the python tools.

## Non-goals / DO NOT CHANGE

- Do NOT port `kanban_dispatcher` (sibling core-dispatcher task owns it).
- Do NOT change the 3 tools' observable behavior (same DB queries, same
  watermark format, same relevant-index format, same tasks.yml schedule shape).
- Do NOT change the other 3 tools in the built-in actions plugin beyond
  deletion (hindsight/relevance/setup move wholesale; nothing else lives in
  that crate).
- Do NOT touch the omniagent core scheduler/hooks code paths that CALL
  actions.yml — only the plugin that provides the tools changes.
- Do NOT remove `builtin_relevance_indexer` / `builtin_hindsight_populator` /
  `builtin_setup_knowledge_pipeline` entries from actions.yml unless their
  tool_name needs updating for the python names (keep them, keep is_builtin
  semantics — the actions.yml entries are core config, the tool implementation
  is what moves).
- No db-migrations change.

## Verification gates

- omni-plugins: `python3 -c "import json, yaml"`-style sanity + the plugin
  server starts and responds to MCP `initialize` + `tools/list` with the 3
  tools (run `server.py` locally or in the toolbox with OMNI_DIR/DATABASE_URL
  set). Python version in the runtime container: check what python3 the
  omniagent image ships (the memory python plugin already runs there, so the
  deps are available — `psycopg2` confirmed via tools/memory).
- omniagent: `cargo check --workspace --all-targets` clean, `cargo clippy
  --workspace --all-targets -- -D warnings` clean, `cargo test --workspace
  --release` (baseline ~433+ / 0 failed), `cargo fmt --check` clean, after
  removing the crate + workspace member.
- Grep audit: no `plugins/tools/actions` in omniagent; no `mcp-server-actions`
  references; Cargo.toml no longer lists it; omni-stack remote.yml +
  plugins.yml point at the omni-plugins python plugin.
- Live check (omnidev, isolated): after wiring, `GET /plugins` shows the
  actions plugin as remote with 3 tools; run each action via a real action
  (e.g. `builtin_hindsight_populator` / `builtin_relevance_indexer`) and verify
  the same side effects as before (watermark advances, relevant-index.md
  written, tasks.yml knowledge_pipeline schedule created idempotently).

## Deliverable

Commit + push to origin/main. Repos: omni-plugins (new `tools/actions/` python
plugin) + omniagent (remove `plugins/tools/actions/` + workspace member +
reference cleanup) + omni-stack (remote.yml + plugins.yml + actions.yml
tool_name updates if needed). Report commit SHAs, the tool-name mapping, the
python plugin structure, the removal diff, and the live-check evidence (plugin
listed remote, 3 tools registered, actions produce identical side effects). Do
NOT claim done until all gates pass.
