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
- **tester** (optional) — runs/creates tests, never implements the kanban task; may implement
  automated tests, per what is defined for the test (in the template)
- **reviewer** (optional) — reviews execution + tests, never implements

Each step has its own **retry limit** (**limit = retries + 1**; default `retries` 0 → limit 1 =
one run — the first run is never a retry). When no workflow is attached (`workflow_id` NULL),
behavior must be byte-for-byte identical to today.

---

## 2. Key decisions (all resolved — do not re-open)

| # | Decision | Value |
|---|----------|-------|
| D1 | Retries are the ONLY cap; **no explicit same-step retry** | per-step retry count; re-entry past limit → `blocked`; agent never explicitly requests to re-run the same step (only interruption reruns do, transparently) |
| D2 | Reviewer loop bounded by retries only | no extra loop protection |
| D3 | History comments | `kanban_history.comment` column; surfaced in context |
| D4 | `ready` removed | replaced by `thread_status` (NULL/scheduled/running); NULL = resting |
| D5 | Tester fails on ANY single test error | one error → back to executor (`running`, new scheduled thread) |
| D6 | Reviewer always verifies work + tests | review-only role |
| D7 | `clear_executions_on_review` | workflow-level boolean (default `false`, outside roles): when `true`, an executor/tester retry-limit → `review` (running+testing executions cleared to 0) instead of `blocked`; reviewer retry-limit still → `blocked`; reviewer executions NEVER reset → loop is bounded (no infinity) |
| D8 | **Explicit stop-thread ≠ restart recovery** | `skip_recovery` (init/restart) is IMPLICIT continuation: pending/processing threads are re-scheduled (new thread, status unchanged) so the task continues from where it stopped. `POST /stop-thread` is an EXPLICIT stop: the thread is marked skipped AND the kanban task moves to `blocked` (thread_status → NULL) so the operator can later move it (e.g. to `todo`) deliberately. No re-schedule, no retry consumed, no move to `todo` automatically |
| R1 | `thread_status` semantics | NULL = no in-flight step thread; scheduled = thread created; running = picked up |
| R2 | Interruption reruns consume that step's retry | incl. tester/reviewer steps (I1) |
| R3 | Pre-start/external skips consume NO retry | channel closure/deletion (scheduled OR running thread) / no-provider / thread-creation failure → task re-scheduled (new thread, status unchanged), no increment |
| R4 | `ready` dropped, no compat | migrate rows, reject future writes |
| R5 | Invalid target → `blocked` + auto comment | `review` valid without reviewer (manual state); `testing` without tester is invalid |
| R6 | Failure signal = generic built-in tool | **`fail-thread`** (full `builtin_fail-thread`) — NOT kanban-named |
| R7 | Threads carry workflow fields | `workflow_id` (workflows.yml key string), `workflow_step`, `task_type`, `task_id` |
| R8 | Engine transitions are ONE DB transaction | thread + seq-0 + status/thread_status + history comment |
| R9 | Workflows are file-defined entities | **`workflows.yml` in OMNI_DIR** (NO DB tables); precedence workflow_role > workflow_field > task > channel > global |
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
| N4 | workflows storage | **`workflows.yml` file in OMNI_DIR** — NO workflow tables; `kanban_tasks.workflow_id` = workflow key string (no FK) |
| N5 | where retries live | **`workflows.yml`** — workflow-level `retries` default + per-role `retries` override (Rust: `workflows.roles.<role_key>.retries`) |
| N6 | fail targeting `review` | **NEVER** — only reviewer-interrupted thread re-runs review (I1, has a reviewer) |
| N7 | task_type backfill | **NO backfill** — omniagent not in production; fields stay empty for existing rows |
| N8 | auto-comment wording | **prompt-plugin concern** — builtin prompt plugin defines best wording; engine stores transition facts |
| N9 | "last message and type" | last message in thread; type = `messages.msg_type` |
| N10 | recent-threads scope | prompt-plugin concern (builtin = sensible window; thread id as meta field) |
| N11 | executor resume | prompt-plugin concern (context-only assumed) |
| N12 | cron threads in lookup | **Yes** — cron step threads are included in the task-id thread lookup (`task_type='cron'`), same as kanban; scope/window is a prompt-plugin concern |
| N13 | step may not fail itself | fail `workflow_step` = `running` or `testing` (**step keys**, NOT role names — keeps `threads.workflow_step` values), valid only if that step's role is present in the workflow; `blocked` from any step; **no one → review** |
| N14 | where tester-created tests live | project-specific (template or AGENTS file; generic template). The agent may also look at the project and find where tests are made, if not specified anywhere in the template, skill, or wiki referenced by the template, or the project AGENTS file |

---

## 3. Status machine

`valid_statuses = ["backlog", "todo", "running", "testing", "review", "blocked", "done"]`
(`ready` removed — R4; `testing` added — D5). `thread_status ∈ {NULL, 'scheduled', 'running'}`.

### Transition table

`todo` is an **initial/manual state only** — there are NO automated transitions INTO `todo` from any
step. Executor failure (non-success terminal or empty fail target) re-runs the executor step
(→ `running`, new thread, `thread_status='scheduled'`), never `todo`. The old omniagent-start
behavior that moved skipped `running` tasks to `todo` is also gone: skipped scheduled/running tasks
are **re-scheduled** (new thread, status unchanged) instead. This applies to ALL tasks (workflow and
non-workflow, kanban and cron).

