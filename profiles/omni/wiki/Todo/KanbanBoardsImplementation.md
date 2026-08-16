# Kanban Boards (Implementation)

**Status:** Planned
**Date:** 2026-08-16
**Scope:** omniagent (core + kanban server), omni-stack (config/boards.yml), omni-dashboard (kanban UI)

## Goal

Introduce the concept of **boards** for kanban. A board groups kanban tasks and
defines their default execution options (channel, profile, workflow, plan, …).
Every kanban task belongs to a board; tasks with no board or an invalid board
are ignored by the dispatcher and by any process that creates a thread from a
kanban task. The dashboard gets a board selector, board create/edit/delete
modals, and a move-to-board action on the task detail page.

**CRITICAL CONSTRAINT (user rule):** this feature must be developed in
**omnidev** and must NOT affect **omnistable** yet — boards are used only in
the next version. Concretely: the feature is **gated on the presence of
`config/boards.yml`**. When the file does not exist (omnistable today), all
kanban behavior must remain exactly as it is now: tasks without a board are
normal, the dispatcher works as today, and no validation is applied. When
`boards.yml` exists, the rules below apply.

## Why (verified)

- Kanban task fields today (`kanban_tasks`): `channel_id`, `profile`,
  `workflow_id`, `plan`, `template`, `priority` — a board should carry the
  same option set so it can act as the task's fallback for each.
- Executor thread creation: `dispatch_handler` (`src/server/kanban.rs:2077`)
  picks the first eligible `todo` task, creates the executor thread
  (`workflow_step "running"`), and marks the task `running` (`:2316`). The
  task's channel is resolved by `resolve_task_channel` (`src/server/kanban.rs:2083`).
  The every-minute `builtin_kanban_dispatcher` action
  (`omni-stack/config/actions.yml:25`) calls `POST /kanban/dispatch`.
- Status-change dispatch + `/redispatch` (`change_status_handler`
  `src/server/kanban.rs:713`; redispatch re-creates the role thread at
  `:2288`) are the other thread-creation paths for a kanban task. The
  in-workflow transitions (`route_completed_thread` / `create_review_thread`
  in `src/agent/kanban_updater.rs`) create tester/reviewer threads.
- Step-thread identity resolution already exists and applies the order
  **Workflow Role > thread identity** for profile/provider/model/plan/template:
  `resolve_step_identity` (`src/agent/kanban_updater.rs:374`) — role config
  (`workflows.yml` → role) wins, falls back to the parent thread's values.
  The thread identity itself comes from the task/channel resolution at
  dispatch time. **The Board layer must be inserted between the Kanban Task
  and the Channel** in this existing resolution chain (see Design §4).
- Failed-thread-on-validation already exists and must be reused:
  `fail_thread` (`src/agent/fail_thread.rs`) creates a system error message,
  marks the thread `failed`, and delivers the error back to the platform.
  `src/db/threads.rs:615` is the existing "no channel" failure path that
  creates a thread and immediately fails it; `src/db/threads.rs:100` calls
  `mark_thread_terminal(pool, thread_id, "failed")`.
- `workflows.yml` loading pattern to mirror for `boards.yml`:
  `config_path::config_path(data_dir, "workflows.yml")` +
  `WorkflowsFile::load` (`src/workflows.rs`).
- Dashboard kanban code: `src/pages/kanban.ts` (board page),
  `src/lib/kanban-board.ts` / `src/lib/kanban-detail.ts` / `src/lib/kanban-subtasks.ts`,
  `src/lib/api.ts` (API helpers), `src/lib/types.ts`. localStorage precedent:
  `src/pages/explorer.ts:298` (`explorer-collapsed`) and `:616` (`diff-full`).

## Design (executor picks cleanest implementation)

### 1. `config/boards.yml` (OMNIDIR — same dir as `workflows.yml`)

Top-level `boards:` dict; each key is the board name; the value is a dict with
the same option set a kanban task can carry:

```yaml
boards:
  main:
    channel: mattermost-stable-channel   # channel name or id (resolution below)
    profile: omni
    workflow: omniagent-dev
    plan: true
    # template, priority, … also allowed if meaningful
```

Load it lazily like workflows (`config_path` + a `BoardsFile::load`-style
loader). **Absent file ⇒ feature disabled** (see Goal). Unknown keys are
tolerated (forward compat) but should be surfaced in logs.

### 2. Task → board association

Add a nullable `board` text column to `kanban_tasks` (migration; keep it
`NULL` when no board). The create/update kanban task API accepts an optional
`board` field. Tasks created without a board are valid **only when boards.yml
is absent**; when boards.yml is present, a task with `board IS NULL` or
`board NOT IN boards.yml` is an **invalid-board task** (rules below).

### 3. Invalid-board handling (feature enabled only)

- **Dispatcher** (`POST /kanban/dispatch` eligibility scan): skip invalid-board
  tasks exactly like backlog/archived tasks are skipped today — they must
  never be promoted/dispatched.
