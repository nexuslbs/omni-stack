# Dispatch Gate: No New Task While Channel Has Active Threads (Implementation)

**Status:** IMPLEMENTED 2026-08-14 (omniagent `4086d06` — dispatch gate: do not start a task when its channel has active threads)
**Date:** 2026-08-13
**Scope:** omniagent

## Goal

`POST /kanban/dispatch` must NOT start a new task's executor thread when the
task's target channel already has an **active** thread (queued or running).
This lets the full workflow (executor → tester → reviewer → done) of the
current task finish before the next task on the same channel begins.

## Why

Today the dispatcher picks the highest-priority eligible `todo` task and
creates its executor thread unconditionally — even if the channel already has
pending/processing threads from an in-flight task. The channel worker then
serializes by `created_at`, so a newly dispatched executor thread can run
BEFORE the previous task's reviewer/tester threads that were created earlier
in the same workflow → the workflow chains interleave and tasks re-verify
mid-flight state (observed 2026-08-13: thread 298 dispatched while 295/296/297
were queued, queueing the max_tokens task's executor behind unrelated steps).

## Verified facts (do not re-derive)

- `src/server/kanban.rs:2077` — `async fn dispatch_handler` (route `POST
  /kanban/dispatch` at `:122`).
- Candidate scan `:2079-2100`: `SELECT id, title FROM kanban_tasks WHERE
  status = 'todo' ORDER BY priority ASC, position ASC` → `DispatchTaskRow
  {id, title}` (`:1980-1984`) — **no `channel_id` in the scan row today**.
- Dependency eligibility loop `:2102-2159`; `first_eligible_index` `:2161`.
- Full task detail `:2172-2195` — `DispatchTaskDetailRow` SELECT includes
  `channel_id`.
- Channel resolution `:2197-2204` — `resolve_default_channel` with
  `default_kanban_channel` fallback.
- Thread creation `:2268-2312` (`create_thread_with_cause`, workflow_step
  "running"); task marked `running` at `:2316`.
- ⚠️ **The gate MUST be status-based, NOT `threads.terminal`.** On channel 4
  there are 13 `skipped` threads with `terminal=false` (left by the operator
  stop at 2026-08-13 20:07 — the stop handler's skip path didn't set
  `terminal=true`). A `WHERE terminal = false` gate would block dispatch
  FOREVER. Use `WHERE status IN ('pending','processing')` — those are the only
  states that represent queued/running work.

## Design direction (executor decides cleanest implementation)

- Add `channel_id` to the `DispatchTaskRow` scan query (the detail query
  already selects it), so the eligibility loop can gate per candidate.
- In the eligibility loop, after dependency check, skip any candidate whose
  channel has an active thread:
  `SELECT 1 FROM threads WHERE channel_id = :channel_id AND status IN
  ('pending','processing') LIMIT 1` (or a COUNT).
- Pick the FIRST candidate that is both dependency-eligible AND channel-free.
  If none: return `{"dispatched": false, "message": "Channel busy: <id> has N
  active thread(s)"}` — do NOT fall through and create a thread.
- Do not change the channel worker's serialization or step-thread creation
  (`kanban_updater.rs`) — only the dispatch entry point.

## Non-goals / DO NOT CHANGE

- Do NOT change the channel worker drain order, stop/close handlers, or
  step-thread creation in `kanban_updater.rs`.
- Do NOT use `threads.terminal` as the gate condition (see pitfall above).
- Do NOT change `create_thread_with_cause` or the task-status flip.
- The working tree contains SIBLING WIP from in-flight tasks (channels.yml,
  plan normalization, default channels, cron/hooks, channel_subscriptions,
  plugin restart, max_tokens). Commit ONLY your own files.
- Do NOT touch db-migrations (no schema change needed).

## Verification gates (bare canonical commands — omnidev container, project_dir /opt/workspace/omni-stack, env_file /opt/workspace/omni-deployer/omnidev.env, service omniagent)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  SQLX_OFFLINE=true in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- Live gate check: while a channel-4 thread is `processing`, call
  `POST /kanban/dispatch` → must return `dispatched: false` (channel busy)
  instead of creating a thread. Then verify no new `threads` row appeared.

## Deliverable

- Commit + push to origin/main: **omniagent**. Report the commit SHA.
