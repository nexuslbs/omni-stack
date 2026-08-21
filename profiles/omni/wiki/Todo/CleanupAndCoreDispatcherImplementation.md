# Old-Data Cleanup (messages/threads/kanban_history) + Kanban Dispatcher into Core

**Status:** IMPLEMENTED 2026-08-17 (omniagent `26e2ae1` — delete old threads/kanban_history via delete_after_days (0=disabled); kanban dispatcher moved into core (kanban_dispatcher_interval default 15s), removed from actions plugin)
**Date:** 2026-08-17
**Scope:** omniagent core (`src/main.rs`, `src/db/`, `src/agent/config.rs`, `src/server/settings.rs`) + actions plugin (`plugins/tools/actions/`) + omni-stack config (settings.yml, actions.yml)

## Goal

Two changes:

1. **Extend the age-based cleanup** to delete old **threads** and old **kanban_history**
   in addition to the existing old-messages/old-summaries deletion. The days
   threshold uses the existing `delete_after_days` setting (already present,
   default 30); **0 must disable the cleanup entirely** (currently 0 would
   delete everything — no guard exists).
2. **Move the kanban dispatcher into core**: the dispatch trigger must live
   inside the omniagent core process (a background loop, not an external
   cron/action), with a new global setting for the run interval in seconds,
   default **15s**. The `kanban_dispatcher` action/tool may be removed from the
   actions plugin (it becomes core functionality).

## Verified facts (do not re-derive — greps from 2026-08-17)

- Repo: `/opt/workspace/omniagent` (branch main). Dev env: omnidev-omniagent-1
  container maps /app → repo, cargo at /usr/local/cargo/bin/cargo,
  CARGO_HOME=/usr/local/cargo. Non-login shell:
  `docker exec omnidev-omniagent-1 bash -c 'export PATH=/usr/local/cargo/bin:$PATH CARGO_HOME=/usr/local/cargo; cd /app && <cmd>'`.

### 1. Existing cleanup

- **Daily cleanup loop**: `src/main.rs:277-302` — `tokio::spawn` with
  `interval = Duration::from_secs(86400)`; each tick computes
  `before = Utc::now() - Duration::days(delete_after_days)` and calls:
  - `db::types::delete_old_messages(&pool, before)` → `src/db/messages.rs:219`
    (`DELETE FROM messages WHERE created_at < :cutoff`) — messages only.
  - `db::types::delete_old_summaries(&pool, before)` → `src/db/summaries.rs:85`
    (`DELETE FROM summaries WHERE created_at < :cutoff`) — summaries only.
  - **It never touches `threads` or `kanban_history`** — that is the gap.
- **Setting**: `delete_after_days` ALREADY EXISTS — settings.yml `general:` key
  (`/opt/workspace/omni-stack/config/settings.yml`, value `30`); config field
  `pub delete_after_days: u32` at `src/agent/config.rs:92`, parsed with default
  "30" at `:234` (and again at `:333` for the env bootstrap path). Settings API
  registration: `src/server/settings.rs` — key list `general` vec (~:173),
  `SettingMeta` (~:429), category mapping (~:645), serialization list (~:746).
  Description text: "Days before old messages and summaries are deleted" —
  extend to mention threads + history.
- **0 = disable is NOT implemented**: `before = now - 0 days = now` would
  DELETE EVERYTHING. The task must add the guard: when `delete_after_days == 0`,
  skip the cleanup entirely.

### 2. Schema facts for deleting threads

- FK constraints (verified live):
  - `messages_thread_id_fkey` — messages.thread_id → threads.id
  - `threads_parent_id_fkey` — threads.parent_id → threads.id (self-ref)
  - `thread_subtasks_thread_id_fkey` — thread_subtasks.thread_id → threads.id
  - `kanban_task_dependencies_*_fkey` — dependencies → kanban_tasks
- `kanban_history` has **NO FK** to kanban_tasks (`kanban_task_id` is plain
  text, no constraint) — deletable independently by `created_at`.
- Delete order for threads: messages → thread_subtasks → threads. Must handle
  the threads self-ref (`parent_id`): either delete leaf threads first or null
  out `parent_id` on children before deleting a parent, or delete in two passes
  (children first). Design decision for the executor — but the invariant is:
  no orphaned `parent_id`, no FK violation.
- **Do NOT delete active threads**: only delete threads that are `terminal`
  (status in completed/failed/skipped/interrupted/system, or `terminal=true`)
  AND `created_at < cutoff`. Never delete `pending`/`processing` threads even
  if old (a stuck processing thread is recoverable; deleting it loses state).

