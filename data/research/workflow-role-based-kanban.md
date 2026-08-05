# omniagent "workflow" Feature — Role-Based Kanban Flow (Executor / Tester / Reviewer) — v5

**Status:** Research (design proposal, not yet implemented)
**Date:** 2025 (research thread; v5 incorporates user design decisions D1–D6, user rulings R1–R9
(v3), R11–R13 (v4), **and ROUND-3 rulings (v5): thread_status rename, `testing` status, executions
counter, N9–N14 resolutions**; R10 was referenced in the v3 task brief but no ruling content was
supplied — treated as a no-op, flagged in §13 N3)
**Source of truth:** omniagent repo at `/opt/workspace/omniagent` (read in-thread for v1), live DB
(`kanban_tasks`/`threads`/`kanban_history`/`kanban_task_dependencies`), dashboard at
`/opt/workspace/omni-dashboard`. Facts marked [VERIFIED] were read from source in the v1 thread;
facts marked [PRE-VERIFIED] were supplied and reused. **v2/v3/v4/v5 reuse all v1 facts** — the user
design decisions and rulings change the *target design*, not the verified current-system facts
(§2), so no sources were re-read for v5.

**v5 changelog (ROUND-3 user rulings — these override the v4 text where they conflict):**
- **thread_status** — the kanban_tasks field is named `thread_status` (NULL / 'scheduled' /
  'running'), NOT `run_status`. Renamed everywhere.
- **`testing` status** — the new kanban status is `testing`, NOT `test`. Renamed everywhere
  (status enum, transitions, workflow_step values, fail-tool matrix, schema).
- **Executions counter instead of retries-remaining** — retry/execution LIMITS are defined in the
  workflow role config (`workflows.config.<role>.retries`); the task references the workflow
  (`workflow_id`) to know the limits and tracks `workflow_state.executions[<step>]` — incremented
  by 1 after each thread run. Guard: `executions[<step>]` ≥ limit → `blocked` (no thread).
- **N9–N14 resolved** — last-message/type = last message in thread + messages.msg_type; recent
  threads scope is a prompt-plugin concern (builtin = sensible window); executor resume is a
  prompt-plugin concern; cron threads included (prompt plugin); a step may NOT fail itself
  (executor → empty/self or `blocked` only; reviewer → running/testing/blocked; tester →
  running/blocked); tester-created tests are project-specific (template or AGENTS file, generic
  template).

**v2 changelog (user design decisions applied):**
- **D1 — Retries are the ONLY cap.** Each step (main/test/review) has a retry count, default 0
  (= 1 try). Any re-entry of a step consumes one retry of that step (rework, retest, fail,
  interruption). No separate thread cap; no extra loop protection.
- **D2 — No extra loop protection.** No throttles or circuit breakers beyond D1 retries.
- **D3 — Comments on status changes.** Every transition accepts an optional `comment`, stored in
  `kanban_history.comment`.
- **D4 — `thread_status` + `ready` removal.** `ready` is removed; a `thread_status` column
  (NULL / 'scheduled' / 'running') reflects the step-thread lifecycle. NULL = resting state.
- **D5 — Tester step fails on ANY single test error.** Tester success → `review`; tester
  failure/rework → back to executor (`todo`).
- **D6 — Reviewer always verifies the work including tests.** Reviewer decisions: approve /
  rework (→ executor) / retest (→ tester) / block. Note: R12 (v4) re-expresses how the reviewer
  AGENT issues these decisions — via normal thread completion (approve) or the generic fail-task
  tool (rework→`running`, retest→`testing`, block→`blocked`) — see §4.2/§8.1.

**v3 changelog (user rulings applied — these override the v2 text where they conflict):**
- **R1** — `thread_status` NULL means the task is **doing nothing** (resting state), NOT a legacy
  synonym for 'running'. 'scheduled' = step thread just created (seq-0 written), pending pick-up;
  'running' = the omniagent loop picked the thread up and started iterations. A task may go
  `todo → running` without ever being 'scheduled' when no thread pre-creation is involved —
  `thread_status` reflects the *thread lifecycle*, not the task status. All "legacy NULL = running"
  mappings are removed (§4.1, §5, §11).
- **R2** — An interruption that causes a rerun of the SAME step consumes that step's retry —
  **including the tester step** (confirmed). Stated explicitly in §4.2, §7, §8.
- **R3** — Pre-start / external skips consume NO retry. A step "started" = its thread was created
  (`thread_status` became 'scheduled' or the step began). Failures/interruptions AFTER start consume
  retries; conditions that prevent start (channel closed, no provider, thread creation failed) do
  NOT. Precisely defined in §7.2.
- **R4** — NO backward compatibility for `ready` (omniagent has not gone to production): no
  read-mapping grace period, no legacy 'ready'→'running' mapping on read. Migrate existing 'ready'
  rows at migration time (`status='running'`, `thread_status='scheduled'` when a thread is pending,
  else NULL) and REJECT any future writes of 'ready' (§11).
