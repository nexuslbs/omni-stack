# Hooks: Profile-scoped Wiki/Templates/Skills Maintenance + Channel-scoped Summaries

> Status: planned (kanban task TBD)
> Scope: omniagent (core) + omni-stack (config/skills) — shared repo, applies to both omnistable and omnidev.

## Goal

Define **2 hooks** for omniagent, both firing on `thread_finished` every **10 threads**,
both **agentic mode** (spawn a hook-caused agent thread), both scoped across ALL
profiles / ALL channels (no single named target — per-scope counters):

1. **Profile-scoped wiki/templates/skills maintenance hook** — the hook thread
   follows a skill to create/update/delete/merge wiki files, update templates and
   skills, based on the threads between `last_thread` and `current_thread`.
2. **Channel-scoped summaries hook** — the hook thread follows a skill to create
   a summary and save it to the existing `summaries` table (channel as a field).

## Verified facts (do not re-derive)

### Hooks engine already exists (src/hooks.rs)

- Events: `thread_started | thread_finished | new_message` (src/hooks.rs:43-45).
  `fire_thread_finished(thread_id)` called at src/db/threads.rs:91, 102, 833, 1002.
- Scopes: `global | channel | profile` (src/hooks.rs:48-49). Per-scope counters:
  `scope_key()` (src/hooks.rs:542-562) — `scope: profile` with NO `target` returns
  `Some(profile)` (one counter per profile, all profiles); `scope: channel` with NO
  `target` returns `Some(channel_name)` (one counter per channel, all channels).
- Trigger threshold: `count` — counter increments per scope key, triggers when
  `>= count`, resets that key (src/hooks.rs:320-368 `record_and_maybe_trigger`).
- Modes: `agentic` spawns a hook-caused thread (src/hooks.rs:395-480
  `run_agentic`); `action` runs an actions.yml action (src/hooks.rs:482+).
- Event payload built by `build_event` (src/hooks.rs:633-649):
  `{last_thread, last_message, current_thread, current_message, channel, profile}`.
  **The user's `last_thread_id` / `current_thread_id` map to the existing
  `last_thread` / `current_thread` keys** (they hold the thread ids). DO NOT
  rename these keys — unit tests assert them (src/hooks.rs:888+) and the
  dashboard/API consume them.
- The event JSON is embedded into the spawned thread's prompt:
  `"<hook prompt>\n\nEvent: <json>"` (src/hooks.rs:430-434).
- Infinite-loop protection: hook-caused threads never re-trigger hooks
  (src/hooks.rs:256-262, `threads.hook_caused`).
- Hooks are defined in `config/tasks.yml` `hooks:` section (src/tasks_yaml.rs:50-58),
  parsed fresh on every event (src/hooks.rs:224-236). HookDef fields
  (src/tasks_yaml.rs:95-125): `enabled, channel, profile, plan, event, scope,
  target, count, prompt, action, mode, template`. YAML shape:
  ```yaml
  hooks:
    <name>:
      enabled: true
      event: thread_finished
      scope: profile        # or channel
      count: 10
      mode: agentic
      prompt: "..."
  ```
- `config/tasks.yml` currently: `schedules: {}` + `hooks: {}` (both empty).

### ⚠️ Core bug to fix — counter meta is SHARED across scope keys

`meta_get` / `meta_update` (src/hooks.rs:603-626) read/write `counter["meta"]`
at the TOP LEVEL of the counter document, shared across ALL scope keys. The
counter doc is `{"global": 0, "channel": {...}, "profile": {...}, "meta": {...}}`.

For a per-profile hook (scope=profile, no target): when profile A triggers, it
writes `meta.last_thread = A's thread`; when profile B later triggers, `meta_get`
returns **A's last_thread** — WRONG. Same for per-channel hooks. **Requirement:
`meta` (last_thread/last_message) must be stored PER SCOPE KEY** so each
profile/channel's trigger event carries THAT scope's previous trigger ids.
Executor picks the exact shape (e.g. per-key meta map, or meta nested inside each
per-key counter object); the requirement is: the event delivered to a trigger for
scope key K must contain K's own previous last_thread/last_message.

### Summaries table + core summary-creation code

- `summaries` table (db-migrations/src/lib.rs:598-604):
  `id BIGSERIAL PK, channel_id TEXT NOT NULL, next_thread_id BIGINT NOT NULL,
  content TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()`. **channel is
  already a field (`channel_id`, holds the channel NAME)** — matches the user's
  "referencing the channel as a field of the db table (existing summaries table)".
- Query fns: src/db/summaries.rs — `get_latest_summary` (:11), `get_recent_summaries`
  (:36), `create_summary` (:61, INSERT), `delete_old_summaries` (:85).