| # | From | To | Trigger |
|---|------|----|---------|
| 1 | `todo` | `running` | Dispatcher (executor step) — initial/manual scheduling only |
| 2 | `running` | `running` | Executor non-success terminal OR empty fail target (F0): re-run executor step — new thread, `thread_status='scheduled'`, status stays `running`; retry-guarded → `blocked` at limit |
| 3 | `running` | `running` | Interruption → rerun same step (I1), consumes executor retry |
| 4 | `running` | `testing` | Executor success + tester defined → server loop creates test thread |
| 5 | `running` | `review` | Executor success + no tester → review (manual or reviewer thread) |
| 6 | `running` | `blocked` | Executor retry limit reached (guard before start); **unless** workflow `clear_executions_on_review: true` → row 6a |
| 6a | `running` | `review` | Executor retry limit + `clear_executions_on_review: true` → go to `review` instead of `blocked`: clear `executions[running]`+`executions[testing]` to 0 (reviewer executions untouched), create a review thread if a reviewer role exists (else manual review state, no thread), status → `review` |
| 7 | `testing` | `review` | Tester pass + reviewer defined → review thread; no reviewer → manual review |
| 8 | `testing` | `running` | Tester rework/failure → executor step: new executor thread, `thread_status='scheduled'`, status → `running` (consumes executor retry); retry-guarded → `blocked` at limit |
| 9 | `testing` | `running` | ANY single test error (D5) → executor step (same as row 8) |
| 10 | `testing` | `testing` | Tester interruption → rerun (consumes tester retry, omniagent loop handles transparently) |
| 11 | `running` | `blocked` | **Explicit stop-thread** (operator `POST /stop-thread/{id}`): thread marked skipped, task → `blocked`, `thread_status` → NULL (D8). Operator may later move to `todo` deliberately |
| 11a | `testing` | `blocked` | **Explicit stop-thread**: thread marked skipped, task → `blocked`, `thread_status` → NULL (D8) |
| 11b | `review` | `blocked` | **Explicit stop-thread** when `thread_status` ∈ {scheduled, running}: thread marked skipped, task → `blocked`, `thread_status` → NULL (D8) |
| 11c | `review` | (unchanged) | **Explicit stop-thread** when `thread_status` IS NULL (manual review state — no thread exists to stop): no-op |
| 12 | `testing` | `blocked` | Tester retry limit reached (guard); **unless** workflow `clear_executions_on_review: true` → row 12a |
| 12a | `testing` | `review` | Tester retry limit + `clear_executions_on_review: true` → go to `review` instead of `blocked`: clear `executions[running]`+`executions[testing]` to 0 (reviewer executions untouched), create a review thread if a reviewer role exists (else manual review state, no thread), status → `review` |
| 13 | `review` | `done` | Reviewer approve = normal completion + summary message (status success); or manual/API |
| 14 | `review` | `running` | Reviewer rework — fail-thread `metadata.workflow_step='running'`: new executor thread, `thread_status='scheduled'`, status → `running`; retry-guarded → `blocked` at limit |
| 15 | `review` | `testing` | Reviewer retest — fail-thread `metadata.workflow_step='testing'`; no tester role → `blocked` + auto comment |
| 16 | `review` | `blocked` | Reviewer block — fail-thread `='blocked'` (no thread) |
| 17 | `review` | `review` | Reviewer interruption → rerun (consumes reviewer retry, omniagent loop handles transparently) |
| 19 | `blocked` | — | Terminal, no thread ever |
| 20 | `done` | — | Terminal, no thread ever |

**No explicit same-step retry (D1 dropped):** the agent NEVER explicitly requests to run the same
step again. While a test/review task runs, the role may test/review. On pass → return successfully
with a summary; on failure needing a fix → go to executor (`running` + scheduled thread); on
iteration limit reached (interrupted) → the omniagent loop reruns the step transparently (rows 10/17,
I1). Same rule for the executor step: failing with an empty workflow step in practice re-runs the
executor (F0), but that is implicit, never an explicit "retry" request.

### Fail-task tool matrix (`builtin_fail-thread`, server-loop handled)

`builtin_fail-thread` carries **`metadata.workflow_step`** (NOT `kanban_status`) — meaningful only
in a workflow context (a kanban task with a workflow defined). It receives a **step key** —
`running` or `testing` — matching the `threads.workflow_step` values (NOT the role names
executor/tester, to avoid confusion with the status keys), or `blocked` to go straight to blocked;
empty = executor default (F0). `running`/`testing` are valid **only if that step's role is
present in the workflow** — otherwise → `blocked`. There is **NO `review` fail target**: an agent
can never explicitly fail to go to `review` (only a reviewer-interrupted thread may re-run review
— I1, row 17 — and that is not an explicit fail).

| # | `metadata.workflow_step` | Behavior |
|---|--------------------------|----------|
| F0 | *(empty)* | Executor default — task → `running`, `thread_status='scheduled'`, new executor thread created (guard permitting → `blocked` at limit) |
| F1 | `running` | Guard → increment `executions['running']` → task `running` → new executor thread, `thread_status='scheduled'`. Callers: tester (rework), reviewer (rework). NOT the executor step itself. Tester/reviewer role absent from workflow → `blocked` |
| F2 | `testing` | Guard → increment `executions['testing']` → task `testing` → new test thread, `thread_status='scheduled'`. Caller: reviewer (retest). NOT the tester step itself; no tester role in workflow → `blocked` |
| F3 | `blocked` | Task → `blocked`, NO thread, `thread_status` NULL. Any role |
| F4 | any other value | Task → `blocked` + auto comment (invalid target). **`review` falls here (N6)** |