### 3. Kanban dispatcher today

- **Core already has the dispatch LOGIC** but no trigger loop:
  - `POST /kanban/dispatch` route: `src/server/kanban.rs:122` →
    `dispatch_handler` at `src/server/kanban.rs:2285` — scans `todo` tasks in
    priority order, board gate (`crate::boards`), dependency gate, channel-busy
    gate, then creates the executor thread via
    `create_kanban_step_thread(...)` (`src/db/threads.rs:1503` wrapper).
- **The TRIGGER is external**: a cron schedule (tasks.yml `schedules:`) in
  action mode → `builtin_kanban_dispatcher` action
  (`/opt/workspace/omni-stack/config/actions.yml:25-27`,
  `tool_name: actions_kanban-dispatcher`) → the **actions plugin**
  (`plugins/tools/actions/`, mcp-server-actions) tool `kanban_dispatcher`
  (`plugins/tools/actions/src/main.rs:386`; handler at :93-131) → HTTP POST to
  core `/kanban/dispatch`.
  - ⚠️ On a FRESH stack the schedules are all commented out in tasks.yml → NO
    auto-dispatch at all (verified 2026-08-16). Moving the trigger into core
    with a default 15s loop fixes this permanently.
- **Actions plugin tools** (4): `kanban_dispatcher`, `hindsight_populator`,
  `relevance_indexer`, `setup_knowledge_pipeline` — registered in the `tools`
  vec at `plugins/tools/actions/src/main.rs:386-422`. The other 3 must stay.

## Requirements

### A. Cleanup: threads + kanban_history (+ 0 = disabled)

1. Keep the existing daily loop (`src/main.rs:277-302`) and its
   `delete_old_messages` / `delete_old_summaries` behavior.
2. Add a guard: `if delete_after_days == 0 { skip cleanup entirely }` (log a
   line like "cleanup disabled (delete_after_days=0)" once, then continue the
   loop sleeping).
3. Add `delete_old_threads(pool, before)` in `src/db/threads.rs` (or the
   `db::types` module — match the existing location of
   `delete_old_messages`/`delete_old_summaries`; grep which module `db::types`
   re-exports): delete messages → thread_subtasks → threads, only for
   terminal threads with `created_at < cutoff`, handling the `parent_id`
   self-ref (no FK violation, no orphans).
4. Add `delete_old_kanban_history(pool, before)` in the kanban db module
   (`src/db/kanban.rs` or wherever kanban_history queries live — grep first):
   `DELETE FROM kanban_history WHERE created_at < :cutoff`.
5. Wire both into the daily loop, log counts (`Deleted N threads older than X
   days`, same pattern as messages/summaries).
