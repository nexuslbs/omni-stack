# Workflow Implementation Plan

**Status:** Plan of action — NOT yet implemented
**Source design:** `data/research/workflow-role-based-kanban.md` (v6 — NOT versioned; this page is
the versioned summary of everything decided)
**Date:** 2026-08-04
**Scope:** omniagent role-based kanban workflow — executor / tester / reviewer pipeline with
per-role retries, server-loop atomic transitions, role-aware prompts, dashboard workflows page.

This page is the implementation blueprint. The full research doc (working-tree only, per the
user's rule that `data/` is never versioned) is the source of truth for the rationale; this page
captures every decision that was made so implementation can proceed without re-deriving anything.

---

## 1. Goal

Turn the current single-actor kanban flow (dispatcher → executor thread → `review` → manual
`done`) into an optional **3-role pipeline**:

- **executor** (required) — runs the task as-is
- **tester** (optional) — runs/creates tests, never implements
- **reviewer** (optional) — reviews execution + tests, never implements

Each step has its own **retry limit** (default 0 = 1 run). When no workflow is attached
(`workflow_id` NULL), behavior must be byte-for-byte identical to today.

---

## 2. Key decisions (all resolved — do not re-open)

| # | Decision | Value |
|---|----------|-------|
| D1 | Retries are the ONLY cap | per-step retry count; re-entry past limit → `blocked` |
| D2 | Reviewer loop bounded by retries only | no extra loop protection |
| D3 | History comments | `kanban_history.comment` column; surfaced in context |
| D4 | `ready` removed | replaced by `thread_status` (NULL/scheduled/running); NULL = resting |
| D5 | Tester fails on ANY single test error | one error → back to executor |
| D6 | Reviewer always verifies work + tests | review-only role |
| R1 | `thread_status` semantics | NULL = no in-flight step thread; scheduled = thread created; running = picked up |
| R2 | Interruption reruns consume that step's retry | incl. tester/reviewer steps (I1) |
| R3 | Pre-start/external skips consume NO retry | channel-closed / no-provider / thread-creation failure |
| R4 | `ready` dropped, no compat | migrate rows, reject future writes |
| R5 | Invalid target → `blocked` + auto comment | `review` valid without reviewer (manual state); `testing` without tester is invalid |
| R6 | Failure signal = generic built-in tool | **`fail-thread`** (full `builtin_fail-thread`) — NOT kanban-named |
| R7 | Threads carry workflow fields | `workflow_id`, `workflow_step`, `task_type`, `task_id` |
| R8 | Engine transitions are ONE DB transaction | thread + seq-0 + status/thread_status + history comment |
| R9 | Workflows are dashboard-defined entities | `workflows` + `workflow_roles` tables; precedence Workflow > task > channel > global |
| R10 | (no content supplied — no-op) | flagged §13 N3 |
| R11 | Tester/reviewer never implement | role instructions in prompt |
| R12 | Reviewer decision via completion/fail mechanism | approve = normal completion → done; issue = fail-thread tool |
| R13 | Recent kanban_history surfaced in prompt | error-loop awareness |

### N-ambiguities (all resolved)

| # | Question | Resolution |
|---|----------|------------|
| N1 | fail tool name | **`fail-thread`** / **`builtin_fail-thread`** |
| N2 | `testing` vs `test` | **`testing`** |
| N3 | R10 | no-op (confirmed OK) |
| N4 | shared workflows table | confirmed — `kanban_tasks.workflow_id` FK |
| N5 | where retries live | Rust `workflows.roles.<role_key>.retries`; DB **`workflow_roles` table**, UNIQUE (workflow_id, role_key) |
| N6 | fail targeting `review` | **NEVER** — only reviewer-interrupted thread re-runs review (I1, has a reviewer) |
| N7 | task_type backfill | **NO backfill** — omniagent not in production; fields stay empty for existing rows |
| N8 | auto-comment wording | **prompt-plugin concern** — builtin prompt plugin defines best wording; engine stores transition facts |
| N9 | "last message and type" | last message in thread; type = `messages.msg_type` |
| N10 | recent-threads scope | prompt-plugin concern (builtin = sensible window; thread id as meta field) |
| N11 | executor resume | prompt-plugin concern (context-only assumed) |
| N12 | cron threads in lookup | yes — prompt-plugin concern |
| N13 | step may not fail itself | executor → empty/self or `blocked` only; reviewer → running/testing/blocked; tester → running/blocked; **v6: no one → review** |
| N14 | where tester-created tests live | project-specific (template or AGENTS file; generic template) |

---

## 3. Status machine

`valid_statuses = ["backlog", "todo", "running", "testing", "review", "blocked", "done"]`
(`ready` removed — R4; `testing` added — D5). `thread_status ∈ {NULL, 'scheduled', 'running'}`.

### Transition table

| # | From | To | Trigger |
|---|------|----|---------|
| 1 | `todo` | `running` | Dispatcher (executor step) |
| 2 | `running` | `todo` | Executor non-success terminal OR empty fail target (F0, implicit self); retry-guarded → `blocked` at limit |
| 3 | `running` | `running` | Interruption → rerun same step (I1), consumes executor retry |
| 4 | `running` | `testing` | Executor success + tester defined → server loop creates test thread |
| 5 | `running` | `review` | Executor success + no tester → review (manual or reviewer thread) |
| 6 | `running` | `blocked` | Executor retry limit reached (guard before start) |
| 7 | `testing` | `review` | Tester pass + reviewer defined → review thread; no reviewer → manual review |
| 8 | `testing` | `todo` | Tester rework/failure → executor (consumes executor retry) |
| 9 | `testing` | `todo` | ANY single test error (D5) → executor |
| 10 | `testing` | `testing` | Tester interruption → rerun (consumes tester retry) |
| 11 | `testing` | `testing` | Tester explicit retry (D1) |
| 12 | `testing` | `blocked` | Tester retry limit reached (guard) |
| 13 | `review` | `done` | Reviewer approve = normal completion + summary message (status success); or manual/API |
| 14 | `review` | `todo` | Reviewer rework — fail-thread `metadata.kanban_status='running'` |
| 15 | `review` | `testing` | Reviewer retest — fail-thread `='testing'`; no tester → `blocked` + auto comment |
| 16 | `review` | `blocked` | Reviewer block — fail-thread `='blocked'` (no thread) |
| 17 | `review` | `review` | Reviewer interruption → rerun (consumes reviewer retry) |
| 18 | `review` | `review` | Reviewer explicit retry (D1) |
| 19 | `blocked` | — | Terminal, no thread ever |
| 20 | `done` | — | Terminal, no thread ever |

### Fail-task tool matrix (`builtin_fail-thread`, server-loop handled)

| # | `metadata.kanban_status` | Behavior |
|---|--------------------------|----------|
| F0 | *(empty)* | Executor default — returns to executor step itself (task → `todo`), guard permitting |
| F1 | `running` | Guard → increment `executions['running']` → task `todo` → new executor thread. Callers: tester (rework), reviewer (rework). NOT executor itself |
| F2 | `testing` | Guard → increment `executions['testing']` → task `testing` → new test thread. Caller: reviewer (retest). NOT tester itself; no tester → `blocked` |
| F3 | `blocked` | Task → `blocked`, NO thread, `thread_status` NULL. Any role |
| F4 | any other value | Task → `blocked` + auto comment (invalid target). **`review` falls here (N6)** |

**v6 (N6):** `review` is NOT a valid fail target for ANY role. The only non-successful path that
re-runs a review is a **reviewer-interrupted thread** (I1, row 17) — which has a reviewer by
definition. (v5's F3 `review` target removed; matrix renumbered.)

### Interruption matrix (I1)

| Step | Behavior |
|------|----------|
| running/testing/review | Rerun SAME step: status unchanged, `thread_status='scheduled'`, new thread + seq-0 (parent = interrupted thread). Consumes that step's retry → increments `executions[<step>]`; at limit → `blocked`, no thread |

### Safety rules

- Guard checks `executions[<step>]` against the workflow limit BEFORE any re-entry — no thread is
  created when the limit is reached.
- `blocked`/`done` never have threads; `thread_status` NULL.
- A step thread must be terminal before the next transition.
- Every engine transition is ONE DB transaction (thread + seq-0 + status/thread_status + history
  comment — R8).
- Every transition stores an optional `comment` (D3).

---

## 4. Schema changes

All in the existing **declarative single-phase** migration style: `CREATE TABLE IF NOT EXISTS` /
`ALTER TABLE … ADD COLUMN IF NOT EXISTS` + idempotent UPDATEs; no versioned migration runner.

### `workflows` (new)
- `id` UUID PK, `name` TEXT NOT NULL, `created_at`, `updated_at`. Workflow-level identity only.

### `workflow_roles` (new — v6 N5)
- `id` UUID PK, `workflow_id` UUID NOT NULL REFERENCES `workflows(id)` ON DELETE CASCADE
- `role_key` TEXT NOT NULL — `'executor'` | `'tester'` | `'reviewer'`
- config columns: `name`, `provider`, `model`, `planning_mode`, `template`, `retries` (INT,
  default 0)
- executor REQUIRED, tester/reviewer OPTIONAL
- **UNIQUE (`workflow_id`, `role_key`)** — at most one config row per role per workflow
- Rust representation: `workflows.roles.<role_key>.retries` — NOT `workflows.config` JSONB (gone)

### `kanban_tasks` (add columns)
- `workflow_id` UUID NULL — REFERENCES `workflows(id)`; NULL = today's behavior
- `thread_status` TEXT NULL — `'scheduled'` | `'running'` | NULL = resting;
  `CHECK (thread_status IS NULL OR thread_status IN ('scheduled','running'))`
- `workflow_state` JSONB NULL — `{"executions": {"running": N, "testing": M, "review": K}}`
  - executions counter, NOT retries-remaining; increment by 1 AFTER the step's thread runs
  - guard compares against the workflow's configured limit for that role
- `ready` migration (R4): `status='ready'` → `status='running'` + `thread_status='scheduled'`
  when a pending thread exists, else NULL; future `ready` writes REJECTED at validation

### `threads` (add columns)
- `workflow_id` UUID NULL — REFERENCES `workflows(id)`
- `workflow_step` TEXT NULL — `'running'` | `'testing'` | `'review'` (display names
  executor/tester/reviewer are a prompt-level mapping)
- `task_type` TEXT NULL — `'kanban'` | `'cron'` (discriminator for `task_id`)
- `task_id` — existing column, generalized; set on ALL workflow step threads (R12) so
  `prompt_generate` can find a task's full step-thread history
- **NO backfill (v6 N7)** — omniagent not in production; existing rows keep fields empty

### `kanban_history` (add column)
- `comment` TEXT NULL — optional comment on any transition (D3); auto for `blocked` (R5/R8);
  surfaced in agent context (R13)

### Migration order
1. `workflows` table
2. `workflow_roles` table
3. `kanban_tasks` columns (+ `ready` migration, R4)
4. `threads` columns (**no backfill — v6 N7**)
5. `kanban_history.comment`

---

## 5. Thread execution model

- **Executor step (`running`)**: dispatcher-created thread (existing); `workflow_id` +
  `workflow_step='running'`; `task_id` = kanban task id. Re-entries (rework/fail/interruption) are
  new dispatcher threads via `todo` (row 2) or I1 reruns (row 3).
- **Test step (`testing`)**: server-loop-created at executor completion when a tester is defined
  (row 4, R8); `parent_id` = executor thread; `workflow_step='testing'`; `task_id` = kanban task
  id; seq-0 cause message; `thread_status='scheduled'`.
- **Review step (`review`)**: server-loop-created at tester completion (row 7) or at executor
  completion with no tester (row 5); `parent_id` = previous step thread;
  `workflow_step='review'`; `task_id` = kanban task id; `thread_status='scheduled'`.
- Every step thread is picked up by the omniagent loop when its channel is free (per-channel
  serial execution) → `thread_status='running'`.

### Provider/model per role (R9)
Role config → task fields → channel fields → global defaults. An explicit model is honored ONLY
when the role's provider is ALSO explicitly defined. Executor falls back to today's chain.

### Planning mode / template (R9)
Role planning_mode → kanban task planning_mode → channel planning mode → None (None ≠ Off).
Kanban task `template` takes priority over workflow role `template`.

### Channel closure / deletion (step-aware, §6.4)
- **Pending step thread** (`thread_status='scheduled'`, never started) → task returns to the
  step's PRIOR status; **no retry consumed (R3)**.
- **Running step thread** (`thread_status='running'`) → interrupted mid-flight → step RE-RUN (I1)
  consuming that step's retry (R2) when channel recovers, or `blocked` when exhausted.

---

## 6. Retry semantics (v5 executions counter + v6 N5 placement)

- **Limits** live in `workflow_roles.retries` per role (Rust:
  `workflows.roles.<role_key>.retries`); the task references the workflow via `workflow_id`.
- **Task tracks `executions`** — number of times each step has RUN, not a decrementing counter.
- **Increment**: after running the step's thread, increment `executions[<step>]` by 1 (same
  transition transaction, R8).
- **Guard**: before sending a task to a step again, compare `executions[<step>]` to the limit; at
  limit → `blocked` (+ auto comment), step NEVER starts (no thread).
- **Interruption reruns consume the step's retry (R2)** — incl. tester/reviewer.
- **Pre-start/external skips consume NO retry (R3)** — channel closed at thread creation, no
  provider, thread-creation failure → task returns to prior state without incrementing.
- **No double transitions** — guard + atomic transaction prevent concurrent sends.
- **Mid-flight edit rejection** — reject changes to `workflow_id` / role config while status ∈
  {running, testing, review}.

---

## 7. Roles & prompts (R11–R13)

### Role instructions
- **Executor**: run the task as-is (default for no-workflow tasks); sees previous task threads.
- **Tester**: run/create tests, NEVER implement; sees executor thread + all recent.
- **Reviewer**: comprehensive review of execution + tests, NEVER implement; sees executor + tester
  threads + all recent.

### `prompt_generate` workflow-context block (R12/R13)
1. **Thread lookup by task id**: `SELECT id, workflow_step FROM threads WHERE task_id = <task>
   AND task_type='kanban' ORDER BY id` (cron: `task_type='cron'` — N12). Both handled in the
   prompt plugin, not omniagent core.
2. **Per-thread entry**: `{thread_id, workflow_step (executor|tester|reviewer — display mapping),
   last_message, last_message_type}` — last message = LAST message in thread; type =
   `messages.msg_type` (N9). Normally the thread SUMMARY (success) or the FAIL message (Error-type
   from `builtin_fail-thread`).
3. **Recent `kanban_history` entries**: last N status changes + comments so the agent understands
   WHY it is being run again. Scope = prompt-plugin decision (N10).
4. **Role instruction block** per `workflow_step` + thread-access rules (R11).

**Prompt-plugin-owned (NOT core):** recent-threads window/token budget (N10), executor resume
semantics (N11), cron scope (N12), auto-comment wording (N8). Core guarantees the data source only.

---

## 8. API & dashboard

### HTTP API (`src/server/kanban.rs`)
- `VALID_STATUSES` → `["backlog","todo","running","testing","review","blocked","done"]`; `ready`
  rejected (R4).
- `POST /review` retained for MANUAL/API use: `decision ∈ {approve, rework, retest, block}` +
  optional `comment`; server-side target validation (R5) + retry guards (D1/R2). Reviewer AGENT
  does not call it (R12).
- `GET /kanban/tasks/{id}/history` — data source for R13 context, now including `comment`.

### MCP tools (kanban plugin)
- `kanban_update_task` — validates new status list; `ready` rejected.
- `kanban_review_task` — MANUAL/API only (R12).
- **`builtin_fail-thread`** — built-in agent core, NOT kanban-specific (R6); `metadata.kanban_status`
  handled by server loop (§6.5 of research).

### Dashboard (`omni-dashboard`)
- 7 columns: backlog, todo, running, testing, review, blocked, done; labels from STATUS_LABELS.
- Manual review decision buttons (approve/rework/retest/block + comment) = manual path only.
- History page renders `comment`.
- **Workflows page (R9)**: CRUD — name in `workflows` + per-role fields written as
  `workflow_roles` rows (v6 N5); precedence UI hints.
- Kanban task `planning_mode` → channel planning mode → None.

---

## 9. Phased implementation plan

| Phase | Scope | Key work |
|-------|-------|----------|
| **0** | Schema + migration | §4 DDL (`workflows` + `workflow_roles`, kanban_tasks cols, threads cols, kanban_history.comment); `ready` migration (R4); **no task_type backfill (N7)** |
| **1** | Status validation + dashboard columns | new status lists everywhere (§8); `ready` rejected |
| **2** | Generic fail tool + metadata | built-in `fail-thread`/`builtin_fail-thread` (N1) ending thread FAILED with Error-type last message; `metadata.kanban_status` plumbing |
| **3** | Server-loop atomic transitions + retry guards | R8 transaction; guard (D1/R2/R3); interruption reruns (I1); fail-tool routing F1–F4 (**no `review` target — N6**); no thread on exhaustion |
| **3b** | Role-aware prompt context | `prompt_generate` workflow-context block (§7): thread lookup by task_id; per-thread {id, workflow_step, last message + type}; role instructions; thread-access rules; recent history |
| **4** | Reviewer/tester decisions | tester = normal completion / fail-thread (D5/R6); reviewer per R12 — success = normal completion + summary → done; issue = fail-thread → running/testing/blocked; `kanban_review_task`/`POST /review` manual-only; target validation (R5) |
| **5** | Workflows page + precedence | CRUD (`workflows` + `workflow_roles`, N5); field precedence (Workflow > task > channel > global); planning_mode semantics |
| **6** | Recovery hardening | step-aware channel closure/deletion (§5) |
| **7** | Docs/tests | wiki + CHANGELOG; dashboard polish |

### Phase 3 implementation confirmations (from research §14)
- Pin the exact call site of `update_kanban_status` inside the agent's terminal-finalization path
  (main_loop/executor) before wiring the server loop.
- Pin the thread-start site that flips `thread_status` ('scheduled' → 'running').

---

## 10. Integration test matrix

- No-config (existing behavior unchanged)
- Executor-only fail → blocked
- Tester flow: pass / single test error → executor / fail tool → executor / interruption → rerun
  same step consuming tester retry (R2)
- Reviewer 4-way decisions; retest without tester → blocked + auto comment (R5)
- Channel-closed-before-start → no retry consumed (R3)
- `thread_status` NULL = resting (R1); ready write rejected (R4)
- Fail-tool metadata matrix F1–F4 (**`review` target rejected — N6**)
- Server-loop single-transaction transitions (R8)
- Workflows page CRUD + precedence (R9)
- retry=1 per step, guard blocks re-entry BEFORE the step starts (no thread created)
- rework/retest consume the right budget (D1); reviewer-loop bounded (D2)
- comment persisted on transitions (D3); `thread_status` lifecycle (D4)
- Channel skip mid-test; dependency with test dep; manual override race
- `task_id` present on all step threads (R12)
- `prompt_generate` context lists step threads per task id with step + last message + type (R12)
- Reviewer approves via normal completion (summary, status success) → done (R12)
- Reviewer issue via fail-thread → running/testing/blocked with retry guards (R12)
- kanban-history context present when a task re-runs after tester failure (R13)
- Tester context shows executor thread + all recent; reviewer shows executor + tester threads (R11)
- No-workflow task = executor default role instruction (R12)

---

## 11. Definition of Done

- All phases 0–7 landed as separate PRs on `main`.
- Full integration test matrix (§10) passing against a running container.
- Dashboard workflows page CRUD works (`workflows` + `workflow_roles`).
- Role-aware prompts verified end-to-end (executor/tester/reviewer threads carry task_id;
  context block shows step history + last message + type).
- No `ready` accepted anywhere; `testing` accepted everywhere.
- `builtin_fail-thread` routes F1–F4 correctly; `review` never accepted as a fail target.
- Executions counter increments per run; guard blocks at limit with `blocked` + comment.
- Existing no-workflow tasks behave identically to before.

---

*See also: `data/research/workflow-role-based-kanban.md` (v6, working-tree only) for the full
design rationale, verified current-system facts, and version history.*