**Safety rules (blocked / review):**
- Any step may target `blocked`; an invalid `workflow_step` value also goes to `blocked`.
- Going to `blocked` NEVER creates a thread — tasks in `blocked` do not run.
- Going to `review` with no reviewer also never creates a thread — that is a manual review.

**v6 (N6):** `review` is NOT a valid fail target for ANY role — there is no `review` workflow_step
value. The only non-successful path that re-runs a review is a **reviewer-interrupted thread** (I1,
row 17) — which has a reviewer by definition. (v5's F3 `review` target removed; matrix renumbered.)

### Interruption matrix (I1)

| Step | Behavior |
|------|----------|
| running/testing/review | Rerun SAME step: status unchanged, `thread_status='scheduled'`, new thread + seq-0 (parent = interrupted thread). Consumes that step's retry → increments `executions[<step>]`; at limit → `blocked`, no thread |

### Safety rules

- Guard checks `executions[<step>]` against the workflow limit BEFORE any re-entry — no thread is
  created when the limit is reached.
- `blocked`/`done` never have threads; `thread_status` NULL. **Going to `blocked` NEVER creates a
  thread** — tasks in `blocked` do not run.
- **Going to `review` with no reviewer never creates a thread** — that is a manual review.
- **No automated transition to `todo`** — `todo` is initial/manual only; failures re-schedule the
  step (`running`/`testing` + scheduled thread), and omniagent-start skips re-schedule too.
- A step thread must be terminal before the next transition.
- Every engine transition is ONE DB transaction (thread + seq-0 + status/thread_status + history
  comment — R8).
- Every transition stores an optional `comment` (D3).

---

## 4. Schema & configuration changes

DB changes use the existing **declarative single-phase** migration style: `CREATE TABLE IF NOT
EXISTS` / `ALTER TABLE … ADD COLUMN IF NOT EXISTS` + idempotent UPDATEs; no versioned migration
runner. **Workflows are NOT stored in the DB** — they live in a `workflows.yml` config file
(below); the only DB changes are the task/thread/history columns.

### `workflows.yml` (NEW — file in OMNI_DIR, NO workflow tables)

All workflow definitions live in a **`workflows.yml` file in `OMNI_DIR`** (next to the other
omniagent config). The **dashboard Workflows page reads AND writes this file** — adding a new
workflow, updating one, deleting one = rewriting `workflows.yml`. **Task execution reads the
workflow information from this file** at run time.

```yaml
workflows:
  my_workflow_1:
    profile: omni
    provider: my-provider
    model: my-model
    retries: 3
    plan_mode: "off"
    clear_executions_on_review: true
    roles:
      executor:
        plan_mode: "on"
        retries: 5
        template: executor.md
      tester:
        profile: my-other-profile
        template: tester.md
      reviewer:
        provider: my-provider-2
        model: my-model-2
        template: reviewer.md
  my_workflow_2:
    ...
```

- **Workflow key = id = name**: there is NO separate `name` field — the key under `workflows:`
  IS the workflow's id/name (e.g. `my_workflow_1`). Same for roles: the role keys are exactly
  `executor` / `tester` / `reviewer` — no role name field.
- **Workflow-level optional default fields**: `profile`, `provider`, `model`, `plan_mode`
  (planning mode), `retries`, **`clear_executions_on_review`** — each workflow may define any
  subset; anything undefined falls back down the chain (task → channel → global).
- **`clear_executions_on_review` (NEW, boolean, default `false`)**: TOP-LEVEL workflow field,
  OUTSIDE roles (not per-role). When `true`: (a) a task that reaches the executor or tester
  retry limit goes to `review` instead of `blocked`, clearing the executor+tester executions
  (see §3 rows 6a/12a + §6); (b) the reviewer executions always keep incrementing and are NEVER
  cleared; (c) the task's overall executions counter is not explicitly reset. Gives the reviewer
  power to continue a task that exceeded executor/tester retries but is being done correctly —
  while still being bounded (see §6) so no infinite loop, and the reviewer can always fail the
  task to `blocked` directly.
- **`template` is defined PER ROLE**: OPTIONAL for `executor`, REQUIRED for `tester` and
  `reviewer`.
- **Role-level overrides**: `profile`, `provider`, `model`, `plan_mode`, `retries` may also be
  defined per role; a role-level value takes precedence over the workflow-level value, with
  task/channel/global fallbacks when still undefined.
- `workflow_id` (kanban_tasks / threads) = the **workflow key string** (e.g. `my_workflow_1`),
  not a numeric FK.

### `kanban_tasks` (add columns)
- `workflow_id` TEXT NULL — the workflow key in `workflows.yml`; NULL = today's behavior
- `thread_status` TEXT NULL — `'scheduled'` | `'running'` | NULL = resting;
  `CHECK (thread_status IS NULL OR thread_status IN ('scheduled','running'))`
- `workflow_state` JSONB NULL — `{"executions": {"running": N, "testing": M, "review": K}}`
  - **the actual number of times the task has run in each workflow step** (JSON field on the
    kanban task table), NOT retries-remaining; increment by 1 AFTER the step's thread runs
  - guard compares against the workflow's configured limit for that step (role)
- `ready` migration (R4): `status='ready'` → `status='running'` + `thread_status='scheduled'`
  when a pending thread exists, else NULL; future `ready` writes REJECTED at validation

### `threads` (add columns)
- `workflow_id` TEXT NULL — the workflow key in `workflows.yml`
- `workflow_step` TEXT NULL — **STEP keys**: `'running'` | `'testing'` | `'review'` — NEVER the
  role names. **Steps ≠ Roles:** steps are `running` / `testing` / `review`; roles are
  `executor` / `tester` / `reviewer` (the `roles:` keys in `workflows.yml`). A step's display
  name IS the step name (`running` / `testing` / `review`); a role's display name IS the role
  name (`executor` / `tester` / `reviewer`) — separate concepts; the role name is NOT a display
  name for the step in general. Only where it makes sense to identify the role acting in a step
  (e.g. prompt context: "executor step") may the role name be shown — it is still the role, not
  a step display name. Role names are never stored as `workflow_step` values.
- `task_type` TEXT NULL — `'kanban'` | `'cron'` (discriminator for `task_id`)
- `task_id` — existing column, generalized; set on ALL workflow step threads (R12) so
  `prompt_generate` can find a task's full step-thread history
- **`task_type`/`task_id` are NOT necessarily workflow-related**: a cron task that generates a
  thread also populates them (`task_type='cron'` + cron task id) — today that info only lives in
  the seq-0 message type/subtype + id; the new columns make it queryable.
- **NO backfill (v6 N7)** — omniagent not in production; existing rows keep fields empty

### `kanban_history` (add column)
- `comment` TEXT NULL — optional comment on any transition (D3); auto for `blocked` (R5/R8);
  surfaced in agent context (R13)

### Migration order
1. `kanban_tasks` columns (+ `ready` migration, R4)
2. `threads` columns (**no backfill — v6 N7**)
3. `kanban_history.comment`
(`workflows.yml` needs no migration — it is a config file, not a table.)

---

## 5. Thread execution model

- **Executor step (`running`)**: dispatcher-created thread (existing); `workflow_id` +
  `workflow_step='running'`; `task_id` = kanban task id. Re-entries (rework/fail/interruption) are
  new dispatcher threads via `running` re-schedule (row 2) or I1 reruns (row 3).
- **Test step (`testing`)**: server-loop-created at executor completion when a tester is defined
  (row 4, R8); `parent_id` = executor thread; `workflow_step='testing'`; `task_id` = kanban task
  id; seq-0 cause message; `thread_status='scheduled'`.
- **Review step (`review`)**: server-loop-created at tester completion (row 7) or at executor
  completion with no tester (row 5); `parent_id` = previous step thread;
  `workflow_step='review'`; `task_id` = kanban task id; `thread_status='scheduled'`.
- Every step thread is picked up by the omniagent loop when its channel is free (per-channel
  serial execution) → `thread_status='running'`.

### Workflow role fields & precedence (R9 — workflows.yml)

Workflows are defined in `workflows.yml` (§4). Each workflow has **workflow-level default
fields** (`profile`, `provider`, `model`, `plan_mode`, `retries` — all optional) and a
**`roles:`** section (executor REQUIRED; tester/reviewer OPTIONAL). Roles may override any of the
workflow defaults and define the **`template`** (per-role only). The dashboard writes this file;
omniagent resolves the fallbacks transparently, just like it already does for the kanban task
profile:

| Field | Where it lives | Semantics / fallback chain |
|-------|----------------|----------------------------|
| **Name / id** | workflow KEY in `workflows.yml` | The key IS the name — no separate `name` field. Roles: `executor` / `tester` / `reviewer` keys are the role names |
| **Template** | per-role (`roles.<role>.template`) | OPTIONAL for `executor`, REQUIRED for `tester` / `reviewer`; precedence: role template > kanban task template > channel template > global settings; prompt mapping per §7 |
| **Profile** | workflow default OR role override | role value → workflow value → task profile → channel profile → settings profile → `"omni"` |
| **Provider** | workflow default OR role override | role value → workflow value → channel provider → default provider in settings |
| **Model** | workflow default OR role override | role value → workflow value → default model of the provider resolved after the provider fallbacks; an explicit model is honored ONLY when the provider is ALSO explicitly defined at that level |
| **Plan mode** | workflow default OR role override (`plan_mode`) | role value → workflow value → kanban task planning mode → channel planning mode → None (**None ≠ Off**) |
| **Retries** | workflow default OR role override | role value → workflow value (default 0); limit = retries + 1 (§6) |

**Precedence (ALWAYS, not just overall):** `workflow_role` > `workflow_field` > `task_field` >
`channel_field` > `global_setting`. **Resolution rule:** the field is taken from the
highest-priority source where it **EXISTS**; when the field does not exist in a given source it is
considered `None` and resolution defaults to the next source down the chain. This applies to EVERY
field resolution, not merely as a tie-break between sources that both define a value.

**Field availability:**
- The kanban task has **NO Provider/Model fields** — workflow roles MAY have them.
- Roles have **NO channel fields** — all workflow steps run in the **channel defined on the kanban
  task** (default kanban channel when none, as today). Steps never run in different channels.
- The kanban task keeps its **planning_mode** field (existing; if not present, add it) defaulting
  to none, falling back to channel planning mode → None.
- **planning_mode is NOT workflow-related** — it exists independently of workflows and must be
  implemented FIRST (before any workflow work): the **Kanban Task modal in the dashboard currently
  does NOT show the plan mode field** and must be added; if the field is missing from the
  **backend, API, or DB** it must be added there too, **defaulting to None/NULL**.

### Channel closure / deletion (step-aware, §6.4)

**Retry is NEVER consumed on channel closure/deletion** — this is a pre-start/external skip (R3),
NOT a mid-flight interruption (I1). A kanban task whose thread would be marked skipped (whether
`scheduled` or `running`) simply gets a **new thread** and the task is marked
`thread_status='scheduled'` (status unchanged). This applies to **workflow AND non-workflow kanban
tasks alike** (the normal retry guard still applies on the next actual re-entry — exhaustion →
`blocked`).

- **Pending step thread** (`thread_status='scheduled'`, never started) → **re-scheduled**: new
  thread created, status unchanged, `thread_status='scheduled'`; **no retry consumed (R3)**. (No
  move to `todo` — the old "return to prior status" behavior is replaced by re-scheduling so
  already-completed workflow steps are never re-run.)
- **Running step thread** (`thread_status='running'`, interrupted because the channel
  closed/was deleted) → the thread is marked skipped and the task is **re-scheduled** the same
  way — **NOT** an I1 mid-flight rerun: **no retry consumed, no re-run**, new thread,
  `thread_status='scheduled'`. (I1 reruns — LLM-loop interruptions that DO consume that step's
  retry (R2) — are a different case; see §6.)
- Same re-schedule rule applies to ANY task at omniagent start whose thread was marked skipped
  (scheduled or running) — re-schedule (new thread, status unchanged), for workflow and
  non-workflow (cron) tasks alike; never move to `todo`.

---

## 6. Retry semantics (v5 executions counter + v6 N5 placement)

- **Limits** live in **`workflows.yml`** — workflow-level `retries` default + per-role `retries`
  override (Rust: `workflows.roles.<role_key>.retries`); the task references the workflow via
  `workflow_id` (key string).
- **Task tracks `executions`** — number of times each step has RUN, not a decrementing counter.
- **Increment**: after running the step's thread, increment `executions[<step>]` by 1 (same
  transition transaction, R8).