- **R5** — Invalid target status → `blocked` with an AUTOMATIC comment (replaces v2's
  "reject with clear error"). If a decision/transition would target a status that is incorrect for
  the task's workflow config, the task goes to `blocked` and a `kanban_history` comment (D3)
  explains why (e.g. "…target status was incorrectly defined as 'testing' but no tester is
  configured"). EXCEPTION: `review` is a VALID target even with NO reviewer defined — the task
  sits in `review` awaiting MANUAL review (existing behavior). So: review-without-reviewer = valid
  manual state; test-without-tester = invalid → blocked + auto comment. Resolves v2 §13 Q1.
- **R6** — v2 §13 Q6 RESOLVED: the failure signal is a **generic BUILT-IN fail-task tool** (NOT
  kanban-specific in name or scope). It ends the current thread as FAILED with an Error-type
  message as the LAST thread message; a `metadata` param may carry `kanban_status` ∈ {`running`,
  `testing`, `review`, `blocked`} (default `running`; any other value → `blocked`). The kanban
  status change is done by the SERVER LOOP (§R8), which verifies the execution limit of the TARGET
  status: limit reached → `blocked` (no thread); else increment `executions[<target>]` by 1, create
  thread + seq-0, mark task 'scheduled'. Works for `running`, `testing` AND `review` (the
  dispatcher only does `running`). `blocked` never has a thread and its `thread_status` is NULL.
  (Naming note: rulings use `testing` where v2 uses the status `testing` — see §13 N2.)
- **R7** — Threads table gains workflow/task-type fields: `workflow_id` (which workflow definition),
  `workflow_step` (the kanban status: `running`/`testing`/`review`), `task_type` (`cron`|`kanban`),
  `task_id` (kanban or cron task id). The last two are NOT necessarily workflow-related — a cron
  thread populates them too. The seq-0 message type/subtype indication moves to dedicated columns.
- **R8** — The server loop handles fail/interrupt transitions ATOMICALLY (single DB transaction):
  thread + seq-0 message + kanban status / thread_status update + history comment, reusing the
  existing thread-creation function. Failure → new status (running/testing/review, retry-guarded);
  interruption → rerun SAME step (status unchanged, thread_status→'scheduled'); retry limit reached →
  `blocked`, NO new thread. Exact comment templates in §6.5.
- **R9** — Dashboard gains a **Workflows page** to DEFINE workflows: a NAME plus per-role config
  (executor REQUIRED, tester/reviewer OPTIONAL) with fields Name / Profile / Provider / Model /
  Planning Mode / Template, plus a `workflows` table. Precedence: **Workflow fields > kanban task
  fields > channel fields > global fields**. Roles have NO channel fields — all steps run in the
  task's channel (or the default kanban channel). Kanban task planning_mode semantics defined
  (falls back to channel planning mode → None; None ≠ Off). Model honored only when the role's
  provider is ALSO explicitly defined.

**v4 changelog (Round-3 user rulings R11–R13 applied — authoritative design decisions):**
- **R11 — Role-aware context: the task is the SAME; each role does its PART.** Every step of a
  kanban task runs against the SAME `kanban_tasks` row (same title/body/plan); what differs is the
  role instruction and the thread context the prompt carries. EXECUTOR runs the task AS IS and must
  have a way to know PREVIOUS TASK THREADS — to avoid error loops (not repeat the same mistake), to
  start from where it ended in case of interrupted tasks, and to fix in case of failing review
  (rework). TESTER (when defined) must know it should RUN THE TESTS (and possibly CREATE automated
  tests too) and NOT implement the task; it must have access to the executor thread AND to all
  recent threads of this task. REVIEWER (when defined) must do a COMPREHENSIVE REVIEW of the
  execution and the tests (when a tester is defined) and NOT implement the task; it must have
  access to the executor thread, the tester threads, AND all recent threads of this task. → New
  §3.5.
- **R12 — Threads carry the kanban task id; prompt_generate shows workflow context.** The kanban
  task id MUST be present on the threads it creates — `threads.task_id` is set for ALL workflow
  step threads (executor `running`, test `testing`, review `review`; `task_id` already exists for
  kanban threads — v4 confirms it applies to every workflow step thread). `prompt_generate` looks
  up threads BY kanban task id and shows: the thread id, the `workflow_step` (executor / tester /
  reviewer), and the LAST message of the thread and its TYPE (normally the summary, or the fail
  message of the thread). This gives the agent context: the task is the same, but the role must do
  its part — executor executes the task (this is the DEFAULT for kanban tasks with no workflow);
  tester should NOT execute the task — it should create automated tests and test it; reviewer must
  review — with a successful status and a normal summary message when everything is OK, OR call the
  fail tool in case of an issue, marking to move the task to a given ALLOWED status (`running`,
  `testing`, or `blocked`).
- **R13 — Kanban history as error-loop context.** Recent `kanban_history` entries (status changes +
  comments, incl. the D3 `comment` column) are also good context — e.g. to avoid error loops (like
  knowing that the task is executing again after the tester marked it as failed). The agent's
  context should be able to include recent `kanban_history` entries so it understands WHY the task
  is being run again.

---

## 1. Executive Summary

The user wants a "workflow" mode on top of the existing kanban task pipeline: the current
single-actor flow (dispatcher → executor thread → `review` → manual `done`) becomes an
optional **3-role pipeline** — **executor** (required), **tester** (optional), **reviewer**
(optional) — with **per-step retry counts** (default 0). When no workflow config is present,
behavior must be byte-for-byte identical to today.

Key design choices (v4):

1. **Workflows are dashboard-defined entities (R9)** in a new `workflows` table (name + per-role
   config: name/profile/provider/model/planning_mode/template/retries), referenced by
   `kanban_tasks.workflow_id`; **live run state stays in a `workflow_state` JSONB column**
   carrying **`executions` counters per step** (v5 — limits in the workflow, task counts runs);
   **`thread_status` column**
   (NULL/'scheduled'/'running') replaces the `ready` status (D4) with **NULL = resting state,
   no in-flight step thread (R1)**; **`comment` column on `kanban_history`** (D3).
2. **Retries are the ONLY cap (D1; v5 executions-counter semantics).** The retry/execution
   LIMITS live in the workflow role config (`workflows.config.<role>.retries`); the task tracks
   `workflow_state.executions[<step>]` — incremented by 1 after each run. A step's budget is
   consumed on **any re-entry** of that step: failure reruns, interruption reruns, reviewer
   `rework`/`retest`, tester `rework`/`fail` (each re-entry increments that step's executions).
   **Interruption reruns of the SAME step consume that step's retry (R2)** —
   including the tester step. **Pre-start/external skips consume NO retry (R3)**: a step
   "started" only when its thread was created ('scheduled' or the step began); channel-closed /
   no-provider / thread-creation-failed conditions that prevent start return the task to its
   prior state without incrementing `executions`. **Guard:** before the workflow sends the
   task to a step again it checks the executions counter against the workflow limit FIRST; if the
   limit is reached the task goes directly to `blocked` and the step is **never started**.
3. **`ready` is dropped with NO backward compatibility (R4).** Existing 'ready' rows migrate at
   migration time (`running` + `thread_status='scheduled'` when a pending thread exists, else NULL);
   future writes of 'ready' are REJECTED. No read-mapping, no grace period. `thread_status` NULL is
   the resting state — there is no legacy NULL-as-running mapping (R1).
4. **New status `testing`** added to all status validation lists (enum is open — statuses are plain
   strings everywhere). `ready` removed from all lists (with a data migration, §11).
5. **Each step is one thread** (the existing thread machinery is reused): test/review threads are
   created by the server-loop/workflow engine at thread-completion time, chained via the existing
   `threads.parent_id` column, carrying `threads.workflow_id` + `threads.workflow_step` +
   `threads.task_type`/`task_id` (R7). **`threads.task_id` is set on ALL workflow step threads —
   executor, test, review (R12)** so the task's full thread history is findable by task id and can
   be surfaced as role-aware context (§3.5). Executor re-entries go back through `todo` → the
   existing dispatcher.
6. **Generic built-in fail-task tool (R6):** a BUILT-IN, GENERIC agent tool (not kanban-specific
   in name or scope) ends the current thread as FAILED with an Error-type message as the last
   thread message. A `metadata.kanban_status` param selects the target status (`running` default |
   `testing` | `review` | `blocked`; anything else → `blocked`). The kanban status change is done
   by the **server loop** (§6.5), which execution-guards the TARGET status, increments its
   `executions` counter by 1, and creates the next thread + seq-0 message in a single transaction
   (R8). Works for `running`,
   `testing`, AND `review` (the dispatcher only does `running`). Tester step fails the task if **even
   one** test error occurs. Tester outcomes: pass → review; rework/fail → back to executor
   (`todo`); interruption → rerun the same step consuming a tester retry (R2). **Per R12 the
   reviewer also uses this tool (targets `running`/`testing`/`blocked`) instead of a dedicated
   decision tool — §8.1.**
7. **Reviewer always verifies the work including tests (D6).** Per R12 the reviewer's 4-way
   decision is expressed through the standard completion/fail mechanism: **success = the review
   thread completes normally with a summary message (status success) → `done`; issue = a call to
   the generic fail-task tool marking an allowed target status — `running` (rework), `testing`
   (retest), or `blocked` (block)**. The dedicated `kanban_review_task` MCP tool / `POST /review`
   endpoint are retained for MANUAL/API review only (§8.1, §10.1/§10.2). **Invalid target statuses
   are validated against the workflow config and go to `blocked` with an automatic comment (R5)**:
   e.g. `retest` with no tester configured → `blocked` + auto comment (resolves v2 Q1); `review`
   remains valid with or without a reviewer (manual state).
8. **Dependencies**: a task in `testing` does **not** satisfy dependents (keep `IN ('review','done')`);
   `testing` is treated like `running` for dependency purposes.
9. **Server-loop atomic transitions (R8):** fail/interrupt/retry-exhausted transitions — new
   thread + seq-0 + status/thread_status update + history comment — happen in ONE DB transaction,
   reusing the existing thread-creation function. No new thread is created when retries are
   exhausted (→ `blocked`); `blocked` never has a thread and `thread_status` is NULL.
10. **Workflows page (R9):** dashboard CRUD for workflow definitions (name + per-role
    name/profile/provider/model/planning_mode/template). Precedence: **Workflow fields > kanban
    task fields > channel fields > global fields**; roles have NO channel fields — all steps run
    in the task's channel (default kanban channel when none). Kanban task `planning_mode` falls
    back to channel planning mode → None (None ≠ Off). The kanban task template takes priority
    over the workflow role template when both are defined.
11. **No-workflow tasks are unchanged**: `workflow_id` NULL ⇒ exactly today's behavior
    (executor-only — executor is the DEFAULT role for kanban tasks with no workflow, R12 — then
    `review` → manual/API `done`).
12. **Role-aware agent context (R11–R13):** the kanban task is the SAME for all steps; each role
    does its PART. Prompts carry a role instruction (executor: run the task as-is — the default
    for no-workflow tasks; tester: run/create tests, never implement; reviewer: comprehensive
    review of execution + tests, never implement) plus **thread context built by
    `prompt_generate` from `threads.task_id`** — per-thread {id, `workflow_step`, last message +
    type (summary | fail)} — plus **recent `kanban_history` entries** (status changes + comments)
    so a re-run understands why it is running again (error-loop awareness). New §3.5, §10.4.

---

## 2. Current System — Verified Facts

### 2.1 Status model [VERIFIED]
- **Kanban MCP plugin** `plugins/tools/kanban/src/main.rs`:
  `valid_statuses = ["backlog","todo","ready","running","review","done","blocked"]`
  (used in both create and update handlers). **No `testing` status.**
- **HTTP API** `src/server/kanban.rs`:
  `const VALID_STATUSES: &[&str] = &["backlog","todo","ready","running","review","blocked","done"]`.
- **Dashboard** `omni-dashboard/src/lib/kanban-board.ts`: `KANBAN_COLUMNS` (7 columns:
  backlog, todo, ready, running, review, blocked, done) + `STATUS_LABELS` + `columnColorClass` +
  `statusBadge`; `kanban-detail.ts` renders "Move to" buttons and the edit-modal status select
  **from `STATUS_LABELS`**.
- *Target-design note (D4/R4):* `ready` is removed and `testing` added ⇒ validation lists become
  `["backlog","todo","running","testing","review","blocked","done"]` (still 7 entries; §4.1, §10).
  `ready` writes are rejected outright (R4).

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
- *Target-design note (D4/R4):* the dispatcher keeps owning **only** `todo → running`; it now sets
  status `'running'` + `thread_status='scheduled'` (no `ready`). The dispatcher remains the ONLY
  creator of executor (`running`) threads; the server loop creates test/review threads (R8).
  **v4 note (R12):** the dispatcher already sets `threads.task_id` on the executor thread — v4
  confirms `task_id` is set on EVERY workflow step thread (executor/test/review, §3.5.2).

### 2.3 Thread → task status on completion [PRE-VERIFIED; file `src/agent/kanban_updater.rs`]
`update_kanban_status(cfg, thread, final_status, stats)` — only when `thread.task_id` is set:
- `final_status == "completed"` **and** last tool-result message had `metadata.is_error = true`
  → task `blocked`.
- `final_status == "completed"` (no error) → task `review`.
- any other terminal (`failed`, `interrupted`, `skipped`, …) → task `blocked`.
- (Call site: thread terminal-finalization path in the agent — `main_loop.rs`/`executor.rs`;
  exact helper line to confirm at implementation. The dispatcher sets `todo → ready`; the
  `ready → running` transition is driven by thread start — existing behavior, not in the dispatcher.)
- *Target-design note:* v3 replaces this logic with the server-loop / workflow engine decision
  (§6.5, §7.2), which honors the generic fail-task tool (R6) and the retry guard (D1/R2/R3). The
  no-workflow path is preserved verbatim. **v4 note (R12):** this per-thread task linkage is
  exactly what `prompt_generate` relies on for role-aware context — threads carry `task_id`, so
  the prompt builder can list a task's step threads and their last messages (§3.5.2, §10.4).

### 2.4 Channel-skip / delete recovery [VERIFIED — `src/db/threads.rs`]
`delete_channel` (and the startup skip path): threads of the channel are marked `skipped`
and their tasks recovered:
- threads `status='pending'` with task `status='ready'` → task back to `'todo'`.
- threads `status='running'` → task `'blocked'`.
This logic is **not step-aware** today — it must become workflow-aware (see §6.4).

### 2.5 Schema (live DB + `db-migrations/src/lib.rs`) [VERIFIED]
- `kanban_tasks`: `id, title, body, status, priority, position, assignee, channel_id, profile,
  archived, template, planning_mode, created_at, updated_at, plan`. **No workflow columns.**
  `planning_mode` ALREADY EXISTS — R9's "kanban task should have a planning mode field" is
  satisfied; R9 only defines its fallback semantics (§10.3).
- `threads`: `id, status, cause, channel_id, profile, provider, model, terminal, task_id,
  schedule_task_id, planning_mode, parent_id, iterations, plan, …`. `task_id` links thread→task
  (kanban today); **`parent_id` exists** (thread chaining already supported). R7 generalizes
  `task_id` with a `task_type` discriminator and adds `workflow_id`/`workflow_step`. **v4 note
  (R12):** `task_id` is set on ALL workflow step threads (executor/test/review) — the prompt
  builder finds a task's step threads by `task_id` (§3.5.2).
- `kanban_history`: `id, kanban_task_id, action, initial_board, final_board, previous_values,
  created_at`. **No `comment` column.** (v4 note (R13): `comment` (D3) is surfaced in agent
  context — recent history entries incl. comments become prompt context, §3.5.3/§10.4.)
- `kanban_task_dependencies`: dep pairs (satisfied per §2.2).
- Migration style: **declarative single-phase** — `CREATE TABLE IF NOT EXISTS` + idempotent
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (+ backfill UPDATEs). New columns must follow this
  pattern; no versioned migration runner.
- Live DB: exactly 1 kanban task exists (status `running`); no `testing` status anywhere.

### 2.6 API surface [VERIFIED — `src/server/kanban.rs`, 13 routes]
`GET /kanban/tasks`, `GET /kanban/tasks/{id}`, `GET /kanban/tasks/{id}/dependencies`,
`POST /kanban/tasks`, `PATCH /kanban/tasks/{id}/status`, `PATCH /kanban/tasks/{id}/position`,
`PATCH /kanban/tasks/{id}`, `DELETE /kanban/tasks/{id}`, `GET /kanban/tasks/{id}/threads`,
`POST|DELETE …/dependencies`, `GET /kanban/tasks/{id}/history`, `GET /kanban/history`,
`GET /kanban/tasks/{id}/subtasks`. KanbanTaskRow exposes `workflow`-less fields only.
MCP tools: `kanban_create_task`, `kanban_list_tasks`, `kanban_update_task`,
`kanban_delete_task` (+ dispatcher tool). **v4 note (R12/R13):** `prompt_generate` (agent-core
prompt builder) gains the workflow-context block (§10.4); `GET /kanban/tasks/{id}/history` is the
data source for the recent-history context (R13).

### 2.7 Concurrency model [PRE-VERIFIED]
Threads execute **per-channel serially** (one active thread per channel; different channels
run in parallel). Roles share the task's channel (R9 — roles have no channel fields), so the
executor → test → review chain is strictly serial within that channel.

---

## 3. Feature Spec (User Intent, v4)

- **Workflow definitions (R9)**: a workflow is defined on the dashboard's Workflows page — a
  NAME plus per-step ROLE config: **executor (required)**, **tester (optional)**, **reviewer
  (optional)**. Each role has fields: Name (optional, defaults to the role key), Profile (defaults
  to task profile → channel profile → setting profile → "omni"), Provider (defaults to channel
  provider → default provider in settings), Model (defaults to the default model of the resolved
  provider; an explicit model is honored ONLY when the role's provider is ALSO explicitly
  defined), Planning Mode (defaults to none → kanban task planning mode → channel planning mode →
  None; None ≠ Off), Template (kanban task template takes PRIORITY when both are defined).
  Precedence: **Workflow fields > kanban task fields > channel fields > global fields**. Roles
  have NO channel fields — all steps run in the task's channel (or the default kanban channel).
- **Executor (required)**: existing main execution — `todo → running (thread)`. **Runs the task
  AS IS (R11); the executor is the DEFAULT role for kanban tasks with no workflow (R12).** Its
  prompt must include the PREVIOUS TASK THREADS (thread id, `workflow_step`, last message + type)
  so it can avoid error loops (not repeat the same mistake), start from where it ended in case of
  interrupted tasks, and fix the work after a failing review (rework) (R11 — §3.5).
- **Tester (optional)**: **creates + runs automated tests; does NOT implement the task (R11).**
  When defined, after executor success → **new status `testing`**; a test thread runs; the tester
  **fails the task on ANY single test error** (D5); success → `review`. Its prompt includes the
  executor thread AND all recent threads of this task (R11 — §3.5).
- **Reviewer (optional)**: **comprehensive review of the execution AND the tests (when a tester is
  defined); does NOT implement the task (R11).** When defined, in `review` a reviewer thread runs
  and the reviewer **always verifies the work including tests** (D6). Per R12 the reviewer's
  decision is expressed via the standard mechanism: **success = thread completes normally with a
  summary message (status success) → `done`; issue = call the generic fail-task tool marking an
  allowed target status — `running` (rework), `testing` (retest), or `blocked` (block)**. Its
  prompt includes the executor thread, the tester threads, AND all recent threads of this task
  (R11 — §3.5). `review` is valid even with NO reviewer — it then awaits MANUAL review (R5).
- **Role-aware agent context (R11–R13)**: all steps share the SAME kanban task; each role does its
  PART. Prompts carry (a) a role instruction, (b) thread context built by `prompt_generate` from
  `threads.task_id` (per-thread {id, `workflow_step`, last message + type}), and (c) recent
  `kanban_history` entries (status changes + comments) for error-loop awareness. Full spec in
  §3.5; `prompt_generate` mechanics in §10.4.
- **`thread_status` (D4/R1)**: `'scheduled'` = a step thread was just created (seq-0 written) and is
  pending pick-up; `'running'` = the loop picked the thread up and iterations started; **NULL =
  resting state — no in-flight step thread** (task in backlog/todo/done/blocked, or manual review
  without reviewer). NULL is NOT a legacy synonym for 'running' (R1).
- **Retries = the only cap (D1/R2/R3)**: each step (main/test/review) has a retry budget,
  **default 0** (= 1 try). ANY re-entry of a step — failure rerun, interruption rerun, reviewer
  `rework`/`retest`, tester `rework`/`fail`, generic fail-task tool transition — consumes one
  retry of the step being re-entered (or of the fail tool's TARGET status, R6). A **pre-start
  guard** checks the counter first: if exhausted, the task goes directly to `blocked` and the
  step is never started. **Interruption reruns consume the step's retry (R2); pre-start/external
  skips consume NONE (R3).** No separate thread cap; no extra loop protection (D2).
- **Failure (D5/R6/R12)**: non-successful terminal thread state, an explicit generic **fail-task
  tool** call, or (for the tester) a single test error → the failure path (§7.2); a tester
  failure sends the task back to the executor, consuming an executor retry. The reviewer's issue
  path uses the same fail-task tool with allowed targets `running`/`testing`/`blocked` (R12).
- **Comments (D3/R13)**: every status transition (API, MCP tools, reviewer/tester decision tools,
  engine/server-loop transitions) accepts an optional `comment` stored in `kanban_history.comment`.
  Automatic blocked transitions carry an auto-generated comment explaining why (R5/R8). Comments
  are part of the agent context surface (R13 — §3.5.3).

---

## 3.5 Role-Aware Agent Context (v4 — R11, R12, R13)

> Numbered §3.5 (rather than a renumbered top-level section) to avoid renumbering §4–§14 and
> their ~80 internal cross-references; the section is new in v4.

**Principle (R11): the kanban task is the SAME for all steps; each role does its PART.** Every
step thread of one task runs against the same `kanban_tasks` row (same title/body/plan). What
differs is (a) the **role instruction** in the prompt and (b) the **thread context** the prompt
carries. No step thread ever re-implements another role's part — a tester must not implement the
task, a reviewer must not implement the task.

### 3.5.1 Per-role prompt context (what each role's prompt must include)

| Role | Role instruction (in prompt) | Thread access rules (R11) |
|------|------------------------------|---------------------------|
| **EXECUTOR** (required; default role for no-workflow kanban tasks, R12) | Run the task AS IS — implement the kanban task body. Do not test or review on its behalf. | The task + **PREVIOUS TASK THREADS** (thread id, `workflow_step`, last message + type) — to avoid error loops (not repeat the same mistake), to start from where it ended in case of interrupted tasks, and to fix in case of failing review (rework). |
| **TESTER** (when defined) | RUN THE TESTS (and possibly CREATE automated tests too); **do NOT implement the kanban task**. | The **executor thread** AND **all recent threads of this task** (R11). |
| **REVIEWER** (when defined) | COMPREHENSIVE REVIEW of the execution AND the tests (when a tester is defined); **do NOT implement the kanban task**. Success = complete the thread normally with a summary message (status success) → task `done`. Issue = call the generic fail-task tool marking an ALLOWED target status: `running` (rework) / `testing` (retest) / `blocked` (block) (R12). | The **executor thread**, the **tester threads** (when a tester is defined), AND **all recent threads of this task** (R11). |

Thread-access rules are enforced by the prompt builder when assembling the context block
(§10.4) — the tester/reviewer prompts include the referenced threads' last-message summaries;
the executor prompt includes the prior step threads' last messages. (How much of a referenced
thread — full transcript vs summary — is shown is a context-budget question, flagged §13 N10.)

### 3.5.2 Thread context construction (R12 — prompt_generate)

- **The kanban task id MUST be present on the threads it creates**: `threads.task_id` is set on
  ALL workflow step threads — executor (`running`), test (`testing`), review (`review`) — together
  with `task_type='kanban'`, `workflow_id`, `workflow_step` (R7). `task_id` already exists and is
  set for kanban threads today; v4 confirms it applies to every step thread, including test and
  review threads created by the server loop (§6.1).
- **`prompt_generate`** (agent-core prompt builder) **looks up threads BY kanban task id**
  (`WHERE task_id = <task> AND task_type='kanban' ORDER BY id`) and renders a per-thread entry:
  - **thread id**;
  - **`workflow_step`** — displayed as `executor` / `tester` / `reviewer` (the DB column stores
    the kanban status `running`/`testing`/`review` per R7; the display mapping is assumed, flagged
    §13 N13);
  - **the LAST message of the thread and its TYPE** — normally the thread SUMMARY (successful
    completion), or the FAIL message (the Error-type last message produced by the generic
    fail-task tool, R6). (Definition of "last message" and the message-type taxonomy: flagged
    §13 N9.)
- The block answers "what happened before, in this task?" from the role's viewpoint: the task is
  the same, but the role must do its part. When no thread exists yet (first run), the block is
  empty and the executor starts fresh.
- **No-workflow tasks**: the same mechanism with only executor threads (workflow_step `running`,
  displayed `executor`); the role instruction is the executor default ("run the task as-is",
  R12).

### 3.5.3 Kanban history as error-loop context (R13)

- Recent `kanban_history` entries for the task — **status changes + comments** (incl. the D3
  `comment` column) — are ALSO surfaced in the agent's context, so a step thread understands WHY
  it is being run again. Example from R13: the task is executing again because the tester marked
  it as failed (history shows `test → todo` + comment); the executor thread can then see that the
  previous attempt failed testing and must fix, not repeat.
- Suggested rendering: one line per entry, e.g.
  `#<history_id> <created_at> <action> <step|status → step|status> [comment]` — newest first,
  limited to the "recent" window (proposal: last 10 entries; exact scope flagged §13 N10).
- This context is read-only; it never overrides the role instruction — it only explains the run's
  origin (retries, rework, retest, interruption, blocked).

---

## 4. Status Machine (v4)

### 4.1 Statuses
`valid_statuses = ["backlog","todo","running","testing","review","blocked","done"]` — `ready`
removed (R4), `testing` added (D5), everywhere (plugin, API, dashboard; §10). `thread_status` ∈
{NULL, 'scheduled', 'running'} (R1: NULL = resting — task has no in-flight step thread).

### 4.2 Transition table (workflow-aware; all engine transitions are server-loop, R8)

| # | From | To | Trigger / notes |
|---|------|----|-----------------|
| 1 | `todo` | `running` | Dispatcher (existing; only executor step). Thread created, `thread_status='scheduled'`. `threads.task_id` = task (R12). |
| 2 | `running` | `todo` | Executor non-success terminal OR **empty fail-task target** (F0 — implicit self, v5 N13) — but retry-guarded: if the executor execution limit is reached the task goes to `blocked` instead (guard, D1/R2/R3). Re-entry is a NEW dispatcher thread. **The executor may NOT explicitly fail into `running` (F1 is for tester/reviewer rework, N13).** |
| 3 | `running` | `running` | Interruption → rerun SAME step (status unchanged, `thread_status='scheduled'`), consumes an executor retry (R2). |
| 4 | `running` | `testing` | Executor success AND tester defined (R9) → server loop creates the test thread (R8), `thread_status='scheduled'`. `threads.task_id` = task (R12). |
| 5 | `running` | `review` | Executor success AND no tester defined → review (manual or reviewer thread). |
| 6 | `running` | `blocked` | Executor retry limit reached (guard fires BEFORE the step starts — no new thread, R2/R3). |
| 7 | `testing` | `review` | Tester pass (no test errors, D5) AND reviewer defined → server loop creates the review thread (R8); if NO reviewer defined, the task sits in `review` awaiting MANUAL review (R5). `threads.task_id` = task (R12). |
| 8 | `testing` | `todo` | Tester `rework` / failure — back to executor (consumes an executor retry; guard may send to `blocked`). |
| 9 | `testing` | `todo` | ANY single test error (D5) — back to executor. |
| 10 | `testing` | `testing` | Tester interruption → rerun SAME step, consumes a tester retry (R2 — confirmed for the tester step). |
| 11 | `testing` | `testing` | Tester retry (D1 — explicit re-run without interruption). |
| 12 | `testing` | `blocked` | Tester retry limit reached (guard). |
| 13 | `review` | `done` | Reviewer decision `approve` — **expressed per R12 as the review thread completing NORMALLY with a summary message (status success)**; server loop advances to `done`. Also manual/API (no reviewer / human) via `POST /review` or MCP `kanban_review_task` (§8.1, §10.1/§10.2). |
| 14 | `review` | `todo` | Reviewer decision `rework` — expressed per R12 as a **generic fail-task tool call with `metadata.kanban_status='running'`** → executor (consumes an executor retry; guard). |
| 15 | `review` | `testing` | Reviewer decision `retest` — **fail-task tool with `metadata.kanban_status='testing'`** → tester (consumes a tester retry; guard). `testing`-without-tester → `blocked` + auto comment (R5 — resolves v2 Q1). |
| 16 | `review` | `blocked` | Reviewer decision `block` — **fail-task tool with `metadata.kanban_status='blocked'`** (no thread; `thread_status` NULL). |
| 17 | `review` | `review` | Reviewer interruption → rerun SAME step, consumes a reviewer retry (R2). |
| 18 | `review` | `review` | Reviewer retry (D1). |
| 19 | `blocked` | — | Terminal. No thread ever; `thread_status` NULL. |
| 20 | `done` | — | Terminal. No thread ever; `thread_status` NULL. |

> **R12 note (v5 — N13 resolved):** the reviewer's 4-way decision set (D6) is expressed through
> the standard completion/fail mechanism — `approve` = normal thread completion + summary message
> (row 13), `rework`/`retest`/`block` = generic fail-task tool calls with allowed targets
> `running` / `testing` / `blocked` (rows 14–16). The dedicated decision tool/endpoint remain for
> MANUAL/API use only (§8.1, §10.1/§10.2). **A step may NOT fail itself (v5 — N13 resolved):**
> `review` is not in the reviewer's target set; `running`/`testing` are not in their own steps'
> target sets; only `blocked` is definable by the executor (impossible-task case) and empty →
> returns to the executor itself (implicitly, not explicitly). Interruptions use I1 reruns, never
> fail calls.

**Fail-task tool matrix (R6 — server loop, R8):**

| # | `metadata.kanban_status` | Server loop behavior |
|---|--------------------------|----------------------|
| F0 | *(empty)* | Executor default — returns to the executor step itself (task → `todo`, like the dispatcher), guard/executions permitting (v5 — N13 resolved: implicit self, not explicit). |
| F1 | `running` | Verify `executions['running']` < workflow limit → increment by 1, task → `todo`, create executor thread + seq-0, `thread_status='scheduled'`. Limit reached → `blocked` + auto comment. Allowed callers: tester (rework), reviewer (rework). **NOT the executor itself (N13).** |
| F2 | `testing` | Verify `executions['testing']` < workflow limit → increment by 1, task → `testing`, create test thread + seq-0, `thread_status='scheduled'`. No tester configured → `blocked` + auto comment (R5). Allowed callers: reviewer (retest). **NOT the tester itself (N13).** |
| F3 | `review` | Verify `executions['review']` < workflow limit → increment by 1, task → `review`, create review thread + seq-0 (only used by non-reviewer roles; **no role may fail into its own step** — R12/N13). |
| F4 | `blocked` | Task → `blocked`, NO thread, `thread_status` NULL (R6). Allowed for any role (executor: impossible task; tester/reviewer: block). |
| F5 | any other value | Task → `blocked` + auto comment ("invalid target status …") (R5/R6). |

**Interruption matrix (server loop, R8):**

| # | Step | Behavior |
|---|------|----------|
| I1 | running/testing/review | Rerun SAME step: status unchanged, `thread_status='scheduled'`, new thread + seq-0 (parent = interrupted thread). Consumes that step's retry (R2) — i.e. `executions[<step>]` increments; at the workflow limit → `blocked`, no thread. |

**Safety rules:** guard checks the executions counter against the workflow limit BEFORE any step
re-entry (no thread is created when the limit is reached); `blocked`/`done` never have threads and
`thread_status` is NULL; a step thread must be
terminal before the next transition; every engine transition is ONE DB transaction (thread +
seq-0 + status/thread_status + history comment — R8); every transition stores an optional `comment`
(D3/R13).

### 4.3 Responsibility map
- **Dispatcher** (existing): `todo → running` only (row 1).
- **Server loop / workflow engine** (new): rows 2–18, F1–F5, I1 — atomic (R8), retry-guarded
  (D1/R2/R3), with `comment` support (D3).
- **Agent (executor)**: runs the task as-is; may call the generic fail-task tool (F1/F4).
- **Agent (tester)**: runs/creates tests; success = normal completion (row 7); any test error or
  rework = fail-task tool (F1) or non-success terminal (rows 8/9).
- **Agent (reviewer)**: success = normal completion + summary (row 13, R12); issue = fail-task
  tool with `running`/`testing`/`blocked` (rows 14–16, R12).
- **Manual/API**: `PATCH …/status`, `POST /review` (manual approve/rework/retest/block), MCP
  `kanban_update_task`, MCP `kanban_review_task` (manual-only per R12), task edit/delete, move
  to `done`.

---

## 5. Schema Changes (v4)

All changes follow the existing **declarative single-phase** migration style (§2.5):
`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE … ADD COLUMN IF NOT EXISTS` + idempotent backfill
UPDATEs; no versioned migration runner.

### 5.1 `threads` table (R7 + R12)
- **`workflow_id`** `UUID NULL` — which workflow definition this step thread belongs to
  (`REFERENCES workflows(id)`; NULL for cron/non-workflow threads).
- **`workflow_step`** `TEXT NULL` — the kanban status of the step: `'running'` (executor),
  `'testing'` (tester), `'review'` (reviewer) (R7). Display names executor/tester/reviewer are a
  prompt-level mapping (§3.5.2, §13 N13).
- **`task_type`** `TEXT NULL` — discriminator for `task_id`: `'kanban'` | `'cron'` (R7; NOT
  necessarily workflow-related — a cron thread populates it too).
- **`task_id`** — existing column, generalized (kanban task id today; cron id for cron threads).
  **v4 (R12): `task_id` is set on ALL workflow step threads — executor (`running`), test
  (`testing`), review (`review`)** — the server loop sets it when creating test/review threads, and
  the dispatcher already sets it on executor threads. This is what lets `prompt_generate` find a
  task's full step-thread history (`WHERE task_id = <task> AND task_type='kanban'`, §3.5.2/§10.4).
- **seq-0 type/subtype** — the seq-0 message's type/subtype indication moves to dedicated columns
  (R7); unchanged behavior otherwise.
- `ALTER TABLE threads ADD COLUMN IF NOT EXISTS workflow_id UUID;`
  `ALTER TABLE threads ADD COLUMN IF NOT EXISTS workflow_step TEXT;`
  `ALTER TABLE threads ADD COLUMN IF NOT EXISTS task_type TEXT;`
  Backfill: existing kanban threads get `task_type='kanban'` (task_id already set — N7).

### 5.2 `kanban_tasks` table (D1/D4/R1)
- **`workflow_id`** `UUID NULL` — `REFERENCES workflows(id)`; NULL = no workflow ⇒ today's
  behavior (§11). Rejected mid-flight changes (no edits while status ∈ {running, test, review} —
  §7.2 edge cases).
- **`thread_status`** `TEXT NULL` — `'scheduled'` (step thread just created, seq-0 written) |
  `'running'` (loop picked the thread up) | **NULL = resting state, no in-flight step thread (R1)**.
  `CHECK (thread_status IS NULL OR thread_status IN ('scheduled','running'))`.
- **`workflow_state`** `JSONB NULL` — live run state: `{"executions": {"running": N,
  "testing": M, "review": K}}` (v5 — ROUND-3 ruling). **Executions counter, NOT retries-remaining:**
  the retry LIMITS are defined in the referenced `workflows.config` (via `workflow_id` — the task
  references the workflow to know the limits); the task tracks how many times each step has
  actually RUN. After the task starts the first time, `executions[<step>]` is updated instead of a
  remaining counter — **after running the step's thread, increment `executions[<step>]` by 1**. The
  guard compares `executions[<step>]` against the workflow's configured limit for that role; when
  the limit is reached, re-entry → `blocked` (never starts, no thread). NULL for non-workflow tasks.
- `ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS workflow_id UUID;`
  `ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS thread_status TEXT;`
  `ALTER TABLE kanban_tasks ADD COLUMN IF NOT EXISTS workflow_state JSONB;`
- Migration of `ready` (R4): existing rows with `status='ready'` → `status='running'` +
  `thread_status='scheduled'` when a pending thread exists, else `thread_status=NULL`; future 'ready'
  writes are REJECTED at the validation layer (§2.1, §11).

### 5.3 `kanban_history` table (D3 + R13)
- **`comment`** `TEXT NULL` — optional comment on any transition (D3). Auto-generated for
  automatic `blocked` transitions (R5/R8). **v4 (R13):** `comment` is surfaced in agent context
  as part of the recent-history block (§3.5.3, §10.4).
- `ALTER TABLE kanban_history ADD COLUMN IF NOT EXISTS comment TEXT;`

### 5.4 `workflows` table (new — R9)
- `id` UUID PK, `name` TEXT NOT NULL, `config` JSONB NOT NULL — per-role config:
  `{"executor": {name, profile, provider, model, planning_mode, template, retries},
    "tester":   {…},   "reviewer": {…}}` — executor REQUIRED, tester/reviewer OPTIONAL.
- `created_at`, `updated_at` timestamps.
- **`retries` lives here — in the workflow role config (v5 — ROUND-3 ruling, resolves N5):** the
  retry LIMITS are defined in the workflow, and the task references the workflow (`workflow_id`) to
  know the limits. The task itself only tracks `executions` (§5.2). `config.<role>.retries` = the
  execution limit for that role's step (default 0 = 1 run; any re-entry past the limit → `blocked`).

### 5.5 Migration order & data backfill
1. `workflows` table; 2. `kanban_tasks` columns (+ `ready` migration, R4); 3. `threads` columns
(+ `task_type='kanban'` backfill for existing kanban threads, N7); 4. `kanban_history.comment`.
All idempotent; no data loss for existing tasks.

---

## 6. Thread Execution Model (v4)

### 6.1 Step threads (one thread per step)
- **Executor step (`running`)**: dispatcher-created thread (existing); `workflow_id` +
  `workflow_step='running'`; `task_id` = kanban task id (already set today — R12). Re-entries
  (rework/fail/interruption) are new dispatcher threads via `todo` (row 2) or I1 reruns (row 3).
- **Test step (`testing`)**: server-loop-created at executor completion when a tester is defined
  (row 4, R8); `parent_id` = executor thread; `workflow_step='testing'`; **`task_id` = kanban task id
  (R12)**; seq-0 cause message written; `thread_status='scheduled'`.
- **Review step (`review`)**: server-loop-created at tester completion (row 7) or at executor
  completion when no tester is defined (row 5); `parent_id` = previous step thread;
  `workflow_step='review'`; **`task_id` = kanban task id (R12)**; `thread_status='scheduled'`.
- Every step thread is picked up by the omniagent loop when its channel is free (per-channel
  serial execution, §2.7) → `thread_status='running'`.
- **v4 (R12):** because `task_id` is on ALL step threads, `prompt_generate` renders the task's
  step-thread list (thread id, `workflow_step`, last message + type) for role-aware context —
  §3.5.2, §10.4. The executor thread list is what lets an executor avoid error loops, resume
  interrupted work, and rework after a failed review (R11).

### 6.2 Provider / model per role (R9)
Each role resolves its own provider/model: role config → task fields → channel fields → global
defaults. **An explicit model is honored ONLY when the role's provider is ALSO explicitly
defined** (R9). The executor falls back to today's chain (channel → config → default
`openai/gpt-4o`, §2.2).

### 6.3 Planning mode / template (R9)
Role planning_mode → kanban task planning_mode → channel planning mode → **None** (None ≠ Off).
Kanban task `template` takes priority over the workflow role `template` when both are defined.

### 6.4 Channel closure / deletion (workflow-aware)
`delete_channel` / startup-skip recovery (§2.4) must become step-aware:
- A **pending step thread** (`status='pending'`, `thread_status='scheduled'`) whose step never
  started → task returns to the step's PRIOR status; **no retry consumed (R3)** (e.g. executor
  thread pending → `todo`; test thread pending → `running`; review thread pending → `testing` or
  `running` per workflow).
