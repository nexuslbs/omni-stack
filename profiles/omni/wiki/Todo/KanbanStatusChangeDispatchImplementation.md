# Kanban Status-Change Dispatch + `/redispatch` (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-14
**Scope:** omniagent (core + actions MCP plugin), omni-stack (workflows.yml untouched)

## Goal

Dispatch a kanban task when its STATUS is changed, instead of only via the
explicit dispatcher. Moving a task to a status that maps to a workflow role it
has starts that role's thread. A new `/redispatch` endpoint re-creates the
thread for a task already in `running`/`testing`/`review` without changing its
status. Startup recovery is unified with the same redispatch code.

## Why (verified)

- Today `PATCH /kanban/tasks/{id}/status` (`change_status_handler`,
  `src/server/kanban.rs:713`) is a PURE column move — it shifts positions,
  writes history, and does NOTHING else. Moving a task to `running` by hand
  leaves it stranded: no thread is created until the every-minute
  `POST /kanban/dispatch` cron happens to pick it (and that only picks
  `todo` tasks). Moving a task to `testing`/`review` by hand NEVER creates
  the tester/reviewer thread — the only path that creates those is the
  in-workflow `route_completed_thread` transition in `kanban_updater.rs`.
- `POST /kanban/dispatch` (`dispatch_handler`, `src/server/kanban.rs:2077`)
  picks the first eligible `todo` task, creates the executor thread
  (`workflow_step "running"`), and marks the task `running` (`:2316`). It is
  called every minute by the `builtin_kanban_dispatcher` action
  (`omni-stack/config/actions.yml:12` → `plugins/tools/actions/src/main.rs:93`
  `handle_kanban_dispatcher`, which just forwards
  `POST /kanban/dispatch`).
- Thread statuses: `pending`/`processing` = active work; terminal =
  `skipped`/`completed`/`failed`/`interrupted`/`system`. A task can have
  multiple threads (each workflow step). When the operator manually moves a
  task, any still-active threads for it keep running and can race the new
  step — they must be skipped first.
- `kanban_tasks.thread_status` is the "task goes to scheduled" marker: when a
  thread is created for a task it is set to `'scheduled'` (see
  `src/db/threads.rs:402,929,1098`). The startup recovery
  (`skip_all_pending_threads`, `src/db/threads.rs:1003`) already re-schedules
  kanban-linked pending/processing threads this way (fresh thread,
  `thread_status='scheduled'`, task status unchanged, no retry consumed) — but
  only when the thread ITSELF is pending/processing, and the decision logic
  (`skip_recovery` `:168`) is separate from any task-level redispatch.

## Design (executor picks cleanest implementation)

### 1. Shared dispatch-on-status function

Extract ONE function (e.g. `dispatch_task_for_status(pool, data_dir, task_id,
new_status) -> AppResult<Option<i64>>` returning the created thread id, or
`None` when nothing should run) used by ALL call sites below. It must:

1. **Skip stale threads first**: `UPDATE threads SET status='skipped',
   ended_at=NOW(), terminal=true, iterations = COALESCE((SELECT
   MAX(iteration_number) FROM messages WHERE thread_id = threads.id),0)
   WHERE task_id = :task_id AND status IN ('pending','processing')` — mirror
   the existing skip shape at `src/db/threads.rs:961`. Record a
   `kanban_history` comment per skipped thread if practical (the existing
   re-schedule paths do).
2. **Resolve the role for the target status**: `running` → `"executor"`,
   `testing` → `"tester"`, `review` → `"reviewer"` (same mapping as
   `kanban_updater.rs:383-388` `resolve_step_identity`). Load the task's
   `workflow_id` → `load_workflows_file` → `workflow.resolve_role(role)`.
   - `running` with NO workflow: still run — use the plain executor path
     (template from task/channel via `resolve_dispatch_template`, like
     `dispatch_handler` `:2258-2266`).
   - `testing`/`review` with NO workflow OR without that role in the
     workflow: NO-OP (return `None`). There is no role to run.