- ⚠️ **Core code that creates summaries: `generate_summary` MCP tool in the memory
  plugin** (plugins/tools/memory/src/main.rs:575-824 `handle_generate_summary`,
  registered at :1048 with description "Called automatically by the executor after
  each thread completes"). It reads completed threads since the last summary,
  calls the LLM via the proxy, and INSERTs into `summaries`. It is listed in the
  omni profile's allowed tools as `memory_generate-summary`
  (profiles/omni/config.json:88). **Requirement: remove this auto-summary-creation
  path** (the user: "If there is code in omniagent core that creates summaries in
  the summary table, it should be removed") and give the hook thread a minimal
  save path instead (e.g. keep `create_summary` query fn + expose a thin
  `save-summary` MCP tool the hook agent calls with `channel_id, next_thread_id,
  content`; the hook agent itself generates the summary content). Remove the now
  dead config keys (`summarize_after_days`, `channel_summary_tokens`,
  `summary_provider`, `summary_model` — main.rs:534-537, and their values in
  omni-stack config/plugins.yml memory section) if nothing else uses them.
- The hook agent thread reads thread contents via existing allowed tools:
  `search_thread-messages`, `search_channels`, `search_database`, `filesystem_*`
  (profiles/omni/config.json allowed_tools — 86 tools).

### Profile layout (omni-stack, shared by omnistable + omnidev)

- `profiles/omni/skills/` — 9 skills (deploy-suite-debugging.md,
  docker-compose-usage.md, git-workflow.md, knowledge-pipeline.md,
  memory-context-recovery.md, omniagent-api.md, omniagent-optimization.md,
  remote-development.md, workspace-development.md).
- `profiles/omni/templates/` — 7 templates (code-improvement.md,
  dev-development.md, dev-executor.md, dev-reviewer.md, dev-tester.md,
  knowledge-pipeline.md, research.md). Templates are small, included in EVERY
  prompt that uses them.
- `profiles/omni/wiki/` — Memory/ Reference/ Todo/ + index.md + log.md +
  relevant-index.md (root-owned/auto-generated — leave relevant-index.md).

## Hook 1 — Profile-scoped wiki/templates/skills maintenance

- `event: thread_finished`, `scope: profile` (NO target → all profiles, per-profile
  counters), `count: 10`, `mode: agentic`.
- **Prompt**: instruct the hook agent to follow a skill
  (`profiles/omni/skills/wiki-maintenance.md`, created by this task) that:
  - creates wiki files and updates existing ones;
  - updates existing templates and skills; creates/deletes/merges skills and wiki
    files when needed;
  - base everything on the thread contents between `last_thread` and
    `current_thread` (from the Event JSON);
  - IGNORES threads after `current_thread`;
  - MAY look at threads before `last_thread` for context, especially nearby ones;
  - looks ONLY at threads of the respective profile (the profile in the event);
  - creates/updates/deletes/merges ONLY skills and wikis, and updates templates,
    OF THE RESPECTIVE PROFILE;
  - does NOT create, delete or merge templates;
  - avoids updating templates unless REALLY important (templates are small and
    included in every prompt — keep only the most relevant info; weigh whether an
    update is REALLY valuable before doing it).

## Hook 2 — Channel-scoped summaries

- `event: thread_finished`, `scope: channel` (NO target → all channels,
  per-channel counters), `count: 10`, `mode: agentic`.
- **Prompt**: instruct the hook agent to follow a skill
  (`profiles/omni/skills/channel-summary.md`, created by this task) that:
  - creates a summary and saves it to the DB, referencing the channel as a field
    of the existing `summaries` table (`channel_id`);
  - bases it on the thread contents between `last_thread` and `current_thread`
    (from the Event JSON);
  - IGNORES threads after `current_thread`;
  - MAY look at threads before `last_thread` for context, especially nearby ones;
  - looks ONLY at threads of the respective channel (the channel in the event);
  - saves via the minimal save-summary path (see core change above).

## Skills to create (by the executor, along with the hooks)

1. `profiles/omni/skills/wiki-maintenance.md` — how to read thread contents
   between last/current thread ids, extract durable facts, and
   create/update/delete/merge wiki files + skills, and (rarely) update templates
   of the profile. Encodes the constraints above (no template create/delete/merge;
   template updates only when REALLY valuable; profile-scoped only).
2. `profiles/omni/skills/channel-summary.md` — how to read the channel's threads
   between last/current thread ids and write a structured summary into the
   `summaries` table via the save-summary tool.

## Core changes (omniagent)

1. **Per-scope-key meta fix** (src/hooks.rs meta_get/meta_update) so each
   profile/channel scope key keeps its OWN last_thread/last_message.
2. **Remove auto-summary creation** (`generate_summary` tool in
   plugins/tools/memory/src/main.rs + dead config keys) and **add a minimal
   save-summary MCP tool** the hook thread calls (reusing src/db/summaries.rs
   `create_summary`).
3. Keep the rest of the hooks engine unchanged (scope_key, counters, agentic
   runner, loop protection, manual fire, /hooks API).

## Non-goals / DO NOT CHANGE

- DO NOT rename the event JSON keys (`last_thread`/`current_thread`/`channel`/
  `profile`) — unit tests + dashboard consume them.
- DO NOT change the `summaries` table schema (channel_id already exists).
- DO NOT touch cron schedules, the kanban workflow, or other memory plugin tools
  (`memory_list-memories`, `memory_manage-memory`, `memory_promote-to-memory`,
  `memory_review-memories`).
- DO NOT change the /hooks API endpoints or hook_counters table schema beyond the
  per-scope meta requirement.
- DO NOT write `SQLX_OFFLINE=true` anywhere — CI-only.

## Verification gates (executor must run all)

- `cargo fmt --check` (in the dev container, plain — no cd/env prefixes)
- `cargo check --workspace --all-targets`
- `cargo clippy --workspace -- -D warnings`
- `cargo test` (existing hooks unit tests incl. build_event/meta tests must pass
  — update meta tests for the per-scope-key change)
- Plugin build for memory (`cargo build -p omniagent-memory-tool` or workspace
  build as the repo does)
- Config parse: `python3 -c "import yaml,sys; yaml.safe_load(open('config/tasks.yml'))"`
- Live smoke: after deploy, `GET /hooks` (or the API surface that lists hooks)
  shows the two new hooks; trigger a manual fire and confirm a hook-caused thread
  spawns with the Event JSON in its first message.

## Deliverable

- Commit + push to BOTH repos:
  - `omniagent` (meta fix, summary tool changes) — report commit SHA
  - `omni-stack` (tasks.yml hooks, 2 new skills, plugins.yml memory config key
    removal if applicable) — report commit SHA