- A **running step thread** (`thread_status='running'`) → the step is interrupted mid-flight → the
  step is RE-RUN (I1) consuming that step's retry (R2) when the channel recovers, or `blocked`
  when retries are exhausted.
- The step thread's `task_id`/`workflow_step` fields (R7/R12) are what make this recovery
  step-aware.

### 6.5 Server-loop atomic transitions (R8)
All engine transitions (rows 2–18, F1–F5, I1 in §4.2) run in **ONE DB transaction**, reusing the
existing thread-creation function:
1. Create the next step thread + seq-0 cause message (`parent_id` chaining).
2. Update `kanban_tasks.status` and `thread_status` (and increment `workflow_state.executions[<step>]` when
   the step runs — v5 executions-counter semantics).
3. Insert `kanban_history` row (`action='moved'`, boards, optional `comment` — D3/R13).
Comment templates (auto-generated): `"Rework requested by reviewer — executor run N/M"`,
`"Retest requested by reviewer — tester run N/M"`, `"Tester failure — executor run N/M"`,
`"Execution limit reached for <step> — task blocked"`, `"Invalid target status '<x>' — task blocked
(R5)"`, `"Interrupted — <step> re-run (run N/M, R2)"`, `"<step> failed — task blocked"` (N = current
`executions[<step>]`, M = the workflow's configured limit — v5 executions-counter semantics).
No new thread is created when the execution limit is reached (→ `blocked`; `blocked` never has a
thread, `thread_status` NULL — R6).

---

## 7. Failure & Retry (v4)

### 7.1 Terminal states → success/failure
- `completed` with no error → SUCCESS (executor → row 4/5; tester → row 7; reviewer → row 13).
- `completed` with last tool-result `metadata.is_error = true` → FAILURE (existing
  `kanban_updater` semantics, §2.3).
- `failed` / `interrupted` / `skipped` → FAILURE (non-success terminal).
- **Generic fail-task tool call (R6)** = explicit FAILURE: ends the current thread as FAILED with
  an Error-type message as the LAST thread message; `metadata.kanban_status` selects the target
  (`running` default | `testing` | `review` | `blocked`; anything else → `blocked`).
- Tester step: **ANY single test error fails the task** (D5) regardless of other test outcomes.

### 7.2 Retry guards & routing (v5 — executions counter)
- **Limits live in the workflow (ROUND-3 ruling, resolves N5):** the retry/execution LIMITS are
  defined in `workflows.config.<role>.retries`; the task references the workflow via `workflow_id`
  to know them. The task tracks **`executions`** — the number of times each step has run — NOT a
  decrementing remaining counter.
- **Executions increment (ROUND-3 ruling):** after the task starts the first time, update
  `workflow_state.executions[<step>]` instead of a remaining value; **after running the step's
  thread, increment `executions[<step>]` by 1** (part of the same transition transaction, R8).
- **Guard (D1/R2/R3):** before the workflow sends a task to a step again, it checks
  `workflow_state.executions[<step>]` against the workflow's configured limit for that role. If the
  limit is reached → task goes directly to `blocked` (+ auto comment) and the step is **never
  started** (no thread created). Otherwise the step runs and the executions counter increments as
  part of the transition transaction (R8).
- **Interruption reruns consume the step's retry (R2)** — including the tester step. Status
  unchanged; `thread_status='scheduled'`; new thread + seq-0 (I1).
- **Pre-start / external skips consume NO retry (R3):** conditions that PREVENT the step from
  starting (channel closed at thread creation, no provider, thread-creation failure) return the
  task to its prior state without incrementing `executions` (§6.4).
- **Fail-task tool routing (R6/R8):** the SERVER LOOP performs the status change: verify the
  TARGET status's execution limit (F1–F5), increment `executions[<target>]` by 1, create thread + seq-0, mark
  `thread_status='scheduled'`. Works for `running`, `testing`, AND `review` — the dispatcher only does
  `running`. **v4 (R12):** the reviewer's issue path uses this tool with allowed targets
  `running`/`testing`/`blocked` (§4.2 rows 14–16, §8.1).
- **No double transitions:** guard + atomic transaction (R8) prevent a task from being sent to a
  step while another transition is in flight.
- **Edge cases:** retry threads inherit the same workflow (no mid-flight edits — reject changes
  to `workflow_id` / role config while status ∈ {running, test, review}); a channel-closed skip
  at thread creation consumes no retry (R3); a fail-task tool call from a role that is not
  allowed to target a status (e.g. reviewer → `review`) is handled by the role instruction +
  target validation (R5/R12 — N13).

---

## 8. Review & Tester (v4 — R11/R12)

### 8.1 Reviewer — always verifies work + tests; decision via completion/fail mechanism (D6, R12)
The reviewer **always** verifies the execution **and** the tests (when a tester is defined) (D6).
It does **NOT implement the task** (R11). Its prompt includes the executor thread, the tester
threads, and all recent threads of this task (R11 — §3.5.1).

**Per R12 the reviewer's decision is expressed through the standard completion/fail mechanism**
(instead of a dedicated agent-side decision tool):

- **SUCCESS (approve):** the review thread completes **normally** — `completed`, no tool error,
  no fail call, and a **normal summary message** as its last message (status success). The server
  loop treats review-step success as **approve → `done`** (§4.2 row 13). No `kanban_review_task`
  call is needed.
- **ISSUE:** the reviewer calls the **generic built-in fail-task tool (R6)** with
  `metadata.kanban_status` ∈ allowed targets:
  - `running` → **rework** → executor (row 14; consumes an executor retry, guard);
  - `testing` → **retest** → tester (row 15; consumes a tester retry; no tester configured →
    `blocked` + auto comment, R5);
  - `blocked` → **block** (row 16; no thread, `thread_status` NULL).
  `review` is NOT an allowed target for the reviewer (a reviewer interruption is handled by the
  I1 rerun, row 17 — §13 N13).
- **Target validation (R5):** any invalid/incorrect target (e.g. retest without tester) →
  `blocked` with an automatic comment; `review` remains valid without a reviewer (manual state).
- **Guard (D1/R2):** rework consumes an executor retry; retest consumes a tester retry; when the
  target step's retries are exhausted the task goes to `blocked` instead of re-entering the step.
  The reviewer loop is bounded by D1/D2 (retries are the only cap; no extra loop protection).
- **Manual/API path (unchanged, R5):** `POST /review` / MCP `kanban_review_task` with
  `decision ∈ {approve, rework, retest, block}` + optional `comment` (D3) remain for MANUAL
  review and the no-reviewer manual state — the reviewer **agent** no longer uses them (R12
  supersedes; whether to remove them entirely is flagged §13 N13).

### 8.2 Tester — tests only; fail on ANY single test error (D5, R11/R12)
The tester **runs the tests (and may CREATE automated tests)** and **does NOT implement the
kanban task** (R11). Its prompt includes the executor thread AND all recent threads of this task
(R11 — §3.5.1).
- Success: test thread completes normally (no test errors) → `review` (row 7).
- **ANY single test error** (D5) → failure → back to executor (row 9; consumes an executor
  retry).
- Rework decision → back to executor (row 8).
- Interruption → rerun the same step, consuming a tester retry (R2 — row 10).
- Retry limit reached → `blocked` (row 12, guard).
- The tester may call the generic fail-task tool with `metadata.kanban_status='running'`
  (rework) when it cannot complete testing at all (F1).

### 8.3 Test/review thread context
Test/review threads are created by the server loop (R8): `parent_id` = previous step thread;
`workflow_id` + `workflow_step` (`'testing'`/`'review'`); **`task_id` = kanban task id (R12)**;
seq-0 cause message; `thread_status='scheduled'` → `'running'` on pick-up. Because `task_id` is set
on every step thread, `prompt_generate` can render the task's step-thread history for the
tester/reviewer prompts (§3.5.2, §10.4).

---

## 9. Dependencies (unchanged)

A task in `testing` does **not** satisfy dependents: the dependency gate keeps
`status IN ('review','done')` (§2.2). `testing` is treated like `running` for dependency purposes —
a dependent task never starts while its dependency is in `testing`.

---

## 10. API & Dashboard (v4)

### 10.1 HTTP API (`src/server/kanban.rs`)
- `VALID_STATUSES` → `["backlog","todo","running","testing","review","blocked","done"]` (`ready`
  removed — R4; `testing` added — D5). `PATCH /kanban/tasks/{id}/status` rejects `ready` outright
  (R4) and validates against the new list.
- `POST /review` (reviewer decision endpoint) retained for MANUAL/API use: `decision` ∈
  {approve, rework, retest, block} + optional `comment` (D3); server-side target validation (R5)
  and retry guards (D1/R2) apply (same routing as §8.1). The reviewer AGENT does not call it
  (R12 — §8.1, §13 N13).
- `GET /kanban/tasks/{id}/history` — data source for the R13 recent-history context
  (§3.5.3, §10.4), now including `comment` (D3).

### 10.2 MCP tools (kanban plugin)
- `kanban_update_task` — validates the new status list; `ready` rejected (R4).
- `kanban_review_task` — retained for MANUAL/API use only (per R12); same decisions/comments as
  `POST /review` (§8.1).
- Generic **fail-task tool** (`fail_task` — name TBD, N1) — built-in agent core, NOT
  kanban-specific (R6); `metadata.kanban_status` handled by the server loop (§6.5).

### 10.3 Dashboard (`omni-dashboard`)
- `KANBAN_COLUMNS` → 7 columns: backlog, todo, running, test, review, blocked, done;
  `STATUS_LABELS` updated; detail page "Move to" buttons + edit-modal select come from
  `STATUS_LABELS` automatically. **Manual review decision buttons (approve/rework/retest/block +
  comment) are the manual path (no-reviewer / human review) — the reviewer agent's decisions
  arrive via normal completion or the fail-task tool (R12).**
- History page renders `comment` (D3/R13).
- **Workflows page (R9):** CRUD for workflow definitions — name + per-role fields
  (Name/Profile/Provider/Model/Planning Mode/Template [+ Retries — N5]) — writing
  `workflows.config`; precedence UI hints (Workflow > task > channel > global).
- Kanban task `planning_mode` semantics (R9): falls back to channel planning mode → None.

### 10.4 `prompt_generate` — workflow context block (v4 — R12/R13)
`prompt_generate` (agent-core prompt builder) gains a **workflow-context block** built from the
kanban task id:
1. **Thread lookup by task id (R12):** `SELECT id, workflow_step FROM threads WHERE task_id =
   <task> AND task_type='kanban' ORDER BY id` — every step thread carries `task_id` (§5.1, §6.1),
   so the builder can list the task's step threads even though the task row itself has no thread
   list. **Cron threads included (v5 — N12 resolved):** the same lookup applies to cron threads
   (`task_type='cron'`); both are handled in the prompt plugin, not omniagent core.
2. **Per-thread entry:** `{thread_id, workflow_step (executor|tester|reviewer — display mapping,
   N13), last_message, last_message_type}` — **last message = the LAST message in the thread; type
   = the `messages.msg_type` field (v5 — N9 resolved).** Normally the thread SUMMARY (success) or
   the FAIL message (Error-type message from the fail-task tool, R6).
3. **Recent kanban_history entries (R13):** last N status changes + comments for the task
   (`GET /kanban/tasks/{id}/history` or direct query) so the agent understands WHY the task is
   being run again (e.g. tester marked it failed → executor re-entry). **Scope is a prompt-plugin
   decision (v5 — N10 resolved).**
4. **Role instruction block** per `workflow_step` (executor: run the task as-is — default for
   no-workflow tasks; tester: run/create tests, do NOT implement; reviewer: comprehensive review
   of execution + tests, do NOT implement — §3.5.1) and **thread-access rules** (tester sees the
   executor thread + all recent; reviewer sees executor + tester threads + all recent — R11).
No-workflow tasks: only executor threads are listed and the executor role instruction is used;
the block is empty on first run.

**v5 — this is a PROMPT-PLUGIN concern (N10/N11/N12 resolved):** how many threads, the time
window, token budget, and resume semantics (context-only vs stateful) are defined by the
`prompt_generate` tool — which may be provided by EXTERNAL plugins. The builtin prompt plugin uses
a sensible window. The tool may receive a parameter indicating it is part of a workflow. Tool
calls receive the thread id as a **meta field**. Omniagent core only guarantees the data source
(threads with `task_id` + `workflow_step` + last message, kanban_history entries).

---

## 11. Backward Compatibility (v4)

- **No `ready` compatibility (R4):** existing 'ready' rows migrate at migration time
  (`status='running'` + `thread_status='scheduled'` when a pending thread exists, else NULL);
  future 'ready' writes are rejected. No read-mapping, no grace period.
- **No-workflow tasks unchanged:** `workflow_id` NULL ⇒ today's behavior; the executor is the
  DEFAULT role for kanban tasks with no workflow (R12) — prompts carry the executor role
  instruction and the thread list shows only executor threads (§3.5.2).
- **Existing threads:** `task_id` is already set on kanban executor threads (R12 — the
  `prompt_generate` lookup works immediately for existing tasks); `task_type` is backfilled
  (`'kanban'` when `task_id` set, `'cron'` for `schedule_task_id`-only rows, NULL for ambiguous —
  N7). `thread_status` NULL = resting (R1) — no legacy NULL-as-running mapping.
- **API consumers:** status lists change (`ready` out, `testing` in); dashboard updates per §10.3.

---

## 12. Phased Implementation Plan (v4)

- **Phase 0 — Schema + migration (1 PR):** §5 DDL (workflows, kanban_tasks columns incl.
  `workflow_state`/`thread_status`, threads workflow columns, kanban_history.comment); `ready`
  migration (R4); `task_type` backfill (N7). Declarative single-phase style.
- **Phase 1 — Status validation + dashboard columns (1 PR):** new status lists everywhere
  (§10.1/§10.2/§10.3); `ready` rejected (R4).
- **Phase 2 — Generic fail-task tool + metadata (1 PR):** built-in `fail_task` tool (R6, N1)
  ending the thread FAILED with an Error-type last message; `metadata.kanban_status` plumbing.
- **Phase 3 — Server-loop atomic transitions + retry guards (1 PR):** R8 transaction
  (thread + seq-0 + status/thread_status + history comment); guard (D1/R2/R3); interruption reruns
  (I1); fail-tool routing F1–F5; no thread on retry exhaustion.
- **Phase 3b — Role-aware prompt context (R11–R13, 1 PR):** `prompt_generate` workflow-context
  block (§10.4): thread lookup by `task_id`, per-thread {id, workflow_step, last message + type};
  role-instruction templates (executor/tester/reviewer, §3.5.1); thread-access rules (R11);
  recent kanban_history entries (status changes + comments) as error-loop context (R13).
- **Phase 4 — Reviewer/tester decisions (1 PR):** tester = normal completion / fail-task tool
  (D5/R6); reviewer per R12 — success = normal completion + summary → done; issue = fail-task
  tool with `running`/`testing`/`blocked`; `kanban_review_task`/`POST /review` retained for
  manual/API use; target validation (R5).
- **Phase 5 — Workflows page + precedence (1 PR):** workflows CRUD (R9); field precedence
  (Workflow > task > channel > global); planning_mode semantics.
- **Phase 6 — Recovery hardening (1 PR):** step-aware channel closure/deletion (§6.4).
- **Phase 7 — Docs/tests:** update wiki + CHANGELOG; dashboard polish.
- **Integration test matrix (additions for v4):** no-config (existing); executor-only fail →
  blocked; tester flow (pass / single test error → executor / fail tool → executor / interruption
  → rerun same step consuming tester retry (R2)); reviewer 4-way decisions; retest without tester
  → blocked + auto comment (R5); channel-closed-before-start → no retry consumed (R3);
  `thread_status` NULL = resting (R1); ready write rejected (R4); fail-tool metadata matrix F1–F5
  (R6); server-loop single-transaction transitions (R8); Workflows page CRUD + precedence (R9);
  retry=1 per step, guard blocks re-entry BEFORE the step starts (no thread created);
  rework/retest consume the right budget (D1); reviewer-loop bounded (D2); comment persisted on
  transitions (D3); `thread_status` lifecycle (D4); channel skip mid-test; dependency with test dep;
  manual override race; **task_id present on all step threads (R12); prompt_generate context
  lists step threads per task id with step + last message + type (R12); reviewer approves via
  normal completion (summary, status success) → done (R12); reviewer issue via fail tool →
  running/testing/blocked with retry guards (R12); kanban-history context present when a task
  re-runs after tester failure (R13); tester context shows executor thread + all recent; reviewer
  context shows executor + tester threads + all recent (R11); no-workflow task = executor default
  role instruction (R12).**

---

## 13. Open Questions & Trade-offs (v5)

**Resolved in v3 (user rulings):**
1. **`retest` with no tester (R5 — resolves v2 Q1)** — invalid target → `blocked` + auto comment;
   `review` remains valid even with no reviewer (manual state).
6. **Tester failure tooling (R6 — resolves v2 Q6)** — NEITHER a dedicated kanban fail/test tool
   NOR a decision tool; a generic built-in fail-task tool ends the current thread FAILED with an
   Error-type last message; optional `metadata.kanban_status` ∈ {`running`, `testing`, `review`,
   `blocked`} (default `running`; any other value → `blocked`). The kanban status change is done
   by the server loop (R8), which verifies the target's execution limit: reached → `blocked` (no
   thread); else increment `executions[<target>]` by 1, create thread + seq-0, mark 'scheduled'.
   Works for `running`, `testing`, AND
   `review` (the dispatcher only does `running`). `blocked` never has a thread and its
   `thread_status` is NULL.