3. **Create the thread** with the role's identity (profile/provider/model/plan/
   template — reuse `resolve_step_identity` in `kanban_updater.rs:374` or the
   dispatch_handler resolution `:2232-2266`), `workflow_step = new_status`,
   `task_id`, msg_type `kanban`, and the role's template. On success set
   `kanban_tasks.thread_status = 'scheduled'`.
4. **Do NOT change task status** — the caller owns the status transition.

### 2. `change_status_handler` dispatches

After the existing column-move + history write (`kanban.rs:824-854`), if the
status ACTUALLY changed, call `dispatch_task_for_status(..., body.status)`.
Moving a task to `running` starts the executor; to `testing` starts the tester
(if the workflow has one); to `review` starts the reviewer (if it has one).
The task stays in its new column; `thread_status='scheduled'` marks it as
queued for the agent loop.

### 3. Dispatcher action simplifies to "move to running"

`POST /kanban/dispatch` (`dispatch_handler`) KEEPS its eligibility logic
(deps satisfied, channel gate) but its final act changes from
create-thread + mark-running (`:2268-2331`) to: **move the picked task to
`running` via the shared status-change path** — i.e. call
`dispatch_task_for_status` on it (or PATCH-status through the same code).
The thread creation now lives ONLY in `dispatch_task_for_status`; no duplicate
thread-creation code. The `builtin_kanban_dispatcher` action and its cron
keep working unchanged (it still just calls `POST /kanban/dispatch`).

### 4. NEW `POST /kanban/tasks/{id}/redispatch`

Route: `/kanban/tasks/{id}/redispatch` (register next to the other task
routes in `kanban.rs` ~`:122`). Handler logic:

1. Load the task; 404 if missing.
2. **Ignore (no-op success) unless** `status ∈ {running, testing, review}`.
   Non-workflow tasks: only act in `running`. Workflow tasks: `running`
   always; `testing` only if the workflow has a `tester` role; `review` only
   if it has a `reviewer` role. (Same role-resolution as the shared function;
   if the role wouldn't run on a fresh move to that status, redispatch is
   also a no-op.)
3. **If the task already has a non-terminal thread** (`SELECT 1 FROM threads
   WHERE task_id = :id AND status IN ('pending','processing') LIMIT 1`) →
   no-op (return `{"redispatch": false, "reason": "already active"}`). Do NOT
   skip it — redispatch is for tasks that are NOT actually running.
4. Otherwise create the role thread for the task's CURRENT status (same as
   step 1/3 of the shared function, but WITHOUT skipping stale threads and
   WITHOUT changing `kanban_tasks.status`) and set
   `thread_status='scheduled'`. Return `{"redispatch": true, "thread_id": N}`.

Example: a task stuck in `running` whose executor thread died/failed without a
terminal transition → `/redispatch` creates a fresh executor thread in the
channel, the agent loop picks it up, and the task runs again.

### 5. Startup redispatch unified

At startup (`main.rs:200` `skip_on_startup` / `skip_all_pending_threads`),
replace the kanban re-schedule branch with a call to the SAME redispatch
logic: for every task in `running`/`testing`/`review` (not just those with a
pending/processing thread), if it has no active thread, redispatch it. This
replaces the separate `skip_recovery`/`skip_all_pending_threads` re-schedule
path with the unified code. Keep the existing safeguards: no retry consumed,
task status never moved back to `todo`, blocked/done tasks untouched.

## Verified inventory (do not re-derive)

- `src/server/kanban.rs:47` — `VALID_STATUSES = ["backlog","todo","running","testing","review","blocked","done"]`
- `src/server/kanban.rs:713-857` — `change_status_handler`: position shift +
  status UPDATE + history; NO dispatch today
- `src/server/kanban.rs:2077-2332` — `dispatch_handler`: todo scan
  (`:2079-2100`), deps (`:2102-2159`), `first_eligible_index` (`:2161`),
  detail load (`:2172-2195`), channel resolve (`:2197-2204`), role/template
  resolve (`:2228-2266`), thread create (`:2268-2312`), mark running
  (`:2316`); returns `{dispatched, task_id, thread_id}`
- `src/server/kanban.rs:122` — `.route("/kanban/dispatch", post(dispatch_handler))`
- `src/agent/kanban_updater.rs:311-327` — `route_completed_thread` (the ONLY
  current creator of tester/reviewer threads, via in-workflow completion)