- **Guard**: before sending a task to a step again, compare `executions[<step>]` to the limit; at
  limit → `blocked` (+ auto comment), step NEVER starts (no thread). **Exception:** when the
  workflow's `clear_executions_on_review` is `true`, the executor/tester limit → `review` instead
  of `blocked` (rows 6a/12a): clear `executions[running]` + `executions[testing]` to 0, keep
  `executions[review]` as-is, and let the reviewer decide (approve → done / rework → running /
  retest → testing / block → blocked). The reviewer limit ALWAYS → `blocked` (never cleared,
  never overridden) — rows 16/17 unchanged.
- **`clear_executions_on_review` semantics (D7, default `false`)**: when a task goes to `review`
  under this flag, the executor and tester executions go to 0; the reviewer executions ALWAYS
  increment and are never reset; the task's overall executions counter is not explicitly reset
  (only the per-step running/testing counters are zeroed). Boundedness: with the flag, the
  maximum total executions is `[(num_executor_executions + num_tester_executions + 1) *
  num_reviewer_executions]` — no infinite loop as long as the agent does NOT call the
  reset-executions action (`POST /kanban/tasks/{id}/workflow/executions/reset`). The reviewer
  can always fail the task to `blocked` directly (row 16) without waiting for the limit.
- **No double transitions** — guard + atomic transaction prevent concurrent sends.
- **Limit = retries + 1** — the default `retries` value is 0, so the limit is 1: the FIRST
  execution of any step always runs (the first run is NOT a retry). Every re-entry past the first
  consumes a retry; when `executions[<step>]` reaches `retries + 1` → `blocked` (no thread).