7. **Channel-closed skip at thread creation (R3 — resolves v2 Q7)** — no retry consumed;
   the task returns to its prior state.
8. **`ready` removal vs external consumers (R4 — resolves v2 Q8)** — no backward compatibility;
   migrate + reject.

**Carried over unchanged (still open):**
2. **Assignee** — kanban tasks can assign a user; unchanged (out of scope for v4).
3. **Serial vs parallel** — per-channel seriality keeps the workflow serial within a channel;
   cross-channel parallelism unchanged (out of scope).
4. **Template/planning-mode precedence** — workflow role template vs task template vs channel
   template; v4 assumes task template wins over workflow role template (R9). Confirm in Phase 5.
5. **Stuck in review** — a task in `review` without a reviewer stays manual; no auto-timeout
   (out of scope).
9. **Audit** — decide whether per-step/attempt history rows (e.g. `attempt_id`/
   `attempt_status` in `kanban_history`) are needed, or whether `thread_status` + threads listing +
   `comment` suffice. Propose the latter (minimal); revisit if users want per-attempt dashboards.
10. **Subtasks** — workflow steps apply to the parent task only; per-subtask workflows are out
    of scope (note for future).

**NEW ambiguities found while integrating R1–R9 (v3 — flagged, NOT silently resolved):**
- **N1 — Name of the generic fail-task tool.** R6 says "generic, built-in, NOT kanban-related in
  name or scope" but does not give a name. Working proposal: `fail_task` (agent core); a
  kanban-specific API endpoint is not implied. The kanban-facing effect is entirely via the
  server-loop transitions (§6.5).