6. Update the settings description for `delete_after_days` in
   `src/server/settings.rs` to mention threads + history
   (e.g. "Days before old messages, summaries, threads and kanban history are
   deleted (0 disables)").
7. Non-goal: do NOT change the 86400s cadence, do NOT add a separate setting
   for threads vs messages, do NOT touch kanban_tasks rows (only history).

### B. Kanban dispatcher into core

1. **Refactor the dispatch logic out of the HTTP handler** so it is callable
   in-process: extract the body of `dispatch_handler`
   (`src/server/kanban.rs:2285`) into a reusable function
   (e.g. `pub async fn dispatch_todo_tasks(pool, data_dir) -> AppResult<DispatchSummary>`
   in `src/db/threads.rs` or a new `src/kanban_dispatch.rs`). The HTTP handler
   becomes a thin wrapper that calls it and formats the response — the
   existing response shape must stay compatible with the tests in
   omni-deployer `scripts/tests.py` (GROUP 22 etc. call
   `post_json("/kanban/dispatch", {})` directly — those must keep passing).
2. **Add a background loop in core** (`src/main.rs`, alongside the cleanup
   loop pattern at :277): every `kanban_dispatcher_interval` seconds call the
   in-process dispatch function directly (NO HTTP round-trip). Log dispatch
   results at info level (or debug when nothing dispatched — avoid spam every
   15s; e.g. log only when a task was actually dispatched or on error).
3. **New setting**: `kanban_dispatcher_interval` (seconds, default 15, 0 =
   disabled) — follow the existing `*_interval` naming (e.g.
   `messages_vectorization_interval`, `wiki_vectorization_interval`,
   `state_block_update_interval`). Add to:
   - `src/agent/config.rs` struct field + `get()` parse (both the main :234
     area and the env bootstrap :333 area) — field
     `pub kanban_dispatcher_interval_secs: u64` with default 15
     (name the yml key `kanban_dispatcher_interval` for consistency with the
     other `*_interval` keys that are in seconds).
   - `src/server/settings.rs`: the category key list (execution or general —
     pick the one matching `state_block_update_interval`'s category),
     `SettingMeta` entry, category mapping, serialization list.
   - `/opt/workspace/omni-stack/config/settings.yml`: add
     `kanban_dispatcher_interval: 15` in the same section.
   - ⚠️ If interval is 0 → loop sleeps forever (disabled), same guard pattern
     as cleanup.
4. **Remove the kanban_dispatcher from the actions plugin**:
   - Remove the `kanban_dispatcher` tool entry + `kanban_handler` from
     `plugins/tools/actions/src/main.rs` (keep hindsight_populator,
     relevance_indexer, setup_knowledge_pipeline).
   - Remove the `builtin_kanban_dispatcher` action from
     `/opt/workspace/omni-stack/config/actions.yml`.
   - Remove any commented-out dispatcher cron schedule in
     `/opt/workspace/omni-stack/config/tasks.yml` (it is replaced by the core
     loop; grep for `kanban-dispatcher` / `builtin_kanban_dispatcher` in
     tasks.yml/actions.yml and remove references).
   - ⚠️ Grep for other references to `builtin_kanban_dispatcher` /
     `actions_kanban-dispatcher` / `kanban_dispatcher` across the repo
     (docs, templates, plugin manifests) and update/remove them.
5. Keep `POST /kanban/dispatch` and `POST /kanban/tasks/{id}/redispatch` HTTP
   endpoints working (manual/testing path).

## Non-goals / DO NOT CHANGE

- Do NOT change the dispatch decision logic (board gate, dependency gate,
  channel-busy gate, priority ordering) — only relocate it into a reusable
  function and call it from a loop.
- Do NOT delete kanban_tasks rows in the cleanup (only kanban_history).
- Do NOT delete non-terminal threads.
- Do NOT change the other 3 actions plugin tools (hindsight_populator,
  relevance_indexer, setup_knowledge_pipeline).
- Do NOT change the 86400s cleanup cadence or add per-entity day settings.
- Do NOT touch db-migrations (no schema change: this is all DELETE logic +
  settings + code relocation).

## Verification gates

Run inside omnidev-omniagent-1 (cwd /app, PATH=/usr/local/cargo/bin:$PATH,
CARGO_HOME=/usr/local/cargo). The omnidev dev overlay sets SQLX_OFFLINE=false
— do NOT set SQLX_OFFLINE=true in the dev loop (CI-only); if queries changed,
run `cargo sqlx prepare --workspace` with DATABASE_URL set once at the end.

- `cargo check --workspace --all-targets` (clean).
- `cargo clippy --workspace --all-targets -- -D warnings` (clean).
- `cargo test --workspace --release` (baseline ~433+ passed / 0 failed; add
  unit tests for the 0=disabled guard, thread delete ordering, and any pure
  logic extracted).
- `cargo fmt --check` (clean).
- Grep audit: no remaining `kanban_dispatcher` tool in the actions plugin; no
  `builtin_kanban_dispatcher` references in actions.yml/tasks.yml; the
  in-process dispatch function is called from the loop; HTTP handler still
  wired.
- Live check (omnidev, isolated DB): set `delete_after_days: 0` → insert old
  rows → verify nothing deleted; set `delete_after_days: 1` (or a small value)
  → insert rows older than the cutoff → verify messages/threads (terminal
  only)/summaries/kanban_history deleted, non-terminal threads kept, no FK
  violation, no orphan parent_id. Set `kanban_dispatcher_interval: 5` (or 1)
  → create a todo task with no dependencies → verify it auto-dispatches within
  ~2x the interval WITHOUT any cron/action (core loop only) → verify
  `POST /kanban/dispatch` still works manually.
- omni-deployer integration tests (GROUP 22 + any dispatch tests in
  scripts/tests.py that call `/kanban/dispatch`) still pass.

## Deliverable

Commit + push to origin/main. Repos: omniagent (cleanup + dispatcher loop +
settings + actions plugin removal) + omni-stack (settings.yml +
actions.yml + tasks.yml cleanup). Report commit SHAs, the new setting names +
defaults, the live-check evidence (0-disabled guard, thread delete ordering,
auto-dispatch via core loop without cron, HTTP endpoint still working), and
the grep audit result. Do NOT claim done until all gates pass.
