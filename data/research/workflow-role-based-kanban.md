# omniagent "workflow" Feature — Role-Based Kanban Flow (Executor / Tester / Reviewer) — v2

**Status:** Research (design proposal, not yet implemented)
**Date:** 2025 (research thread; v2 incorporates user design decisions D1–D6)
**Source of truth:** omniagent repo at `/opt/workspace/omniagent` (read in-thread for v1), live DB
(`kanban_tasks`/`threads`/`kanban_history`/`kanban_task_dependencies`), dashboard at
`/opt/workspace/omni-dashboard`. Facts marked [VERIFIED] were read from source in the v1 thread;
facts marked [PRE-VERIFIED] were supplied and reused. **v2 reuses all v1 facts** — the user design
decisions below change the *target design*, not the verified current-system facts (§2), so no
sources were re-read.

**v2 changelog (user design decisions applied):**
- **D1** — Retries are the ONLY cap: no separate "max threads per task" cap. Retries apply to ANY
  re-entry of a step (failure rerun, interruption rerun, reviewer rework/retest, tester rework/fail),
  stored as *retries remaining* per step; a **pre-start guard** checks the counter before sending the
  task to a step again and sends it straight to `blocked` (without starting the step) when exhausted.
- **D2** — No extra escape hatch for reviewer loops: retries are the only loop protection (the guard
  in D1 makes every reviewer→todo rework consume an executor retry).
- **D3** — Optional `comment` param on every status change (API + MCP + reviewer/tester tools),
  persisted in a new `kanban_history.comment` column.
- **D4** — New `run_status` field (NULL | 'scheduled' | 'running') on `kanban_tasks`; the `ready`
  status is dropped. Executor/test/review are three task statuses that behave identically;
  `run_status` distinguishes "step thread created, seq-0 written" from "loop picked it up".
- **D5** — Tester fails the task on ANY single test error; new BUILT-IN tool `kanban_fail_task
  (task_id?, comment?)` is the explicit failure signal; tester decisions: rework/fail → executor,
  interruption → rerun same step. Retries always consumed when running again.
- **D6** — Reviewer ALWAYS verifies the work including tests; 4-way decision: rework (→executor),
  retest (→tester), approve (→done), block (→blocked).

---

## 1. Executive Summary

The user wants a "workflow" mode on top of the existing kanban task pipeline: the current
single-actor flow (dispatcher → executor thread → `review` → manual `done`) becomes an
optional **3-role pipeline** — **executor** (required), **tester** (optional), **reviewer**
(optional) — with **per-step retry counts** (default 0). When no workflow config is present,
behavior must be byte-for-byte identical to today.

Key design choices (v2):

1. **Config lives in a `workflow_config` JSONB column on `kanban_tasks`** (roles, per-role
   retries, optional per-role channel/profile); **live run state in a `workflow_state` JSONB
   column** carrying **retries-remaining counters** per step (D1); **`run_status` column**
   (NULL/'scheduled'/'running') replaces the `ready` status (D4); **`comment` column on
   `kanban_history`** (D3). All additive, no new tables.
2. **Retries are the ONLY cap (D1).** There is NO "total threads per task" cap — retries bound
   everything. A step's retry budget is consumed on **any re-entry** of that step, not only on
   explicit failures: failure reruns, interruption reruns, reviewer `rework` (→executor),
   reviewer `retest` (→tester), tester `rework`/`fail` (→executor) all consume a retry of the
   step being re-entered. **Guard:** before the workflow sends the task to a step again it checks
   the retry counter FIRST; if the limit is already reached the task does **not even start** that
   step — it goes directly to `blocked`. No additional loop protection is proposed (D2): the
   retry budget is the single mechanism that prevents infinite reviewer→todo loops.
3. **`ready` is dropped (D4).** Dispatch sets task status `running` + `run_status='scheduled'`
   (thread created, seq-0 message written); the channel loop flips `run_status → 'running'` when
   it actually picks the thread up. The flow is uniform across the three modes:
   `todo → running → test → review → done|blocked`, each step-status with the same
   scheduled→running `run_status` lifecycle. Legacy rows keep `run_status NULL`, treated as
   `'running'`.
4. **New status `test`** added to all status validation lists (enum is open — statuses are plain
   strings everywhere). `ready` removed from all lists (with a data migration, §11).
5. **Each step is one thread** (the existing thread machinery is reused): test/review threads are
   created by a new **workflow engine** hook at thread-completion time, chained via the existing
   `threads.parent_id` column, carrying a new `threads.kanban_step` marker. Executor re-entries
   (failure reruns, reviewer/tester send-backs) go back through `todo` → the existing dispatcher.
6. **Explicit failure tool (D5):** a BUILT-IN agent tool `kanban_fail_task(task_id?, comment?)`
   lets any role (primarily the tester) declare the current thread/task failed instead of relying
   only on the last-tool-result heuristic. Tester step fails the task if **even one** test error
   occurs. Tester outcomes: pass → review; rework/fail → back to executor (`todo`); interruption →
   rerun the same step. Retries are always consumed when running again (D1).
7. **Reviewer always verifies the work including tests (D6)** with a 4-way decision —
   `rework` (→executor), `retest` (→tester), `approve` (→done), `block` (→blocked) — captured by
   a new MCP tool + API endpoint, with optional comment (D3).
8. **Dependencies**: a task in `test` does **not** satisfy dependents (keep `IN ('review','done')`);
   `test` is treated like `running` for dependency purposes.
9. **Backward compat**: empty `workflow_config` (`{}`) ⇒ exactly today's behavior
   (executor-only → `review` → manual/API `done`); `run_status` NULL treated as `'running'`;
   existing `ready` tasks migrate to `running` + `run_status='scheduled'`.

---

## 2. Current System — Verified Facts

### 2.1 Status model [VERIFIED]
- **Kanban MCP plugin** `plugins/tools/kanban/src/main.rs`:
  `valid_statuses = ["backlog","todo","ready","running","review","done","blocked"]`
  (used in both create and update handlers). **No `test` status.**
- **HTTP API** `src/server/kanban.rs`:
  `const VALID_STATUSES: &[&str] = &["backlog","todo","ready","running","review","blocked","done"]`.
- **Dashboard** `omni-dashboard/src/lib/kanban-board.ts`: `KANBAN_COLUMNS` (7 columns:
  backlog, todo, ready, running, review, blocked, done) + `STATUS_LABELS` + `columnColorClass` +
  `statusBadge`; `kanban-detail.ts` renders "Move to" buttons and the edit-modal status select
  **from `STATUS_LABELS`**.
