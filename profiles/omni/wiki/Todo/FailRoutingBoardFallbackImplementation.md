# Fail-Threat Routing: Board Fallback for Workflow Resolution — Implementation

**Status:** Todo (task 17 — LAST in the serial chain, after models.yml task 16)
**Date:** 2026-08-19
**Scope:** omniagent (src/agent/fail_thread.rs + workflow resolution)

## Goal

Fail-thread routing must resolve the workflow the same way the DISPATCH path
does — including the **board fallback** (`boards.yml`: task.board → workflow)
— so reviewer/tester fails on board-based tasks route to executor rework /
re-test instead of `blocked`.

## Verified facts (do not re-derive — live evidence 2026-08-19)

- **The bug**: `src/agent/fail_thread.rs` resolves the workflow ONLY from
  `kanban_tasks.workflow_id`:
  - engine_transition (~line 830-847): `let wf_id = task.workflow_id.as_deref();
    has_wf = wf_id.is_some(); workflow = wfs.workflows.get(id)` — no board fallback.
  - manual-review path (~line 290-297): same — `task.workflow_id` only.
- Board-based tasks have `workflow_id = NULL` at the task level (verified:
  task_18cd3920aeeea608 → board=omnidev, workflow_id=None, channel_id=None;
  the BOARD carries workflow/channel/profile/plan defaults in boards.yml, and
  the DISPATCH path resolves them). So at fail time `has_wf=false`,
  `workflow=None`, `has_executor_role=false` → `route_fail_tool` F1 ("running")
  → `!has_wf` → `blocked_or_review(true, false)` → **blocked**.
- Live occurrence: reviewer thread 51 called `builtin_fail-thread` with
  `workflow_step="running"` (correct F1 executor-rework request). Engine log:
  `fail-thread: thread 51 ended as FAILED (workflow_step='running',
  transition=no re-run thread (blocked or non-workflow task))`; kanban_history
  #127: "Task failed in thread #51. Moving kanban task to 'blocked' status due
  to no executor role in workflow for status review". The task was BLOCKED
  instead of creating a new executor thread.
- Impact: on board tasks, EVERY fail route is affected — reviewer F1 (running)
  and F2 (testing), tester F0/fail, executor F0 — all land on `blocked` (or
  `review` with review_on_fail=true, which is also wrong: the reviewer should
  be able to rework). Only the explicit reviewer `blocked` (F3) behaves.
- The dispatch path DOES resolve the board fallback (task → board → workflow →
  channel → profile → settings resolution order) — the fail router diverges.
- workflows.yml `omniagent-dev` DOES define roles `executor/tester/reviewer`
  (config/workflows.yml:19-32) — the workflow exists; it just wasn't resolved.

## Requirements

1. **Shared workflow resolution**: extract ONE helper (e.g.
   `resolve_workflow_id(data_dir, task) -> Option<String>` /
   `resolve_workflow(data_dir, task) -> Option<WorkflowDef>`) that applies the
   SAME resolution as dispatch: `task.workflow_id` → else
   `boards.yml[task.board].workflow` → else None. Use it in engine_transition
   AND the manual-review path AND anywhere else fail routing resolves the
   workflow. The dispatch path should reuse it too (no divergence).
2. `has_wf` = resolved workflow id is some; role checks (`executor`/`tester`/
   `reviewer`), retry limits, review_on_fail, auto_approve all read the
   resolved workflow.
3. **Regression tests** (fail_thread.rs):
   - board task (workflow_id NULL, board with workflow: omniagent-dev) +
     reviewer fail `running` → status `running` + NEW executor thread
     (task back to running, not blocked).
   - board task + reviewer fail `testing` → new tester thread.
   - board task + tester fail (F0, no step) → executor re-run (or review per
     review_on_fail semantics — match the non-board behavior exactly).
   - board task + reviewer explicit `blocked` → blocked (F3 unchanged).
   - NON-board task (workflow_id set) → all existing behavior unchanged
     (no regression).
   - unit + integration (dispatch→fail→rework round trip on a board task).
4. **Live verification**: create/dispatch a board task through a deliberate
   reviewer rejection → verify it routes to executor rework (task running +
   new executor thread), NOT blocked. Also verify kanban_history comment no
   longer says "no executor role in workflow" for board tasks.
5. Keep the block_reason accurate: "no executor role in workflow" should only
   appear when the RESOLVED workflow truly lacks the executor role.

## Non-goals / DO NOT CHANGE

- Do NOT change the F0-F4 matrix semantics or review_on_fail/auto_approve
  behavior — only the workflow RESOLUTION (board fallback) changes.
- Do NOT change the dispatch path's resolution order.
- Do NOT touch boards.yml content or task creation.

## Verification gates

- cargo check / clippy -D warnings / cargo test / fmt --check clean.
- deploy.py dev passes (omni-deployer dev-flavor).
- Live smoke (omnidev): board task reviewer-reject → executor rework thread
  created (task running); board task reviewer explicit blocked → blocked;
  non-board task fail → prior behavior.
- kanban_history on a board-task rework shows "Creating thread #N" for step
  'running', not the "no executor role" block.

## Deliverable

omniagent commit(s) + SHAs + test/live evidence. Standing release loop: tasks
→ deploy.py dev → main → stable (never push stable while omnistable tasks
run). NOTE: this bug is live in the running omnistable binary — until the fix
ships, reviewer/tester fails on board tasks will block; recover manually via
the blocked-task recipe (REDISPATCH NOTE + PATCH status → running).