- **Interruption reruns consume the step's retry (R2)** — incl. tester/reviewer. Concretely, an
  interruption rerun (I1) **increments the task's step execution counter**
  (`executions[<step>]`) just like any other run of that step.
- **Pre-start/external skips consume NO retry (R3)** — no provider, thread-creation failure, or
  **channel closure/deletion** (pending OR running thread: the thread is marked skipped and a new
  thread is created with `thread_status='scheduled'`, status unchanged) → task **re-scheduled**
  without incrementing. **Channel closure/deletion NEVER uses retry** — even for `running`
  threads.
- **Explicit stop-thread consumes NO retry but DOES move the task to `blocked` (D8)** — this is
  the operator's deliberate abort: `POST /stop-thread/{id}` marks the thread skipped, moves the
  kanban task to `blocked` and sets `thread_status` → NULL (rows 11/11a/11b). It is NOT a
  re-schedule (that is for implicit recovery at restart/init via `skip_recovery`) and NOT an
  automatic `todo` — the operator moves it forward deliberately later (e.g. to `todo`).
- **No double transitions** — guard + atomic transaction prevent concurrent sends.
- **Mid-flight edit rejection** — reject changes to `workflow_id` / role config while status ∈
  {running, testing, review}.

---

## 7. Roles & prompts (R11–R13)

### Role instructions

The **kanban task is the SAME for all steps** — each role does its PART. Prompts carry a role
instruction plus thread context so the agent knows what to do:

- **Executor**: run the task **as-is** (the default role for kanban tasks with NO workflow).
  Must see previous task threads to: avoid error loops, **start from where it ended** on
  interrupted tasks, and fix the work after a failed review/rework.
- **Tester** (when defined): run the tests — and **may create automated tests** — but must NOT
  implement the kanban task. Must see the executor thread AND all recent threads of this task.
