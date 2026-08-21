# Stop-thread must be surgical: never cancel the channel handler for another thread's sake (Implementation)

**Status:** IMPLEMENTED 2026-08-14 (omniagent `d096e30` — surgical stop-thread: never cancels another thread's handler; stopped kanban thread clears its task's thread_status)
**Date:** 2026-08-14
**Scope:** omniagent

## Goal

`POST /stop-thread/{thread_id}` must affect ONLY the target thread. It must
NOT cancel the channel's processing task when the currently-processing thread
is a different one. And when a stopped thread belongs to a kanban task, the
task's `thread_status` must be cleared (lose the `scheduled`/`running`
marker) — the task must not keep pointing at a thread that no longer exists.

## Why (verified live — incident 2026-08-14)

Stopping thread 420 (a `pending` thread of a wrongly-dispatched task) while
thread 412 (the dispatch-gate TESTER, `processing`) was actively running on
the same channel:

- `stop_thread_handler` step 5 (`src/server/mod.rs:486-497`) does
  `cancel_tokens.remove(&channel_id).cancel()` **unconditionally** — it never
  checks WHICH thread the handler is processing.
- `channel_handler` (`src/agent/mod.rs:270-291`) uses `tokio::select!` with
  `cancel.cancelled()` so cancellation is PROMPT: the currently-executing
  `process_thread` future (thread 412's agent loop, 98 iterations in) was
  dropped mid-flight.
- The supervisor respawns the handler (`Spawned channel handler for channel 4`
  at 20:35:08), but the respawned loop only claims `pending` threads
  (`find_pending_threads_by_channel`, `claim_thread` sets `processing`). Thread
  412 stayed `status='processing'` forever — orphaned, no owner, no
  terminal transition, no re-claim. Its task (`task_18cb82ac646e731e`) kept
  `thread_status='running'` pointing at a dead thread for 1h48m until manual
  recovery (skip + fresh tester thread 421).

Result: stopping one thread silently killed an unrelated in-flight thread and
left a false `processing`/`thread_status` state.

## Verified inventory (do not re-derive)

- `src/server/mod.rs:404-507` — `stop_thread_handler`:
  - `:409-435` — looks up the thread's `channel_id` + `task_id` (row struct
    `ThreadTaskRow`)
  - `:438-450` — `queries::skip_thread(&state.pool, thread_id)` (plain skip:
    no retry consumed, no re-run)
  - `:459-484` — `apply_stop_recovery` (Phase 6b: block the task)
  - `:486-497` — **THE BUG**: `tokens.remove(&channel_id)` → `token.cancel()`
    unconditionally; reports `handler_cancelled: true`
- `src/agent/mod.rs:270-291` — `channel_handler`: `tokio::select!` with
  `cancel.cancelled()` → prompt cancellation drops the in-flight
  `process_thread`; comment `:287-289` explicitly says "Don't skip pending
  threads here: stop_thread_handler already marked the specific thread as
  skipped before cancelling" — it assumes the target IS the active thread.
- `src/agent/mod.rs:331+` — `info!("Processing thread {} in channel {}")` —
  the handler processes threads one at a time per channel.
- `src/db/threads.rs:754` — `find_pending_threads_by_channel` (only
  `pending`); `:787` — `claim_thread` (pending → processing);
  `:959` — `skip_thread` (`WHERE status IN ('pending','processing')` → sets
  `skipped`, terminal=true).
- `src/server/mod.rs:259-298` — `apply_stop_recovery`:
  `queries::stop_thread_recovery(task.status, task.thread_status)` →
  `StopRecovery::Block` → `transition_with_comment(pool, task_id, "blocked",
  None, comment)` — passes `None` for thread_status which NULLs it
  (`NULLIF(:thread_status,'')` in `kanban_updater.rs:349`). BUT the
  `clear_thread_status` flag in the `StopRecovery::Block` enum
  (`src/db/threads.rs:202-212`, `:223-238`) is IGNORED — the match uses
  `Block { .. }` (`mod.rs:286`) and never reads the flag, so Block ALWAYS
  clears thread_status, and the Noop branch (`:296`) NEVER clears it.
- `src/server/mod.rs:305-401` — `stop_handler` (channel-wide `/stop`) and
  `:514+` — `close_handler` legitimately cancel the whole channel (they stop
  ALL threads); do NOT change them.
- `src/main.rs:215-222` — `cancel_tokens: HashMap<String, CancellationToken>`
  keyed by channel_id only — NO per-thread tracking exists.

## Design (executor picks cleanest implementation)