- **N2 — "testing" vs "test" (RESOLVED in v5).** The new kanban status is `testing` (user
  ROUND-3 ruling: "The new Kanban status should be testing"). Renamed everywhere in v5: status
  enum, transition table, `workflow_step` values, fail-tool matrix, schema. No longer an
  ambiguity.
- **N3 — R10.** The v3 task brief references rulings "R1–R10" but no R10 content was supplied.
  Treated as a no-op; no design change attributable to R10.
- **N4 — v2 `workflow_config` JSONB vs the R9 `workflows` table (RESOLVED in v5).** The shared
  `workflows` table is the source of role config; `kanban_tasks.workflow_id` (FK) references it
  and the task reads the limits from the referenced workflow (user ROUND-3 ruling: "The workflow
  is referenced in the task, to know the limits"). Per-task live state stays in `workflow_state`
  (executions). Shared-definition edits are rejected mid-flight (§7.2 edge cases).
- **N5 — retries in the role config (RESOLVED in v5).** Retries live in
  `workflows.config.<role>.retries` (user ROUND-3 ruling: "The retries are defined in the
  workflow"). The task tracks `workflow_state.executions[<step>]` (incremented by 1 after each
  run) and compares against the workflow limit.
- **N6 — fail tool targeting `review` with no reviewer.** R6's "create thread + seq-0" applies to
  configured roles; per R5, `review` is valid without a reviewer (manual state, `thread_status=NULL`,
  NO thread). Assumed the no-thread manual path for that case (F3).
- **N7 — `threads.task_type`/`task_id` backfill.** `threads.task_id` already exists (kanban link)
  and `schedule_task_id` covers cron; R7's `task_type` discriminator needs a best-effort backfill
  from existing seq-0 msg_type/subtype values. Assumed: `task_type='kanban'` for rows with
  `task_id` set, `'cron'` for `schedule_task_id`-only rows; NULL for ambiguous rows.
- **N8 — auto-comment wording.** R8 provides templates for failure/interruption/retry-exhausted;
  the exact text for F4 (fail tool targeting `blocked` directly) and R5 invalid-target comments
  is derived from R8's pattern ("…Moving kanban task to 'blocked' status…"). Exact copy to be
  finalized at implementation.

**Resolved in v5 (ROUND-3 user rulings — N9–N14):**
- **N9 — "last message and its type" (RESOLVED).** The last message is simply the **last message
  in the thread** — the `messages` table already has a type field (`msg_type`), so the type is read
  from there (no new derivation logic). The fail-task tool's Error-type message is just a message
  with its type set accordingly; the summary is the thread's normal final message.
- **N10 — scope of "recent threads" (RESOLVED — prompt-plugin concern).** How many threads, the
  time window, and the token budget are **defined by the `prompt_generate` tool**, which may be
  provided by EXTERNAL plugins. For the builtin prompt plugin, use a sensible window. The tool may
  receive a parameter indicating it is part of a workflow. Tool calls receive the thread id as a
  **meta field**. This is NOT an omniagent-core concern.
- **N11 — executor "start from where it ended" (RESOLVED — prompt-plugin concern).** Resume
  semantics (context-only vs stateful) are decided in the `prompt_generate` plugin tool; external
  plugins may choose differently. Not a concern of the omniagent core code.
- **N12 — cron threads in the task-id lookup (RESOLVED — yes).** The lookup applies to cron
  threads too. Again handled in the prompt plugin, not the omniagent core code.
- **N13 — step may NOT fail itself; fail-target restrictions (RESOLVED).** A workflow step should
  NOT fail defining ITSELF to run again — that only happens in interrupted tasks (I1 rerun), never
  explicitly via the fail tool. An executor fail must not define itself either; defining EMPTY
  returns to itself (in practice like defining itself, but not explicitly). Only `blocked` should
  be definable by the executor (e.g. an impossible task). So the effective fail-tool target rules:
  executor → empty (⇒ self/running) or `blocked` only; reviewer → `running`/`testing`/`blocked`
  (never `review`); tester → `running`/`blocked` (never `testing`). `kanban_review_task`/`POST
  /review` retained for MANUAL/API use only.
- **N14 — where tester-created automated tests live (RESOLVED — project-specific).** That is
  project-specific; some projects may not even have automated tests. It can be defined in the
  **template or the project's AGENTS file**, and the template should be GENERIC, saying to find
  where to include tests in the project (which may already have existing tests). No new storage in
  omniagent.

---

## 14. Verification Notes (honesty)

- All §2 facts marked [VERIFIED] were read from source in the v1 thread (kanban plugin, actions
  dispatcher, `kanban_updater.rs`, `threads.rs`, `server/kanban.rs`, `db-migrations`, dashboard
  libs, live DB). **v2/v3/v4 reused these facts without re-reading sources** — the user rulings
  (R1–R9, R11–R13) alter the *target design*, not the verified current-system facts; no fact
  claimed in §2 was changed by a ruling. `kanban_tasks.planning_mode` and
  `threads.task_id`/`schedule_task_id` already exist per §2.5 — R7/R9/R12 build on them rather
  than adding duplicates.
- **Sections changed by R1–R10 (v3):** §1 exec summary (R1–R9), §3 feature spec (R9), §4 status
  machine + transition table (R1–R6, R8), §5 schema (R1/R4/R6/R7/R9), §6 thread execution
  (R2/R3/R7/R8/R9), §7 failure/retry (R2/R3/R6), §8 review/tester (R2/R5/R6), §10 API/dashboard
  (R4/R6/R7/R8/R9), §11 backward compat (R1/R4), §12 implementation plan (R1–R9), §13 open
  questions (Q1/Q6/Q7/Q8 resolved; N1–N8 added), §14 (this section).
- **Sections changed by R11–R13 (v4):** §1 exec summary (role-aware context, task-id threads,
  kanban-history context — items 5/6/7/11/12), §2 verified facts (R12 task_id-on-all-steps,
  R13 history-as-context notes), §3 feature spec (role instructions — executor as-is / tester
  tests-only / reviewer review-only), **new §3.5 Role-Aware Agent Context**, §4 status machine
  (R12 reviewer decision mechanism — rows 13–16 + note; F1–F5), §5 schema (R12 task_id on all
  step threads; R13 comment in context), §6 thread execution (R12 task_id on every step thread),
  §7 failure/retry (R12 reviewer fail-tool targets), §8 review/tester (R11/R12 mechanism
  rewrite), §10 API/dashboard (**new §10.4 `prompt_generate` workflow context**, R13 history
  surface, manual-only decision buttons), §11 backward compat (executor default role, existing
  task_id threads), §12 implementation plan (**new Phase 3b**, Phase 4 update, v4 test-matrix
  additions), §13 (N9–N14 added), §14 (this section).
- **Resolved open questions:** v2 §13 Q1 (R5), Q6 (R6), Q7 (R3), Q8 (R4).
- **New ambiguities deliberately flagged, not silently resolved:** §13 N1–N8 (v3) and **N9–N14
  (v4 — last-message definition; recent-threads scope; executor resume semantics; cron scope;
  reviewer fail-tool target set + `kanban_review_task` fate + step display mapping; created-test
  storage)**.
- The **exact call site** of `update_kanban_status` inside the agent's terminal-finalization
  path (main_loop/executor) was not pinned to a line number in the v1 thread (file is 72 KB; the
  call is in the completion path). Phase 3 must confirm it before wiring the server loop.
- The thread-start site that flips `thread_status` ('scheduled' → 'running') likewise needs
  line-level confirmation in Phase 3.
- **Consistency checks performed for this v4 write:** no remaining claims that the tester
  implements the task (§3/§8.2 say "does NOT implement"); thread-access rules present for all
  three roles (§3.5.1 — executor: previous task threads; tester: executor thread + all recent;
  reviewer: executor + tester threads + all recent); `prompt_generate` described WITH task-id
  lookup (§3.5.2/§10.4); reviewer success = normal summary completion + status success → done,
  reviewer issue = fail-task tool → `running`/`testing`/`blocked` (§4.2/§8.1); recent
  `kanban_history` entries (status changes + comments) surfaced in context (R13 — §3.5.3/§10.4);
  no `ready` read-mapping/grace period (§11, R4); no kanban-specific fail/test tool names (§8.1,
  R6); no "legacy NULL = running" claims (§4.1/§5/§11, R1).
- **Process note (v4):** the research file is gitignored (working tree only). During the v4
  update the file was rewritten in place; the v3 text was re-assembled from the DB-stored
  `filesystem_write` tool calls of the v3 thread (messages table) before the v4 rewrite, so all
  v3 content is preserved in v4 (with v4 edits). No sources were re-read; no git operations were
  performed.
- **Sections changed by v5 (ROUND-3 rulings):** header/changelog (v5), §1 exec summary (thread_status /
  testing / executions / N9–N14), §3.5 role-aware context (N10/N11/N12 prompt-plugin concerns),
  §4 status machine + transition table + R12 note + fail-task matrix (F0 empty-self; F1/F2/F3
  caller restrictions per N13; `testing` status), §5 schema (`thread_status` rename;
  `workflow_state.executions`; retries in `workflows.config` — N4/N5 resolved), §6.5 atomic
  transitions (executions increment; run N/M comment templates), §7.2 retry guards (executions
  counter vs workflow limit), §10.4 `prompt_generate` (N9 last-message/msg_type; N10/N11/N12
  prompt-plugin scope), §13 (N2/N4/N5/N9–N14 resolved; remaining N1/N3/N6/N7/N8 open), §14 (this
  section).
- **v5 consistency checks:** `run_status` → `thread_status` (only the changelog mentions the old
  name); status `test` → `testing` everywhere (enum, transitions, workflow_step, fail matrix,
  schema); `retries_remaining`/decrement removed (executions counter + workflow limits); a step
  may NOT fail itself (executor → empty/self or blocked only; reviewer → running/testing/blocked;
  tester → running/blocked); N9–N14 marked resolved with user rulings; N2/N4/N5 resolved.
- This document is a design proposal; nothing has been implemented. The user-required location
  was honored (`/opt/workspace/omni-stack/data/research/workflow-role-based-kanban.md`).