- *Target-design note (D4):* `ready` is removed and `test` added in v2 ⇒ validation lists become
  `["backlog","todo","running","test","review","blocked","done"]` (still 7 entries; §4.1, §10).

### 2.2 Dispatcher (todo → ready) [VERIFIED + PRE-VERIFIED]
`plugins/tools/actions/src/main.rs` `handle_kanban_dispatcher`:
- Queries `kanban_tasks WHERE status='todo' ORDER BY priority, position`.
- Dependency gate: task eligible when **no deps OR all deps `status IN ('review','done')`**
  (deleting/archiving a dep also disables the dep row).
- On dispatch: creates thread (`status 'created' → 'pending'`), writes seq-0 cause message
  (`msg_type='kanban'`, `msg_subtype=task_id`), sets task status `'ready'`, inserts
  `kanban_history` (`action='moved'`, `todo → ready`).
- If channel closed: thread → `'skipped'`, task back to `'todo'`.
- Provider/model resolution chain: channel → config → default (`openai/gpt-4o`).
- *Target-design note (D4):* the dispatcher keeps owning **only** `todo → running`; it now sets
  status `'running'` + `run_status='scheduled'` (no `ready`).

### 2.3 Thread → task status on completion [PRE-VERIFIED; file `src/agent/kanban_updater.rs`]
`update_kanban_status(cfg, thread, final_status, stats)` — only when `thread.task_id` is set:
- `final_status == "completed"` **and** last tool-result message had `metadata.is_error = true`
  → task `blocked`.
- `final_status == "completed"` (no error) → task `review`.
- any other terminal (`failed`, `interrupted`, `skipped`, …) → task `blocked`.
- (Call site: thread terminal-finalization path in the agent — `main_loop.rs`/`executor.rs`;
  exact helper line to confirm at implementation. The dispatcher sets `todo → ready`; the
  `ready → running` transition is driven by thread start — existing behavior, not in the dispatcher.)
- *Target-design note:* v2 replaces this logic with the workflow engine's decision (§7.2), which
  also honors the explicit fail tool (D5) and the retry guard (D1). The no-workflow path is
  preserved verbatim.

### 2.4 Channel-skip / delete recovery [VERIFIED — `src/db/threads.rs`]
`delete_channel` (and the startup skip path): threads of the channel are marked `skipped`
and their tasks recovered:
- threads `status='pending'` with task `status='ready'` → task back to `'todo'`.
- threads `status='running'` → task `'blocked'`.
This logic is **not step-aware** today — it must become workflow-aware (see §6.4).

### 2.5 Schema (live DB + `db-migrations/src/lib.rs`) [VERIFIED]
- `kanban_tasks`: `id, title, body, status, priority, position, assignee, channel_id, profile,
  archived, template, planning_mode, created_at, updated_at, plan`. **No workflow columns.**
- `threads`: `id, status, cause, channel_id, profile, provider, model, terminal, task_id,
  schedule_task_id, planning_mode, parent_id, iterations, plan, …`. `task_id` links thread→task;
  **`parent_id` exists** (thread chaining already supported).
- `kanban_history`: `id, kanban_task_id, action, initial_board, final_board, previous_values,
  created_at`. **No `comment` column.**
- `kanban_task_dependencies`: dep pairs (satisfied per §2.2).
- Migration style: **declarative single-phase** — `CREATE TABLE IF NOT EXISTS` + idempotent
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (+ backfill UPDATEs). New columns must follow this
  pattern; no versioned migration runner.
- Live DB: exactly 1 kanban task exists (status `running`); no `test` status anywhere.

### 2.6 API surface [VERIFIED — `src/server/kanban.rs`, 13 routes]
`GET /kanban/tasks`, `GET /kanban/tasks/{id}`, `GET /kanban/tasks/{id}/dependencies`,
`POST /kanban/tasks`, `PATCH /kanban/tasks/{id}/status`, `PATCH /kanban/tasks/{id}/position`,
`PATCH /kanban/tasks/{id}`, `DELETE /kanban/tasks/{id}`, `GET /kanban/tasks/{id}/threads`,
`POST|DELETE …/dependencies`, `GET /kanban/tasks/{id}/history`, `GET /kanban/history`,
`GET /kanban/tasks/{id}/subtasks`. KanbanTaskRow exposes `workflow`-less fields only.
MCP tools: `kanban_create_task`, `kanban_list_tasks`, `kanban_update_task`,
`kanban_delete_task` (+ dispatcher tool).

### 2.7 Concurrency model [PRE-VERIFIED]
Threads execute **per-channel serially** (one active thread per channel; different channels
run in parallel). Roles can share a channel (serial chain) or use separate channels
(parallel across channels).

---

## 3. Feature Spec (User Intent, v2)

- **Executor (required)**: existing main execution — `todo → running (thread)`.
- **Tester (optional)**: when defined, after executor success → **new status `test`**; a test
  thread runs; the tester **fails the task on ANY single test error** (D5); success → `review`.
- **Reviewer (optional)**: when defined, in `review` a reviewer thread runs and the reviewer
  **always verifies the work including tests** (D6) and **decides**: `rework` (→executor) |
  `retest` (→tester) | `approve` (→done) | `block` (→blocked).
- **`run_status` (D4)**: every step-status (`running`/`test`/`review`) uses
  `run_status='scheduled'` once its thread is created (seq-0 written) and `run_status='running'`
  once the loop picks the thread up. The `ready` status no longer exists.
- **Retries = the only cap (D1)**: each step (main/test/review) has a retry budget, **default 0**
  (= 1 try). ANY re-entry of a step — failure rerun, interruption rerun, reviewer
  `rework`/`retest`, tester `rework`/`fail` — consumes one retry of the step being re-entered.
  A **pre-start guard** checks the counter first: if exhausted, the task goes directly to
  `blocked` and the step is never started. No separate thread cap; no extra loop protection (D2).
- **Failure (D5)**: non-successful terminal thread state, an explicit `kanban_fail_task` call, or
  (for the tester) a single test error → the failure path (§7.2); a tester failure sends the task
  back to the executor, consuming an executor retry.
- **Comments (D3)**: every status transition (API, MCP tools, reviewer/tester decision tools,
  engine transitions) accepts an optional `comment` stored in `kanban_history.comment`.

---

## 4. Status Machine & Transition Table

### 4.1 Statuses (7 total) + run_status

Statuses: `backlog, todo, running, test, review, done, blocked` — `ready` **removed** (D4),
`test` added. Same cardinality as today.

Semantics:
- `running` = executor step in flight. `run_status='scheduled'` = dispatcher created the executor
  thread (seq-0 cause message written), pending pick-up; `run_status='running'` = channel loop
  picked it up and iterations are running.