- `src/agent/kanban_updater.rs:374-430` — `resolve_step_identity`: step→role
  map (`running`→executor, `testing`→tester, `review`→reviewer), role config
  load from workflows.yml, profile/provider/model/plan/template resolution
- `src/workflows.rs:264` — `resolve_role(role_key) -> Option<...>`: None when
  the role is not defined on the workflow
- `src/db/threads.rs:961` — skip shape: `UPDATE threads SET status='skipped',
  ended_at=NOW(), terminal=true, iterations=... WHERE id=:id AND status IN
  ('pending','processing')`
- `src/db/threads.rs:1003-1110` — `skip_all_pending_threads` startup
  recovery: skips pending/processing; kanban-linked re-schedule (fresh
  thread, `thread_status='scheduled'`, status unchanged, no retry)
- `src/db/threads.rs:168-177` — `skip_recovery` decision (blocked/done → Noop,
  else Reschedule)
- `src/db/kanban.rs:12` — `update_kanban_task_status` (transactional status
  flip + history)
- `plugins/tools/actions/src/main.rs:93-126` — `handle_kanban_dispatcher`
  (forwards `POST /kanban/dispatch`; thin, no logic to change)
- `omni-stack/config/actions.yml:12-17` — `builtin_kanban_dispatcher` action
  (unchanged)
- `src/main.rs:200-208` — startup `skip_on_startup` call

## Non-goals / DO NOT CHANGE

- Do NOT change `route_completed_thread` or the in-workflow
  executor→tester→reviewer auto-advance — that path already creates step
  threads correctly and must keep working unchanged.
- Do NOT change the channel worker drain order, stop/close handlers, or
  `stop_thread_recovery` (explicit operator stop still BLOCKS the task).
- Do NOT change `builtin_kanban_dispatcher`/cron wiring or
  `format_dispatch_summary` — the action keeps calling
  `POST /kanban/dispatch`; only the core's final act changes.
- Do NOT add a schema change or migration — `thread_status` already exists.
- Do NOT move tasks back to `todo` anywhere; redispatch preserves status.
- The working tree contains SIBLING WIP (channels.yml, plan normalization,
  default channels, cron/hooks, plugin restart, max_tokens, dispatch gate,
  terminal-status invariant, cache-friendly compaction, LLM transport).
  Commit ONLY your own files.

## Verification gates (bare canonical commands — omnidev container, project_dir /opt/workspace/omni-stack, env_file /opt/workspace/omni-deployer/omnidev.env, service omniagent)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  SQLX_OFFLINE=true in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- Unit tests for `dispatch_task_for_status` role resolution: running w/o
  workflow → executor thread; testing w/o tester role → None; review w/o
  reviewer role → None; stale pending/processing threads skipped first.
- Unit tests for `/redispatch` gating: backlog/todo/done/blocked → no-op;
  `testing` non-workflow → no-op; `testing` w/o tester → no-op; active thread
  present → no-op; `running` w/o active thread → new thread, status unchanged.
- Live: PATCH a test task to `running` → executor thread appears
  (`threads` row with `task_id`, `workflow_step='running'`,
  `kanban_tasks.thread_status='scheduled'`); PATCH to `testing` → tester
  thread (omniagent-dev has tester); PATCH to `review` → reviewer thread.
- Live: `POST /kanban/tasks/{id}/redispatch` on the running task → either
  no-op (thread active) or new thread (if none), status unchanged.

## Cross-task coordination (do not duplicate)

Sibling task `task_18cb83096b238872` (Terminal status invariant, also todo)
mandates a SINGLE choke point for flipping threads to terminal status, with
`terminal=true` always set. If that choke point exists when this task runs,
route the stale-thread skip through it instead of writing a second skip path.
If it does not exist yet, the skip MUST set `terminal=true` (the
`threads.rs:961` shape) so this task never reintroduces the
skipped-with-terminal=false bug the invariant task is fixing.

## Deliverable

- Commit + push to origin/main: **omniagent** (core + actions plugin, if the
  plugin needs changes) + **omni-stack** (wiki spec/index/log). Report commit
  SHAs.