- **Reviewer** (when defined): do a **comprehensive review of the execution AND the tests** (when
  a tester is defined) — must NOT implement the kanban task. Must see the executor thread + tester
  threads AND all recent threads of this task. Review passes with a **successful status + a normal
  summary message**; on any issue it calls the fail tool with `metadata.workflow_step` =
  `running`, `testing`, or `blocked` (never `review` — N6; `running`/`testing` valid only if the
  target step's role exists in the workflow, else `blocked`).

### Prompt generation (built-in prompt plugin)

Prompts are generated agnostically per step, with nothing role-specific hardcoded. The
**template** defines WHAT to do (execution spec / test criteria / review checklist); the **task
description** supplies the subject. How they map to messages depends on the step:

- **Executor**: the template (when defined) is a **system message** — part of the context; the
  **task description is the user prompt**. Template OPTIONAL — when absent, the prompt is just
  the task description as user prompt (today's behavior).
- **Tester / reviewer**: the INVERSE — **template = user prompt** (drives the role: test criteria
  / review checklist); **task description = system prompt** (context about WHAT is being
  tested/reviewed). Template REQUIRED for both.

This way the prompt needs no role-specific definitions: the template drives the role, and the task
description supplies the subject. The **template is REQUIRED for tester and reviewer, and OPTIONAL
for the executor**.

### `prompt_generate` workflow-context block (R12/R13)
1. **Thread lookup by task id**: `SELECT id, workflow_step FROM threads WHERE task_id = <task>
   AND task_type='kanban' ORDER BY id` (cron: `task_type='cron'` — N12). Both handled in the
   prompt plugin, not omniagent core.
2. **Per-thread entry**: `{thread_id, workflow_step (stored step key `running`/`testing`/`review`),
   last_message, last_message_type}` — last message = LAST message in thread; type =
   `messages.msg_type` (N9). Normally the thread SUMMARY (success) or the FAIL message (Error-type
   from `builtin_fail-thread`). The step is displayed by its own step name; only where it makes
   sense to identify the role acting in the step (e.g. "executor step") may the role name
   (`executor`/`tester`/`reviewer`) be shown alongside — that is still the role, not a step
   display name.
3. **Recent `kanban_history` entries**: last N status changes + comments so the agent understands
   WHY it is being run again. Scope = prompt-plugin decision (N10).
4. **Role instruction block** per `workflow_step` + thread-access rules (R11).

**Prompt-plugin-owned (NOT core):** recent-threads window/token budget (N10), executor resume
semantics (N11), cron scope (N12), auto-comment wording (N8). Core guarantees the data source only.

### Auto-comment wording (N8 — builtin prompt plugin defines; examples)

The engine stores transition facts (thread ids, status, step, executions n/M) and the builtin
prompt plugin renders the comment. Reference wording (matches the fail-thread flow):

- **Fail → re-run another step** (e.g. tester/reviewer fail → executor/test thread):
  `"Task failed in thread #{thread_id}. Creating thread #{new_thread_id}"` — creates the new
  thread + seq-0 message, moves the kanban task to the target status (`running` for
  `workflow_step='running'`, `testing` for `workflow_step='testing'` — the allowed fail targets,
  N6; absent role → `blocked` with no thread; `review` threads are created only on normal
  completion, rows 5/7), sets `thread_status='scheduled'`, and records the comment — all in ONE DB
  transaction (R8; reuses the existing thread-creation function; also updates kanban history).
- **Interrupted → rerun SAME step** (I1): `"Task interrupted due to LLM calls iteration limit
  reached in thread #{thread_id}. Creating thread #{new_thread_id}"` — creates the new thread +
  seq-0 message, sets `thread_status='scheduled'`, comment in one transaction. **Kanban STATUS is
  NOT changed** — only `thread_status`, to run the same task step again.
- **Retry limit reached → blocked (no new thread)**: `"Task failed in thread #{thread_id}. Moving
  kanban task to "blocked" status due to retry limit reached for status {status}"` (or
  `"...interrupted due to LLM calls iteration limit reached in thread #{thread_id}. Moving kanban
  task to "blocked" status due to retry limit reached for status {status}"` for the interruption
  case). No thread is created; `thread_status` NULL.

---

## 8. API & dashboard

### HTTP API (`src/server/kanban.rs`)
- `VALID_STATUSES` → `["backlog","todo","running","testing","review","blocked","done"]`; `ready`
  rejected (R4).
- `POST /review` retained for MANUAL/API use: `decision ∈ {approve, rework, retest, block}` +
  optional `comment`; server-side target validation (R5) + retry guards (D1/R2). Reviewer AGENT
  does not call it (R12).
- `GET /kanban/tasks/{id}/history` — data source for R13 context, now including `comment`.
- **`POST /kanban/tasks/{id}/workflow/executions/reset`** (NEW) — resets the task's
  `workflow_state.executions` counters (back to 0) so the workflow steps can run again from a
  clean budget. Called by a **"Reset workflow executions" button on the Kanban Task Details
  page** (manual operator escape hatch, e.g. after fixing the cause of repeated failures).
  Idempotent; only meaningful for tasks with `workflow_id` set.
- **Workflows CRUD API (NEW)** — `GET/PUT/DELETE /workflows` (or per-workflow routes) that the
  dashboard calls to list/create/update/delete workflows; backed by reading/writing
  `workflows.yml` (validation on write: executor role required, tester/reviewer templates
  required).
- **`POST /stop-thread/{id}`** (D8, explicit stop): marks the thread skipped AND, when the
  thread is kanban-linked, moves the kanban task to `blocked` with `thread_status` → NULL —
  from `running`/`testing` always, and from `review` when `thread_status` ∈ {scheduled,
  running}. `review` with `thread_status` NULL (manual review, no thread) is a no-op on the
  task. No re-schedule, no retry consumed, no automatic move to `todo` (the operator may move
  it deliberately later).

### MCP tools (kanban plugin)
- `kanban_update_task` — validates new status list; `ready` rejected.
- `kanban_review_task` — MANUAL/API only (R12).
- **`builtin_fail-thread`** — built-in agent core, NOT kanban-specific (R6); `metadata.workflow_step`
  (step key `running`/`testing`, or `blocked`; no `review` — N6) handled by server loop (§6.5 of
  research).

### Dashboard (`omni-dashboard`)
- 7 columns: backlog, todo, running, testing, review, blocked, done; labels from STATUS_LABELS.
- Manual review decision buttons (approve/rework/retest/block + comment) = manual path only.
- History page renders `comment`.
- **Workflows page (R9)**: CRUD reads/writes **`workflows.yml`** in OMNI_DIR (workflow key =
  name; per-role fields; NO DB tables — N5); precedence UI hints. The workflow form MUST include
  the top-level **`clear_executions_on_review`** boolean field (default `false`; checkbox/switch,
  outside roles) — D7.
- Kanban task `planning_mode` → channel planning mode → None. **The Kanban Task modal MUST show
  the plan mode field** (currently missing); default None/NULL. Independent of workflows —
  implement first (DB column + backend/API field if absent, then the modal).
- **Kanban Task Details page**: "Reset workflow executions" button → calls
  `POST /kanban/tasks/{id}/workflow/executions/reset` (clears `workflow_state.executions`).

---

## 9. Phased implementation plan

| Phase | Scope | Key work |
|-------|-------|----------|
| **0a** | Kanban task `planning_mode` (NOT workflow-related) | lands FIRST, independently of workflows: DB column default NULL (if missing) + backend/API field (if missing) + **Kanban Task modal field** (currently missing); fallback channel planning mode → None |
| **0** | Schema + config | §4 DB DDL (kanban_tasks cols, threads cols, kanban_history.comment) + **`workflows.yml` parsing/validation** (NO workflow tables); `ready` migration (R4); **no task_type backfill (N7)** |
| **1** | Status validation + dashboard columns | new status lists everywhere (§8); `ready` rejected |
| **2** | Generic fail tool + metadata | built-in `fail-thread`/`builtin_fail-thread` (N1) ending thread FAILED with Error-type last message; `metadata.workflow_step` plumbing (step keys `running`/`testing`/`blocked`, no `review` — N6) |
| **3** | Server-loop atomic transitions + retry guards | R8 transaction; guard (D1/R2/R3); interruption reruns (I1); fail-tool routing F1–F4 (**no `review` target — N6**); no thread on exhaustion |
| **3b** | Role-aware prompt context | `prompt_generate` workflow-context block (§7): thread lookup by task_id; per-thread {id, workflow_step, last message + type}; role instructions; thread-access rules; recent history; **executor prompt = task description (user prompt) + template as system message (optional); tester/reviewer = template (user prompt) + task description (system prompt), template required** |
| **4** | Reviewer/tester decisions | tester = normal completion / fail-thread (D5/R6); reviewer per R12 — success = normal completion + summary → done; issue = fail-thread `workflow_step` → `running`/`testing`/`blocked` (target step's role must exist, else `blocked`; no `review` — N6); `kanban_review_task`/`POST /review` manual-only; target validation (R5) |
| **4b** | `clear_executions_on_review` (D7) | top-level workflow boolean (default false): executor/tester retry-limit → `review` instead of `blocked` (rows 6a/12a), clearing `executions[running]`+`executions[testing]` (reviewer executions NEVER cleared, reviewer limit still → `blocked`); bounded (see §6); Workflows page form field |
| **6b** | Explicit stop-thread → `blocked` (D8) | `POST /stop-thread/{id}`: thread marked skipped AND kanban task → `blocked` + `thread_status` NULL (from `running`/`testing` always; from `review` only when `thread_status` ∈ {scheduled, running}; `review` manual no-op). Distinguish from restart recovery (`skip_recovery` = implicit re-schedule). No retry consumed, no auto `todo` |
| **5** | Workflows page + precedence | CRUD against **`workflows.yml`** (N5); execution reads workflow from file; field precedence (workflow_role > workflow_field > task > channel > global); planning_mode semantics; **reset-executions API + Kanban Task Details button** |
| **6** | Recovery hardening | step-aware channel closure/deletion (§5) |
| **7** | Docs/tests | wiki + CHANGELOG; dashboard polish |

### Phase 3 implementation confirmations (from research §14)
- Pin the exact call site of `update_kanban_status` inside the agent's terminal-finalization path
  (main_loop/executor) before wiring the server loop.
- Pin the thread-start site that flips `thread_status` ('scheduled' → 'running').

---

## 10. Integration test matrix

- No-config (existing behavior unchanged)
- Executor-only fail → re-scheduled executor (`running` + scheduled thread) → blocked at limit
- **No automated transition to `todo`** — executor fail / tester rework / any-step failure never
  moves a task to `todo`; skipped tasks at omniagent start are re-scheduled (new thread, status
  unchanged), for workflow and non-workflow (cron) tasks alike
- Tester flow: pass / single test error → executor (`running` + scheduled) / fail tool `workflow_step`
  → `running` / interruption → rerun same step consuming tester retry (R2)
- Reviewer 4-way decisions; retest without tester → blocked + auto comment (R5)
- **No explicit same-step retry** — agent cannot request to re-run the same step (D1 dropped);
  only interruption reruns (I1) re-run a step, transparently
- **Channel closure/deletion NEVER consumes a retry (R3)** — pending (`scheduled`) OR running
  thread: thread marked skipped → task re-scheduled (new thread, `thread_status='scheduled'`,
  status unchanged), workflow and non-workflow tasks alike; no increment, no re-run
- `thread_status` NULL = resting (R1); ready write rejected (R4)
- Fail-tool `metadata.workflow_step` matrix F1–F4 (**`review` rejected — N6**; absent
  role → `blocked`; any invalid value → `blocked`)
- **`blocked` never creates a thread** (F3, retry-limit paths); **`review` without reviewer never
  creates a thread** (manual review)
- Server-loop single-transaction transitions (R8)
- Workflows page CRUD reads/writes `workflows.yml`; execution resolves role fields from the file (R9)
- `workflow_id` = workflows.yml key string; field precedence workflow_role > workflow_field > task
  > channel > global (always)
- Reset-executions API + button: clears `workflow_state.executions`; idempotent; no-op without
  `workflow_id`; steps can re-run from a clean budget after reset
- retries=1 per step (limit = 2), guard blocks re-entry BEFORE the step starts (no thread created)
- rework/retest consume the right budget; reviewer-loop bounded (D2)
- **`clear_executions_on_review: true`** — executor retry-limit → `review` (not `blocked`), `executions[running]`+`executions[testing]` cleared to 0, reviewer executions untouched; tester retry-limit → `review` the same way (rows 6a/12a)
- **`clear_executions_on_review: true` + reviewer retry-limit → `blocked`** as usual (reviewer limit never overridden/cleared)
- **`clear_executions_on_review` default `false` (or absent)** — executor/tester retry-limit → `blocked` exactly as before (no behavior change)
- **Boundedness under the flag** — total executions ≤ `[(executor + tester + 1) * reviewer]`; no infinite loop without calling reset-executions; reviewer can fail to `blocked` directly at any time
- Workflows page form shows/edits `clear_executions_on_review` and persists it to `workflows.yml`
- **Explicit stop-thread (D8)**: stop a `running` thread → task `blocked` + `thread_status` NULL; stop a `testing` thread → same; stop a `review` thread with `thread_status` scheduled/running → same; stop-thread on `review` with `thread_status` NULL → task unchanged (no-op); no retry consumed, no re-schedule, no auto `todo`
- **Restart recovery ≠ stop-thread**: restart with pending/processing threads → re-scheduled (status unchanged, `thread_status='scheduled'`, no retry) — the implicit continuation path stays distinct from explicit stop (D8)
- comment persisted on transitions (D3); `thread_status` lifecycle (D4)
- Channel skip mid-test; dependency with test dep; manual override race
- `task_id` present on all step threads (R12)
- `prompt_generate` context lists step threads per task id with step + last message + type (R12);
  cron threads included (`task_type='cron'`, N12)
- Reviewer approves via normal completion (summary, status success) → done (R12)
- Reviewer issue via fail-thread `workflow_step` → running/testing/blocked with retry guards (R12)
- **Prompt mapping: executor = task description (user prompt) + template as system message
  (optional); tester/reviewer INVERSE = template (user prompt) + task description (system
  prompt)**; template required for tester/reviewer
- kanban-history context present when a task re-runs after tester failure (R13)
- Tester context shows executor thread + all recent; reviewer shows executor + tester threads (R11)
- No-workflow task = executor default role instruction (R12)

---

## 11. Definition of Done

- All phases 0a, 0–7 landed as separate PRs on `main`.
- Full integration test matrix (§10) passing against a running container.
- Dashboard workflows page CRUD works against `workflows.yml` (persists across restarts; no
  workflow tables).
- Role-aware prompts verified end-to-end (executor/tester/reviewer threads carry task_id;
  context block shows step history + last message + type).
- No `ready` accepted anywhere; `testing` accepted everywhere.
- **No automated transition to `todo`** — failures re-schedule the step (`running`/`testing` +
  scheduled thread); omniagent-start skip re-schedules instead of moving to `todo`.
- `builtin_fail-thread` routes F1–F4 correctly via `metadata.workflow_step` (step keys
  running/testing/blocked); `review` never accepted; absent role → `blocked`.
- Executions counter increments per run; guard blocks at limit with `blocked` + comment (no thread).
- Reset-executions API + button work end-to-end (executions cleared, steps re-runnable).
- `clear_executions_on_review` (D7) implemented end-to-end: executor/tester limit → `review`
  with running/testing executions cleared when `true`; default `false` unchanged; reviewer
  limit always `blocked`; bounded per §6; Workflows page form field present.
- Explicit `stop-thread` (D8): task → `blocked` + `thread_status` NULL from running/testing
  always, from review only with an in-flight thread; manual-review no-op; distinct from restart
  re-schedule.
- Existing no-workflow tasks behave identically to before.

---

*See also: `data/research/workflow-role-based-kanban.md` (v6, working-tree only) for the full
design rationale, verified current-system facts, and version history.*

**⚠️ This page SUPERSEDES the research doc where they differ** — the research doc has NOT been
updated with the later decisions: workflows are stored in `workflows.yml` (NO DB tables), fail-tool
`metadata.workflow_step` uses step keys (`running`/`testing`/`blocked`), prompt mapping is inverse
for tester/reviewer vs executor, channel closure/deletion never consumes a retry (even for
`running` threads), and the retry limit is `retries + 1`.