- **Any thread-creation path from a kanban task** (dispatch, change-status
  dispatch, `/redispatch`, workflow transitions): if the task is an
  invalid-board task, **create the thread and immediately terminate it as
  `failed` with an Error message**, reusing the existing fail logic
  (`fail_thread` / the `src/db/threads.rs:615` pattern). The thread's
  `data.error` must carry a clear message (e.g. `task has no board` /
  `task board 'X' not found in boards.yml`).
- Status column moves (pure `PATCH status`) without thread creation stay
  allowed; only thread creation is blocked/failed.

### 4. Resolution order — insert the Board layer

When a thread is created for a kanban task (dispatch, move status,
redispatch, workflow transition), resolve each option in this order, falling
through to the next level when the option is not defined:

**Workflow Role > Workflow > Kanban Task > Board > Channel > Global Settings**

- **Workflow Role** — role-level fields in `workflows.yml` (profile,
  provider, model, plan_mode, template) — already implemented in
  `resolve_step_identity` (kanban_updater.rs:374). Untouched.
- **Workflow** — workflow-level fields in `workflows.yml`. Untouched.
- **Kanban Task** — task columns (`channel_id`, `profile`, `workflow_id`,
  `plan`, `template`).
- **Board** — NEW: the task's board dict from `boards.yml` (channel, profile,
  workflow, plan, …).
- **Channel** — the resolved channel's settings (`channels.yml` / channel
  row). Today this is where `resolve_task_channel` lands; it must now be
  consulted AFTER the board.
- **Global Settings** — `settings.yml` defaults.

Workflow-specific note (user rule): `workflow` exists only at the Kanban Task
and Board levels. If the task defines a workflow → use it; else the board's
workflow; else the task has NO workflow (a normal task, current behavior).

Implement this as one shared resolver used by ALL thread-creation paths
(extend `resolve_step_identity` or add a task-level resolver feeding it), so
dispatch, status-change, redispatch, and workflow transitions agree.

### 5. Dashboard (omni-dashboard)

**Kanban page (`src/pages/kanban.ts`):**
- Top bar with a **board selector** (select of all boards from `boards.yml`).
  When a board is selected, the page shows **only that board's tasks**.
- Selection is persisted in **localStorage** (e.g. key `kanban-board`).
  Going to the root kanban page redirects to the **last visited board**.
- A **"No board" option** in the selector erases the localStorage item and
  goes to the base kanban page, which shows in its content a prompt to
  choose a board or create one (and lists existing boards as choices).
- **"Create board" button** at the top → modal very similar to the kanban
  task creation modal, but for boards (name + the board's options).
- When inside a selected board, a second **"Edit board" button** → Edit Board
  modal with the same fields, plus a **delete option** with a confirmation
  that **all tasks of that board will be deleted** (delete board removes its
  tasks — decide/implement the DB cascade; keep it consistent with the
  existing task-delete behavior).

**Task detail page (`src/lib/kanban-detail.ts` / detail view):**
- A **"Move to another board"** control: a select initialized with only the
  placeholder `"Select a board..."`, listing **every other board** as options
  (excluding the task's current board), and a **Move button** that is enabled
  only when a board is selected. Moving updates the task's `board` via the
  kanban API.
- When boards.yml is absent (omnistable), the dashboard shows the kanban page
  as today (no selector, no board controls).

### 6. Tests

- Rust: boards.yml load (absent file ⇒ disabled; parse; invalid board);
  dispatcher skips invalid-board tasks; thread-creation paths fail threads
  with the error message; resolution order unit tests (task > board >
  channel > global, including workflow task-vs-board).
- Dashboard: unit tests for the selector persistence, No-board reset,
  move-task validation (button disabled until selection), board create/edit
  modal basics. Keep the existing 35-test suite green.
- Integration (omnidev only): create a board + tasks with/without board;
  verify dispatch skips invalid tasks and fails threads truthfully.

## Acceptance criteria

1. `boards.yml` absent ⇒ omnistable behavior is byte-for-byte today (no
   gating regressions).
2. `boards.yml` present ⇒ invalid-board tasks are never dispatched; any
   thread creation for them ends `failed` with a clear Error message (reusing
   existing fail logic).
3. Resolution order is exactly
   Workflow Role > Workflow > Kanban Task > Board > Channel > Global Settings
   on every thread-creation path.
4. Dashboard: board selector + localStorage redirect + No-board reset +
   create-board modal + edit-board modal (with delete + confirmation) +
   move-to-board on task details.
5. Developed and verified in omnidev only; boards.yml is NOT added to the
   omnistable config. All tests pass; cargo build/check clean; sqlx offline
   cache refreshed (prepare.py) if queries changed.

## Notes for the executor

- This is a core + dashboard feature. Verify against the live omnidev stack,
  not omnistable. Do not tear down omnistable (deploy.py dev is fine —
  it never stops omnistable by design).
- Reuse existing resolution and fail-thread machinery; do not reinvent it.
- If you find the resolution chain is scattered, consolidate it into one
  shared function used by all call sites — that is the point of §4.