### 1. Only cancel the handler when the target is the active thread

In `stop_thread_handler`, decide cancellation by the target's status AFTER the
skip:

- Read the thread's status in step 1 (`ThreadTaskRow` — add `status` to the
  SELECT). After `skip_thread`, decide:
  - Target was `processing` → the handler IS processing it (one thread at a
    time per channel) → cancelling the handler is correct and necessary (the
    in-flight loop must stop so the supervisor respawns and continues with
    remaining `pending` threads). Keep the current cancel.
  - Target was `pending` (or anything else) → the handler is processing a
    DIFFERENT thread (or idle) → **do NOT cancel the handler**. The skip alone
    is enough: `find_pending_threads_by_channel` will simply not return the
    skipped thread, and the other thread keeps running untouched. Set
    `handler_cancelled: false`.
- Race note: `skip_thread` sets `skipped` + terminal BEFORE the decision, so
  the handler can no longer claim the target (`claim_thread` requires
  `status='pending' AND NOT terminal`). The check is therefore race-free.

### 2. Always clear the stopped thread's task thread_status

When a stopped thread belongs to a kanban task, the task's `thread_status`
must be cleared regardless of Block/Noop outcome (the task must not point at
a thread that is being stopped):

- In `apply_stop_recovery`, honor the `clear_thread_status` flag on
  `StopRecovery::Block` (stop ignoring it with `Block { .. }`), and ALSO clear
  `thread_status` in the Noop branch when the task currently has one set —
  i.e. after the decision, if the thread is kanban-linked, run
  `UPDATE kanban_tasks SET thread_status = NULL WHERE id = :task_id AND
  thread_status IS NOT NULL` (or pass the cleared value through
  `transition_with_comment` where it already handles NULLIF). The task status
  itself stays untouched in the Noop case (e.g. a `todo`/`backlog` task whose
  thread_status was `scheduled` must lose the marker but keep its column).
- User requirement (verbatim): "the stopped thread, if part of a Kanban task,
  should lose the processing thread_status."

### 3. Defense in depth — no orphaned `processing` threads

If a handler IS cancelled (legitimately, target was `processing`), the target
is already skipped — fine. But add a safety net so a `processing` thread can
never be left ownerless: in `channel_handler`'s cancellation branch
(`:277-290`), before `break`, skip any thread the handler was actively
processing if it is still `processing` (idempotent `skip_thread` on the
current thread id — no-op when already terminal). This guarantees the
invariant "every `processing` thread has a live owner" even under races
(and aligns with the sibling terminal-status-invariant task
`task_18cb83096b238872`'s single-choke-point rule: use `skip_thread`, do not
write a second skip path).

## Non-goals / DO NOT CHANGE

- Do NOT change `stop_handler` (`/stop`) or `close_handler` (`/close`) — they
  are channel-wide stops and legitimately cancel the handler.
- Do NOT add a schema change or migration — `thread_status` already exists.
- Do NOT change the channel worker's `pending` claim order or
  `process_thread`.
- Do NOT change `stop_thread_recovery`'s Block/Noop decision table — only
  honor its `clear_thread_status` flag and clear on Noop-when-set.
- The working tree contains SIBLING WIP (channels.yml, plan normalization,
  default channels, cron/hooks, plugin restart, max_tokens, dispatch gate,
  terminal-status invariant, cache-friendly compaction, LLM transport,
  status-change dispatch). Commit ONLY your own files.

## Verification gates (bare canonical commands — omnidev container, project_dir /opt/workspace/omni-stack, env_file /opt/workspace/omni-deployer/omnidev.env, service omniagent)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  SQLX_OFFLINE=true in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- Unit tests: stop-thread on a `pending` thread while ANOTHER thread is
  `processing` on the same channel → `handler_cancelled: false`, the
  processing thread's status unchanged, target skipped; stop-thread on the
  `processing` thread → `handler_cancelled: true`, target skipped, handler
  respawns and continues remaining pending threads.
- Unit tests: stopped kanban-linked thread → `kanban_tasks.thread_status`
  becomes NULL in BOTH Block and Noop outcomes; task status preserved in the
  Noop case.
- Live: create two threads on the same channel (one `pending`, one
  `processing`), stop the `pending` one → the `processing` one must keep
  running to completion (its message count keeps growing). Then stop the
  `processing` one → `handler_cancelled: true`, no thread is left in
  `status='processing'` without a handler after the respawn.

## Deliverable

- Commit + push to origin/main: **omniagent** (code). Report the commit SHA.