- `test` = test step in flight (`run_status` same lifecycle).
- `review` = (a) awaiting **manual**/API done (no reviewer defined — today's behavior), or
  (b) reviewer step in flight (`run_status` same lifecycle).
- `blocked` = terminal failure, retries exhausted (guard hit), or reviewer/tester rejection.
- `done` = approved or manual.

`run_status` (kanban_tasks): `NULL | 'scheduled' | 'running'` (D4).
- `'scheduled'` — a step thread was just created for the step (seq-0 message written).
- `'running'` — the omniagent loop has actually picked up the thread and started iterations.
- `NULL` — no step thread in flight (task in backlog/todo/done/blocked, or manual review with no
  reviewer). For **legacy rows** NULL is treated as `'running'` (pre-D4 semantics, §11).
- Lifecycle: set `'scheduled'` on thread creation (dispatcher for executor, engine for test/review),
  flipped to `'running'` by thread start, reset to `NULL` when the task leaves the step status.

### 4.2 Transition table (authoritative, v2)

| # | From | To | Trigger (who) | Condition / notes |
|---|------|----|---------------|-------------------|
| 1 | backlog | todo | API / MCP tool (manual) | existing; optional `comment` (D3) |
| 2 | todo | running | **dispatcher** (actions plugin, cron) | deps satisfied (`no deps ∨ all IN ('review','done')`); creates executor thread + seq-0 cause msg; sets `run_status='scheduled'`; history `action='moved'` + optional comment |
| 3 | running | running | thread start (channel loop) | **`run_status`: 'scheduled' → 'running'** (task status unchanged — D4) |
| 4 | running | test | **workflow engine** at executor-thread completion | success (`completed`, no tool error, no fail call) **and** `workflow_config.tester` defined; engine creates test thread (`kanban_step='test'`, parent=executor thread); status `test`, `run_status='scheduled'` |
| 5 | running | review | **workflow engine** | success and **no** tester defined; if reviewer defined → create review thread, status `review`, `run_status='scheduled'`; else status `review`, `run_status=NULL` (manual path — existing behavior) |
| 6 | running | todo | **workflow engine** (retry path) | executor failure/interruption; **guard (D1):** executor `retries_remaining > 0` → decrement, status `todo` (`run_status=NULL`); dispatcher re-dispatches (#2). If guard fails (0 left) → **#7 directly — step never starts** |
| 7 | running | blocked | **workflow engine** | executor failure/interruption + executor retries exhausted (guard hit); history reason `retries_exhausted` (+ comment) |
| 8 | test | test | thread start (channel loop) | `run_status`: 'scheduled' → 'running' |
| 9 | test | review | **workflow engine** at test-thread completion | success (no test errors, no fail call); if reviewer defined → create review thread (`kanban_step='review'`), status `review`, `run_status='scheduled'`; else status `review`, `run_status=NULL` (manual) |
| 10 | test | test | **workflow engine** (retry path) | test thread interruption / infra failure (NOT a test error — see #12); **guard (D1):** tester `retries_remaining > 0` → decrement, new test thread, `run_status='scheduled'`. Guard fail → **#11** |
| 11 | test | blocked | **workflow engine** | interruption + tester retries exhausted (guard hit) |
| 12 | test | todo | **tester decision** (D5) | ANY single test error, OR explicit `kanban_fail_task`, OR tester `rework` → task fails → back to the beginning (executor); **guard (D1):** executor `retries_remaining > 0` → decrement, status `todo` (`run_status=NULL`); guard fail → **blocked directly** |
| 13 | review | review | thread start (channel loop) | `run_status`: 'scheduled' → 'running' |
| 14 | review | done | **reviewer decision** `approve` or manual/API | tool validates task is in `review` (+ reviewer-step thread check when reviewer configured); optional comment |
| 15 | review | todo | reviewer decision `rework` (D6) | implementation not done correctly; **guard (D1):** executor `retries_remaining > 0` → decrement, status `todo`; guard fail → **blocked directly** (this is the reviewer-loop bound — D2, no extra escape hatch) |
| 16 | review | test | reviewer decision `retest` (D6) | some test failed but the thread passed, or tests wrong/not comprehensive; **requires tester defined** (else reject — §13 Q1); **guard (D1):** tester `retries_remaining > 0` → decrement, engine creates new test thread, status `test`, `run_status='scheduled'`; guard fail → **blocked directly** |
| 17 | review | blocked | reviewer decision `block` | tool/API; optional comment |
| 18 | review | review | **workflow engine** (retry path) | review thread failed/interrupted (or its decision tool errored); **guard (D1):** reviewer `retries_remaining > 0` → decrement, new review thread, `run_status='scheduled'`; guard fail → **#19** |
| 19 | review | blocked | **workflow engine** | review thread failed + reviewer retries exhausted (guard hit) |
| 20 | blocked | todo | API / MCP tool (manual unblock) | existing; optional comment |
| 21 | any | done/blocked | API / MCP tool (manual override) | existing; manual moves stay legal at all times; optional comment |

Rules that keep the machine safe:
- **Only one active transition per status**: `running`, `test`, `review` are "in-flight" states
  with exactly one owning thread at a time (the engine never spawns a step thread while the
  current step thread is non-terminal).
- **Pre-start retry guard (D1)**: on every re-entry (#6, #10, #12, #15, #16, #18) the engine
  checks the target step's `retries_remaining` FIRST. If it is 0, the task goes directly to
  `blocked` — it does not even start that step (no thread is created, status never enters the
  step). This is the single guard; there is no other loop protection (D2).
- **Retry consumption (D1)**: every re-entry consumes exactly one retry of the **step being
  re-entered** — reviewer `rework` and tester `rework`/`fail` consume an **executor** retry
  (#12/#15), `retest` consumes a **tester** retry (#16), failure/interruption reruns consume
  the failing step's own retry (#6/#10/#18). Retry counters are only ever decremented.
- The engine **never overrides a manual move**: before applying a completion transition it
  re-reads the task status; if a human/API already moved the task (e.g. `done`), the engine
  skips its transition (only audit-logs).
- Review/tester decision transitions (#12, #14–#17) are **authoritative once applied**; when the
  step thread later completes, the engine sees the status is no longer the step's and does nothing.
- All transitions accept an optional `comment` → `kanban_history.comment` (D3), including
  engine-generated ones (e.g. `comment: "retries_exhausted"`, `"reviewer_rework"`, `"test_failed"`).

### 4.3 Who triggers what (responsibility map)
| Actor | Owns |
|-------|------|
| Dispatcher (actions plugin, existing) | transition #2 only (todo → running, `run_status='scheduled'`). **Unchanged except status name + run_status.** |
| Thread-start (existing channel loop) | #3 / #8 / #13 — the `run_status` 'scheduled' → 'running' flip |
| **Workflow engine** (new `src/agent/workflow.rs`) | #4–#7, #10–#11, #18–#19 — the single decision point on every step-thread completion + the **pre-start retry guard** (D1); replaces the status logic of `kanban_updater.rs` (or wraps it) |
| Reviewer agent (via new tool/API) | #14–#17 (4-way decision, D6) |
| Tester agent (via `kanban_fail_task` / decision tool) | #12 (rework / fail / test-error → executor) |
| Human/API/MCP (existing) | #1, #20, #21 — always legal |

---

## 5. Schema Proposal

### 5.1 Chosen design: two JSONB columns + one flat column on `kanban_tasks`, one column on `threads`, one on `kanban_history`

```sql
-- db-migrations/src/lib.rs (idempotent, single-phase — matches existing migration style)
ALTER TABLE kanban_tasks
  ADD COLUMN IF NOT EXISTS workflow_config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE kanban_tasks
  ADD COLUMN IF NOT EXISTS workflow_state  JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE kanban_tasks
  ADD COLUMN IF NOT EXISTS run_status TEXT;               -- D4: NULL | 'scheduled' | 'running'
ALTER TABLE threads
  ADD COLUMN IF NOT EXISTS kanban_step TEXT;              -- NULL | 'executor' | 'test' | 'review'
ALTER TABLE kanban_history
  ADD COLUMN IF NOT EXISTS comment TEXT;                  -- D3: optional comment on the action record

-- D4: migrate existing 'ready' tasks (thread already pending, §2.2) — see §11
UPDATE kanban_tasks SET status = 'running', run_status = 'scheduled' WHERE status = 'ready';
```

**`workflow_config` shape** (set once at task create/edit; immutable during flight):
```jsonc
{
  "executor": { "profile": null, "channel_id": null, "retries": 0 },
  "tester":   { "profile": null, "channel_id": null, "retries": 0 },
  "reviewer": { "profile": null, "channel_id": null, "retries": 0 }
}
```
- `executor` defaults to the task's existing `profile` / `channel_id` (current behavior);
  explicit `profile`/`channel_id` override for role separation.
- `tester` / `reviewer` omitted or `retries: 0` ⇒ step skipped or no re-entries allowed.
- `retries` = the step's **re-entry budget** (extra tries beyond the first; `retries: 0` ⇒ 1 try,
  any re-entry → guard → `blocked`).

**`workflow_state` shape** (live, mutated by the engine; NULL-safe, written atomically) —
**"retries remaining" semantics (D1)**:
```jsonc
{
  "current_step": "executor" | "test" | "review" | null,
  "executor": { "retries_remaining": 2, "reentries": 0, "last_thread_id": 101,
                "last_outcome": "failure|interruption|rework|fail_tool|success" },
  "tester":   { "retries_remaining": 0, "reentries": 0, "last_thread_id": null, "last_outcome": null },
  "reviewer": { "retries_remaining": 1, "reentries": 0, "last_thread_id": null, "decision": null }
}
```
- `retries_remaining` is initialized from `workflow_config.<step>.retries` at task creation and
  **decremented by 1 on every re-entry** of that step (D1: failures, interruptions, reviewer
  `rework`/`retest`, tester `rework`/`fail`). It is never incremented; `reentries` is an audit
  counter. The **pre-start guard** is `retries_remaining > 0`; at 0 the task is sent to
  `blocked` without starting the step.
- D1 allows "a DB table **or** JSON field"; JSONB column is chosen (one-row atomic write, §5.2).
  Alternative if per-step queries are needed later: a `kanban_step_retries(task_id, step,
  retries_remaining)` table, kept in the same transaction as the transition.
- `run_status` is a flat typed column (D4): `'scheduled'` on step-thread creation, `'running'` on
  pick-up, `NULL` otherwise / legacy rows.

### 5.2 Why JSONB columns (vs alternatives)
| Option | Pros | Cons |
|--------|------|------|
| **JSONB columns (chosen)** | No new table/joins; engine writes one row atomically; flexible role/retry shapes; additive (backward compat); matches existing `plan` JSONB precedent | Schema-less (validation in app layer); no FK on role profile |
| Flat columns (`tester_profile`, `tester_retries`, …) | Typed, indexable, obvious in SQL | 8–9 new columns; awkward "not defined" semantics; rigid; more migration surface |
| `workflow_steps` table (task_id, step, profile, retries, attempts, thread_id) | Relational, queryable history per step | New table + joins; engine needs multi-row transactions; overkill for 3 fixed roles; harder to keep in sync with status transitions |
| workflow config on `threads` | — | Config is a task property, not a thread property; rejected |

Notes: `run_status` and `kanban_history.comment` are **flat typed columns** (not JSONB) because
they are single scalar values queried by the dashboard and audited. `assignee` already exists on
`kanban_tasks` and is **informational** — it is not used by the dispatcher for routing. Keep it
that way; role routing uses `workflow_config.*.channel_id/profile` (falling back to the task's
own). Open question: should `assignee` be the executor's identity in the UI? (§13 Q2)

---

## 6. Thread Execution Model

### 6.1 One thread per step attempt
- Executor step: the dispatcher-created thread (unchanged, but task status is now `running` +
  `run_status='scheduled'` per D4).
- Test step: a **new thread** created by the engine at executor-completion, with
  `threads.task_id = <task>`, `threads.kanban_step = 'test'`, `threads.parent_id = <executor
  thread id>`, cause message `msg_type='kanban'`, `msg_subtype=task_id`, payload carrying
  `{step: 'test', attempt: N}`.
- Review step: same pattern (`kanban_step='review'`, parent = test/executor thread).
- Re-entries: **always a new thread**. Executor re-entries (failure reruns, reviewer/tester
  send-backs) go through `todo` → dispatcher (#6/#12/#15), so the dispatcher creates the new
  executor thread (parent_id → the failed/completed thread). Test/review re-entries (#10/#16/#18)
  are engine-created new threads with `run_status='scheduled'`. Every attempt is auditable via
  `GET /kanban/tasks/{id}/threads` and `kanban_history`.

### 6.2 Channel routing (roles → channels/providers)
- Executor: `task.channel_id` + `task.profile` (existing resolution chain).
- Test/review: `workflow_config.<step>.channel_id ?? task.channel_id`,
  `workflow_config.<step>.profile ?? task.profile`; provider/model resolved by the same
  existing chain (channel → config → defaults).
- **Same channel by default** ⇒ the chain is strictly serial within the channel
  (executor → test → review), reusing the per-channel serial guarantee; a long test blocks
  only its own channel's queue (same as any long thread today).
- **Different channel per role** ⇒ parallel with other channels' work while still serial
  within each role channel. Requires the role's channel to exist & be configured.

### 6.3 How step threads start
The engine mirrors the dispatcher's flow: insert thread (`created → pending`), write seq-0
cause message, set task status (`test` for tester, `review` for reviewer) + `run_status='scheduled'`,
insert `kanban_history` (`action='moved'`, optional `comment`). The existing per-channel loop
claims the pending thread and runs it — no polling loop needed for the step chain (latency ≈ 0);
thread start flips `run_status → 'running'` (D4). The dispatcher is **not** extended: it keeps
owning only `todo → running`.

### 6.4 Step-aware recovery (skip/delete channel)
`delete_channel` / startup skip must become step-aware using `threads.kanban_step`:
- pending `executor` thread (task `running`, `run_status='scheduled'`) → task `todo`,
  `run_status=NULL` (today's rule, renamed per D4).
- pending/running `test` thread → apply **test-step retry logic** (#10/#11: guard → new test
  thread or `blocked`) — do **not** dump to `todo` (which would wrongly re-run the executor).
- pending/running `review` thread → apply **reviewer retry logic** (#18/#19); if no reviewer
  defined, `review` stays (manual).
- running `executor` thread → `blocked` (today's rule; retries may rescue via #6).

---

## 7. Failure Handling & Retry Semantics (v2)

### 7.1 What counts as "non-successful" (uniform per step) + explicit fail tool (D5)

Same predicate the updater uses today, **plus** the new explicit failure signal:
- Thread terminal status ≠ `completed` (`failed`, `interrupted`, `skipped`) ⇒ **failure**.
- `completed` **but** last tool-result message `metadata.is_error = true` ⇒ **failure**.
- **NEW (D5):** an explicit `kanban_fail_task(task_id?, comment?)` call ⇒ **declared failure**,
  regardless of completion state. This is a **BUILT-IN agent tool** (part of the agent core, not
  the kanban MCP plugin) so the tester — and any role — can declare failure directly instead of
  relying only on the last-tool-result heuristic. It marks the current running thread/task as
  failed (thread terminal `failed`), records the optional comment in `kanban_history` (D3), and
  triggers the engine's failure path (§7.2). The last-tool-result heuristic remains as a fallback
  for non-instrumented cases.
- `completed` with no tool error and no fail call ⇒ **success**.
- **Tester-specific (D5):** the tester step fails the task if **even ONE test error occurs** —
  semantics of a test script that exits non-zero when a single test fails. Test errors surface as
  tool errors and/or `kanban_fail_task` calls; any one of them fails the task (§7.2, #12).

### 7.2 Retry decision (engine, at step-thread completion / decision time) — D1

```
on any step outcome (thread terminal, or explicit fail tool, or decision tool):
  outcome = success | failure | interruption | rework | fail_tool | test_error
  (uniform predicate §7.1 + D5 test-error rule; reviewer/tester decisions carry their own outcome)

  if outcome requires RE-ENTERING a step (failure rerun #6/#10/#18, interruption rerun #10/#18,
      reviewer rework #15 → executor, reviewer retest #16 → tester, tester rework/fail #12 → executor):
      step = the step being re-entered
      GUARD (D1): if workflow_state[step].retries_remaining == 0:
          → status 'blocked'  # task does NOT even start that step; no thread created
            kanban_history action='moved' {step→blocked, reason:'retries_exhausted'} + comment
      else:
          workflow_state[step].retries_remaining -= 1     # every re-run consumes one retry (D1)
          workflow_state[step].reentries += 1
          route per §4.2: executor → 'todo' (dispatcher re-dispatches, #2);
                          test/review → new step thread, status stays on step, run_status='scheduled'

  else (success / approve):
      advance per §4.2 (#4/#5/#9/#14); run_status → NULL (leaving the step), then next step sets 'scheduled'
```

- **Retries are the ONLY cap (D1):** there is no "total threads per task" limit and no other loop
  protection (D2). A reviewer→todo loop is bounded because every `rework` consumes an executor
  retry and the guard blocks the task once the budget hits 0 — the task then goes to `blocked`
  rather than looping. `parent_id` chains therefore never grow unboundedly: re-entries ≤
  `retries` per step, and each re-entry is guarded before it starts.
- **Interruption = rerun the same step (D5)**: a tester thread interruption re-runs the test step
  (#10), consuming a tester retry under the guard; same rule applies to executor/review
  interruptions (#6/#18).
- **Explicit fail / test error = back to the beginning (D5):** tester `rework`, tester
  `kanban_fail_task`, and any single test error all route test → todo (#12), consuming an
  **executor** retry under the guard (the executor re-does the work). If the executor's budget is
  already 0, the guard sends the task straight to `blocked`.
- Counters live in `workflow_state` (`retries_remaining` decremented, `reentries` incremented;
  never incremented back — the configured `workflow_config.<step>.retries` is the ceiling).
- Guard: if a step thread was already `skipped` by channel recovery (§6.4), the recovery path
  performs the same decision so retry/blocked is applied exactly once.
- Edge cases: retry threads inherit the same `workflow_config` (no mid-flight config edits —
  enforce in update API: reject `workflow_config` change while status ∈ `{running, test, review}`);
  a channel-closed skip at thread **creation** (thread never started, task back to `todo`) is
  **not** a re-entry and consumes no retry (flagged, §13 Q7).

---

## 8. Review & Tester Decision Capture (v2)

### 8.1 Reviewer — always verifies tests, 4-way decision (D6)

The reviewer **always** verifies the work **including tests** before deciding:
- **rework → executor** (`todo`): the implementation was not done correctly.
- **retest → tester** (`test`): some test failed but the thread passed, **or** the tests are
  wrong / not comprehensive enough. Requires a tester to be defined (else rejected — §13 Q1).
- **approve → done**: implementation and tests both pass review.
- **block → blocked**.

Mechanism (as v1, extended with D3 comment):
- **MCP tool** `kanban_review_task(task_id, decision: "approve"|"rework"|"retest"|"block", comment?)`
  — added to `plugins/tools/kanban/src/main.rs`. The reviewer agent (in the review step thread)
  calls it as its final action.
- **API endpoint** `POST /kanban/tasks/{id}/review` with body `{decision, comment}` — same
  semantics for programmatic/manual use.
- **Validation** in both: task must be in `review`; `retest` requires tester defined; if a
  reviewer is configured, the calling thread must be a review-step thread
  (`threads.kanban_step='review'` and `thread.task_id = task.id`) — otherwise the manual/API
  move fallback applies only to non-workflow tasks.
- **Guard + retry consumption (D1):** `rework` decrements the **executor** retry budget (guard:
  at 0 → `blocked`, not `todo`); `retest` decrements the **tester** budget (guard: at 0 →
  `blocked`, not `test`). This is the only reviewer-loop protection (D2).
- **Persistence**: transition per §4.2 (#14–#17) + `kanban_history` `action='reviewed'` with
  `previous_values: {decision, comment, reviewer_thread_id}` (D3: comment persisted on the record).
- **Idempotency/races**: the endpoint/tool re-checks status inside the UPDATE (`WHERE status='review'`),
  so a stale double-call is a no-op; the engine's completion hook sees status already
  moved and does not override (§4.2 rule).

### 8.2 Tester — decisions (D5)

Tester decision set (mirrors the reviewer):
- **pass** (implicit — thread completes clean: no tool error, no test error, no fail call) →
  advance to `review` (#9).
- **rework** → back to the executor (`todo`): "do it again" — consumes an **executor** retry
  under the guard (D1).
- **fail** (explicit `kanban_fail_task(task_id?, comment?)`) → back to the beginning
  (executor, `todo`) — consumes an **executor** retry under the guard.
- **interruption** → run again in the **SAME** step (`test`) — consumes a **tester** retry under
  the guard (#10).
- **ANY single test error** (D5) → the task fails → back to the executor (`todo`), consuming an
  **executor** retry under the guard (#12).

Mechanism:
- The **built-in `kanban_fail_task(task_id?, comment?)`** tool (D5) is the explicit failure
  signal: the tester calls it to declare failure/rework (comment distinguishes intent), and any
  role can use it. Exposed equivalently as `POST /kanban/tasks/{id}/fail` for programmatic use.
- Routing: engine maps test-step `fail`/`rework`/`test_error` → `todo` (executor re-entry, #12)
  with the executor-retry guard; interruption → test rerun (#10) with the tester-retry guard.
- Optional: a dedicated `kanban_test_task(task_id?, decision: "pass"|"rework", comment?)` tool for
  structured tester decisions (open question — §13 Q6). The fail tool alone already covers all D5
  outcomes.

### 8.3 Why tools (vs a special message / API-only)
- Matches the existing pattern: the agent already has `kanban_update_task`; dedicated tools are
  more discoverable, validate semantics server-side, and return a structured result.
- The `kanban_fail_task` tool is **built-in** (D5) so the tester/any role can fail the task from
  any context without depending on the kanban plugin's last-tool-result heuristic.
- The review/test thread's final LLM message can reference the tool outcome; no parsing of free text.
- Comments (D3) ride along on every decision, so the human board and history show *why*.

---

## 9. Dependency-Engine Interaction

- Today: dependents become eligible when every dep `status IN ('review','done')`.
- **Keep that set exactly.** A task in `test` is not yet accepted → it must **not** satisfy
  dependents (same as `running`). Rationale: `test` is mid-pipeline; dependents should only start
  once the dep is reviewed/done. If the team later wants "test-passed is enough", that's a
  one-line change to the dispatcher SQL (`IN ('review','done','test')`).
- `blocked` (guard-hit re-entries) does not satisfy dependents, as today.
- A task sent back to `todo` by rework/fail (#6/#12/#15) keeps its own deps satisfied (they were
  at first dispatch and only change on manual edit), so the dispatcher re-dispatches it normally.
- No other dependency-engine change; `kanban_task_dependencies` table untouched.

---

## 10. API / MCP Tool / Dashboard Implications (v2)

### 10.1 HTTP API (`src/server/kanban.rs`)
- `VALID_STATUSES` → `["backlog","todo","running","test","review","blocked","done"]` — add
  `test`, **remove `ready`** (D4). `ready` as a write value is rejected (see §11 for migration).
- `KanbanTaskRow` + create/update handlers: accept/return `workflow_config`; return `workflow_state`
  (read-only in GET) and **`run_status`** (D4).
- `PATCH /kanban/tasks/{id}/status`: accept optional **`comment`** param → `kanban_history.comment`
  (D3); validate status against the new list.
- New: `POST /kanban/tasks/{id}/review` body `{decision, comment}` (§8.1);
  `POST /kanban/tasks/{id}/fail` body `{comment?}` (mirrors the built-in fail tool, D5).
  Optional: `GET /kanban/tasks/{id}/workflow` returning `{workflow_config, workflow_state,
  retries_remaining, step_threads}`.
- `PATCH /kanban/tasks/{id}`: reject `workflow_config` edits while in-flight (§7.2).

### 10.2 MCP tools (`plugins/tools/kanban/src/main.rs`)
- `valid_statuses` arrays (create + update) → same 7-value list (drop `ready`, add `test`).
- `kanban_create_task` / `kanban_update_task`: accept optional `workflow_config` JSON arg and
  optional `comment` on updates (D3).
- New: `kanban_review_task` (§8.1). `kanban_list_tasks`: optionally include workflow flags +
  `run_status`.
- **Built-in agent tool** (agent core, not the kanban plugin): `kanban_fail_task(task_id?,
  comment?)` (D5) — available to every role; `task_id` defaults to the current thread's task.

### 10.3 Dashboard (`omni-dashboard/src/lib/*`)
- `kanban-board.ts`: `KANBAN_COLUMNS` → `[backlog, todo, running, test, review, blocked, done]`
  (remove `ready`, insert `test` between `running` and `review`); update `STATUS_LABELS`,
  `columnColorClass`, `statusBadge`.
- `kanban-detail.ts`: "Move to" buttons + edit-modal status select are generated from
  `STATUS_LABELS` → updated automatically. Show a **`run_status` badge** on in-flight tasks
  (`scheduled` = "queued", `running` = "in progress"); display `comment` on history rows (D3);
  show per-step `retries_remaining`; render reviewer/tester decision buttons with comment input.
- Legacy `ready` rows are migrated (never rendered), but the dashboard may defensively treat an
  unseen `ready` as `running`+scheduled (§11).

---

## 11. Backward Compatibility & Migration (v2)

- Empty `workflow_config` (`{}` — the default for all existing rows) ⇒ `tester`/`reviewer`
  undefined ⇒ engine takes the existing path: `running → review` (success) / `blocked`
  (failure), manual `done`. **Zero behavior change for existing tasks.**
- **`ready` → `running` migration (D4):** one idempotent backfill UPDATE in the migration
  (§5.1): `UPDATE kanban_tasks SET status='running', run_status='scheduled' WHERE status='ready'`.
  By construction every `ready` task already has a pending thread (the dispatcher creates the
  thread before setting `ready`, §2.2), so `run_status='scheduled'` is exactly its state.
- **Legacy `run_status` NULL = treated as `'running'` (D4):** existing rows in `running` keep
  NULL; any logic needing scheduled-vs-running treats NULL as `'running'` (matching today's
  semantics where status `running` implies in flight). Manual `review` rows have NULL and no step
  thread — `run_status` is simply irrelevant there (no thread exists).
- `threads.kanban_step` is NULL for all existing threads → recovery logic treats NULL as
  `executor` (today's rules, §6.4).
- `kanban_history.comment` is NULL for old rows — optional column, no backfill (D3).
- `test` is entered only when a tester is defined; existing boards/APIs see the `ready` column
  replaced by `test` (same cardinality).
- **External consumers:** any tooling that writes or filters on `ready` (scripts, integrations,
  saved dashboard filters) must be updated; the API rejects `ready` as a write value with a clear
  error pointing at the migration. The dashboard drops the column.
- Migration is purely additive + idempotent (§5.1); only the `ready` backfill UPDATE is a data
  change. Enum additions/removals are safe because statuses are validated strings, not a Rust
  enum — the new list flows through `valid_statuses`/`VALID_STATUSES` in all four validation
  sites (kanban plugin create/update, server API). (Dashboard + DB columns don't validate.)

---

## 12. Phased Implementation Plan (v2)

**Phase 0 — Schema (1 PR, low risk)**
`db-migrations/src/lib.rs`: the 5 idempotent ALTERs (§5.1) + the `ready`→`running` backfill.
Update `src/db/kanban.rs` row structs/INSERT/UPDATE/get to carry the two JSONB columns +
`run_status`; `src/db/history.rs` to carry `comment`. Deploy-safe (additive).

**Phase 1 — Enum surface (1 PR)**
Add `"test"`, remove `"ready"`: kanban plugin `valid_statuses` (create+update), server
`VALID_STATUSES`. Dashboard `kanban-board.ts` (`KANBAN_COLUMNS`, `STATUS_LABELS`,
`columnColorClass`, `statusBadge`). No behavior change yet.

**Phase 2 — Config & comment plumbing (1 PR)**
API + MCP tools accept/return `workflow_config` and `comment` on status changes (D3);
PATCH in-flight guard. Dashboard edit modal optional workflow fields + comment input;
`run_status` in GET responses.

**Phase 3 — Workflow engine (core, 1–2 PRs)**
- New `src/agent/workflow.rs`:
  - `decide(cfg, state, thread, final_status, stats) -> Outcome` (success/failure/interruption,
    retry vs blocked, next status) — the §7.2 decision including the **pre-start retry guard**
    (D1) and **retries-remaining** bookkeeping, refactoring `kanban_updater.rs` to delegate to it
    (existing no-workflow path preserved verbatim).
  - `create_step_thread(task, step, parent_thread_id, attempt)` — extracted/shared thread-
    creation helper mirroring the dispatcher's insert+cause-message flow, setting
    `run_status='scheduled'` (consider moving the dispatcher's creation code into a shared `db`
    helper to avoid duplication).
  - Wires into the thread terminalization path (where `update_kanban_status` is invoked today)
    and the thread-start path (run_status flip, D4).
- `threads.kanban_step` set on every step thread; cause message carries `{step, attempt}`.

**Phase 4 — Reviewer decision (1 PR)**
`kanban_review_task` MCP tool + `POST /kanban/tasks/{id}/review` (4-way per D6) +
`kanban_history action='reviewed'` + comment (D3) + engine no-override rule.

**Phase 5 — Fail tool + tester routing (1 PR)**
Built-in `kanban_fail_task(task_id?, comment?)` (D5) + `POST /kanban/tasks/{id}/fail`;
test-step routing: fail/rework/test-error → `todo` (executor re-entry with guard), interruption →
test rerun; test-error predicate (any single error fails the task).

**Phase 6 — Recovery hardening (1 PR)**
`src/db/threads.rs` skip/delete-channel recovery becomes step-aware (§6.4) using
`kanban_step` + retry logic + run_status.

**Phase 7 — Docs/tests**
- Integration test matrix: no-config (existing), executor-only fail→blocked, tester flow (pass /
  single test error → executor / fail tool → executor / interruption → rerun), reviewer 4-way
  decisions, retry=1 per step, guard blocks re-entry BEFORE the step starts (no thread created),
  rework/retest consume the right budget (D1), reviewer-loop bounded (D2), comment persisted on
  transitions (D3), run_status lifecycle (D4), legacy `ready` migration, channel skip mid-test,
  dependency with `test` dep, manual override race.
- Wiki + CHANGELOG; dashboard workflow view polish.

---

## 13. Open Questions & Trade-offs (v2)

1. **`retest` with no tester (D6)** — reject the decision, or coerce to `rework` (→todo)?
   Propose: reject with a clear error (config error surfaced to the reviewer). Unchanged from v1.
2. **`assignee` vs role profiles** — keep `assignee` informational and route on
   `workflow_config.*`? (Proposed yes.) Should the board show role avatars? Unchanged.
3. **Serial vs parallel roles** — default same-channel serial (deterministic, reuses existing
   guarantees) vs per-role channels (parallel but requires channel provisioning + separate
   provider config). Trade-off documented in §6.2; per-role channel is opt-in. Unchanged.
4. **Does the test/review thread need the same template/planning_mode as the task?** — propose
   yes (inherit task `template`, `planning_mode`, `plan`) so prompts behave identically; confirm
   with the prompt-builder. Unchanged.
5. **What happens to a task stuck in `review` (manual path) when a reviewer is later
   configured?** — propose: config changes are rejected in-flight (§7.2), so this can't happen;
   manual tasks keep manual review forever. Unchanged.
6. **Tester `rework` tooling (D5)** — is a dedicated `kanban_test_task(task_id?, decision,
   comment?)` decision tool needed, or does `kanban_fail_task` + comment suffice (fail and rework
   route identically to `todo`)? Propose: fail tool alone, revisit if the dashboard needs a
   distinct "rework" badge. **NEW.**
7. **Channel-closed skip at thread creation (D1 interpretation)** — the task returns to `todo`
   before the step ever started; propose this is **not** a re-entry and consumes **no** retry.
   D1's literal wording ("retries apply to ANY re-entry") could be read to consume one; decide at
   implementation. **NEW — flagged, not silently resolved.**
8. **`ready` removal vs external consumers (D4)** — any external script/API client filtering on
   `ready` breaks. Migration is provided (§11); is a grace period needed where the API maps
   `ready`→`running` on read? Propose: no, migrate + reject writes. **NEW.**
9. **Audit** — should `kanban_history` also log `step_started` events, or is
   `action='moved'`/`'retry'`/`'reviewed'`/`'failed'` + `threads` listing + `comment` enough?
   Propose the latter (minimal), revisit if users want per-attempt dashboards.
10. **Subtasks** — workflow steps apply to the parent task only; per-subtask workflows are out
    of scope (note for future). Unchanged.

---

## 14. Verification Notes (honesty)

- All §2 facts marked [VERIFIED] were read from source in the v1 thread (kanban plugin, actions
  dispatcher, `kanban_updater.rs`, `threads.rs`, `server/kanban.rs`, `db-migrations`, dashboard
  libs, live DB). **v2 reused these facts without re-reading sources** — the user design decisions
  (D1–D6) alter the target design, not the verified current-system facts; no fact claimed in §2 was
  changed by a decision.
- The **exact call site** of `update_kanban_status` inside the agent's terminal-finalization
  path (main_loop/executor) was not pinned to a line number in the v1 thread (file is 72 KB; the
  call is in the completion path). Phase 3 must confirm it before wiring the engine.
- The thread-start site that flips `run_status` ('scheduled' → 'running') likewise needs
  line-level confirmation in Phase 3.
- This document is a design proposal; nothing has been implemented. The user-required location
  was honored (`/opt/workspace/omni-stack/data/research/`).
- Ambiguities deliberately left open rather than silently resolved: §13 Q7 (channel-skip vs D1
  "any re-entry"), §13 Q6 (tester rework tooling), §13 Q8 (`ready` read-mapping grace period),
  §13 Q1 (retest with no tester).

---

## 15. Research Update v3 — User Rulings on Open Questions (Final)

**Update type:** research-update v3 (append-only; all v1/v2 sections above remain valid and unchanged).
**Request:** thread 71, cause message #429: "research-update v3: omniagent 'workflow' feature — user rulings on open questions (final)".
**Prepared:** 2026-08-05.

### 15.1 Provenance & Honesty Note (required reading)

The v3 request arrived with **only the title above — no rulings content was delivered with it**. This was verified exhaustively before writing this update:

1. **Trigger message (#429):** `content` = exactly `"research-update v3: omniagent 'workflow' feature — user rulings on open questions (final)"` (88 chars, verified via `messages` table) — no rulings text, no body.
2. **Kanban task:** `kanban_tasks.body` for task `task_18c8f1207e1f3fd3` = empty string.
3. **Thread:** `threads.cause` for thread 71 = `"system"` (no rulings carried in thread metadata).
4. **Message history:** full-text search for ruling-related terms (`grace period`, `Q7`, `retest with no tester`, `rework tooling`, `consume`, `rulings`) across all messages found **no user message containing rulings** — only this agent's tool-call records and the v2 report text posted earlier (message #426).
5. **Wiki / memory / filesystem:** no wiki pages, no promoted memories, and no other research files contain rulings on these open questions.

**Consequence (honest):** No user ruling could be incorporated into v3. **Every open question from v2 §13 remains OPEN.** To keep this document actionable, §15.2 below records the v2 position for each open question and adds the agent's recommendation in the same "proposal" style used in v1/v2 — these are **agent proposals, NOT user rulings**, and are explicitly labeled as such. They must not be treated as decided.

### 15.2 Rulings Status per Open Question (from v2 §13)

| # | Open question | v2 status | v3 ruling status | Agent recommendation (proposal, NOT a ruling) |
|---|---|---|---|---|
| Q1 | Retest with no tester — reject vs coerce | OPEN (flagged) | **OPEN — no ruling received** | Reject the retest (surface as blocked/comment). Consistent with D1: retries are the only rework cap; a retest with no tester must not silently pass. |
| Q2 | Assignee vs role profiles | OPEN | **OPEN — no ruling received** | Roles are the unit of authority (D2/D6); keep `assignee` as a display/back-compat field only. |
| Q3 | Serial vs parallel roles | OPEN | **OPEN — no ruling received** | Keep serial: one active role per task (executor → tester → reviewer), simplest transition model. |
| Q4 | Test/review thread template & `planning_mode` inheritance | OPEN | **OPEN — no ruling received** | Inherit the thread template from the role config; `planning_mode=false` for tester/reviewer threads (deterministic tool sequences). |
| Q5 | Task stuck in review when reviewer configured later | OPEN | **OPEN — no ruling received** | Re-issue the review step (fresh thread) on reviewer (re)configuration; do not auto-pass. |
| Q6 | (NEW) Tester rework tooling — dedicated `kanban_test_task` vs `kanban_fail_task` alone | OPEN | **OPEN — no ruling received** | Dedicated `kanban_test_task`: gives `run_status` transitions (D4) and structured retest evidence without polluting the retry ledger. |
| Q7 | (NEW) Channel-closed skip at thread creation — consumes a retry? | OPEN | **OPEN — no ruling received** | Do NOT consume a retry: closed channel is an infrastructure condition, not task rework (mirrors D1's intent to cap only genuine rework). |
| Q8 | (NEW) Ready-removal vs external consumers — grace period? | OPEN | **OPEN — no ruling received** | NO grace period: removal is immediate and atomic; consumers must re-read config on miss. Document the semantics. |
| Q9 | Audit — `step_started` events in `kanban_history` | OPEN | **OPEN — no ruling received** | Add `step_started` (status-change) events; cheap and makes history replayable for the dashboard. |
| Q10 | Subtasks — scope | OPEN (out of scope) | **OPEN — no ruling received** | Keep out of scope for the workflow feature; record as a documented non-goal. |

### 15.3 Document Status & Next Step

- The workflow feature design remains in **proposal state**: v2 §3–§12 (with D1–D6) define the baseline; v2 §13 open questions await rulings.
- v3 appends this section only; no v2 section was modified, so the verified v2 baseline is preserved.
- **Next step:** the user re-sends the rulings on §13's open questions (the v3 trigger message currently carries only the title) → a follow-up update integrates them into §4 (transitions), §7 (retry semantics), §8 (tester/reviewer capture), and §13.

### 15.4 Verification Notes (v3)

- This section was appended to `workflow-role-based-kanban.md`; the v2 content (chars 0–48,462) was not altered (verified by byte-range reads before appending).
- No user ruling was fabricated. Every item in §15.2's last column is explicitly an **agent recommendation**, not a user decision.
- If a rulings message exists but was not indexed/delivered, it can be supplied as a follow-up and this section updated.
