# Resolve Task Fallbacks Once (workflow/channel/profile/plan/provider/model) — Shared Resolver for ALL Task-Field Consumers

**Status:** Todo (task 17 — LAST in the serial chain, after models.yml task 16)
**Date:** 2026-08-19 (generalized from the fail-routing board-fallback bug)
**Scope:** omniagent (boards.rs / new resolution module + all consumers)

## Goal (user principle 2026-08-19 — do NOT re-litigate)

**Any place that uses kanban task fields that have fallbacks — workflow,
channel, profile, plan, provider, model, and similar — MUST resolve them
FIRST before any shallow use of the raw task fields.** The fix applies to ALL
such cases, not just the fail-thread workflow resolution. The code should be
more robust: **resolve fallbacks earlier rather than later — as close as
possible to where the values are loaded** (i.e. compute the effective values
once when the task row is loaded, and let every consumer use the resolved
values).

## Verified facts (do not re-derive — live evidence 2026-08-19)

- **Resolution order** (documented in config/boards.yml + used by dispatch):
  `Workflow Role > Workflow > Kanban Task > Board > Channel > Global Settings`.
  The board (boards.yml) carries channel/workflow/profile/plan defaults; the
  DISPATCH path resolves them.
- **The bug that triggered this**: `src/agent/fail_thread.rs` resolves the
  workflow ONLY from `kanban_tasks.workflow_id` (engine_transition ~830-847:
  `has_wf = wf_id.is_some(); workflow = wfs.workflows.get(id)`; manual-review
  path ~290-297 same). Board-based tasks have `workflow_id = NULL` (verified:
  task_18cd3920aeeea608 → board=omnidev, workflow_id=None) → `has_wf=false` →
  `has_executor_role=false` → `route_fail_tool` F1 ("running") → blocked.
  Live: reviewer thread 51 called builtin_fail-thread with
  `workflow_step="running"`; engine log `transition=no re-run thread (blocked
  or non-workflow task)`; kanban_history #127 "no executor role in workflow
  for status review". Task blocked instead of executor rework.
- **Audit of shallow task-field consumers** (grep 2026-08-19):
  - `src/agent/fail_thread.rs` — raw `task.workflow_id` reads at 291/296/352/
    830 + raw `task.channel_id` at 343 (fail routing + re-run thread creation).
  - `src/db/threads.rs` — thread-creation paths resolve channel (~1453) and
    workflow (~1477, `task.workflow_id.as_deref().and_then(...)`) with partial
    fallbacks; plan/profile/provider/model inserted from raw task fields
    (threads.rs:77 insert, 380/710/908/1507).
  - `src/kanban_dispatch.rs` — per-consumer `resolve_task_channel`
    (line 125) + board fallback (line 290) — a LOCAL resolver, not shared.
  - `src/server/kanban.rs` — status transitions + `resolve_workflow_reset`
    (2208) + workflow reads (2305); create/update validation (509/532).
  - `src/kanban_action.rs` — action-mode context carries workflow_id
    (139/183/206).
  - `src/boards.rs` — has `boards_enabled` + `task_board` (175/186) but no
    full task-defaults resolver.
- Non-board tasks (explicit workflow_id/channel_id set) are unaffected today;
  board tasks are the ones with NULL fields needing the fallback.

## Requirements

1. **ONE shared resolver** — e.g. `ResolvedTaskDefaults { workflow_id,
   channel_id, profile, plan, provider, model }` built by
   `resolve_task_defaults(data_dir, task) -> ResolvedTaskDefaults` applying
   the documented resolution order (task field → board (boards.yml by
   task.board) → channel/global settings). Place it next to the board helpers
   (boards.rs) or a new `src/task_resolution.rs`. **Resolve AS EARLY as
   possible: compute once right after the task row is loaded, pass the
   resolved struct to consumers** — never resolve piecemeal per consumer.
2. **All consumers switch to the resolved values** (no shallow field reads):
   - fail_thread.rs (engine_transition + manual-review + re-run thread
     creation: workflow, channel, profile, plan, provider, model);
   - db/threads.rs thread-creation paths (channel/workflow/plan/profile/
     provider/model);
   - kanban_dispatch.rs (reuse the resolver instead of the local
     `resolve_task_channel`);
   - status-change dispatch, /redispatch, startup recovery;
   - kanban_action.rs context;
   - server/kanban.rs transition paths that need EFFECTIVE values.
   Display-only API responses (GET /kanban/tasks etc.) keep the raw stored
   fields — they show what's stored; BEHAVIOR uses resolved values.
3. **No divergence**: the dispatch path and every other consumer must use the
   SAME resolver (extract + share; do not keep per-consumer resolvers).
4. **Robustness**: malformed/unknown board → explicit error at resolution time
   (fail loud, mirror `task_board` semantics), never silent empty fallback
   that changes behavior.
5. **Regression tests** (per consumer):
   - board task (workflow_id NULL, board=omnidev) + reviewer fail `running` →
     status `running` + NEW executor thread (the original bug);
   - board task + reviewer fail `testing` → new tester thread;
   - board task + tester fail F0 → executor re-run (or review per
     review_on_fail — match non-board behavior exactly);
   - board task + reviewer explicit `blocked` → blocked (F3 unchanged);
   - board task status-change dispatch + redispatch resolve workflow/channel
     from the board;
   - board task thread creation resolves plan/profile/provider/model from the
     board;
   - NON-board task (explicit fields) → ALL existing behavior unchanged.
6. **Live verification** (omnidev): board-task reviewer-reject → executor
   rework thread (task running); kanban_history shows "Creating thread #N"
   for step 'running', not the "no executor role" block; a status-change
   dispatch on a board task lands on the board channel.

## Non-goals / DO NOT CHANGE

- F0-F4 matrix semantics, review_on_fail, auto_approve — UNCHANGED (only the
  workflow/field RESOLUTION changes).
- boards.yml content, task creation/validation, display API response shapes.
- Channel/global-settings resolution semantics (only centralize + share).

## Verification gates

- cargo check / clippy -D warnings / cargo test / fmt --check clean.
- deploy.py dev passes (omni-deployer dev-flavor).
- grep audit gate: no behavior-path consumer reads raw
  `task.workflow_id`/`task.channel_id`/`task.profile`/`task.plan`/
  `task.provider`/`task.model` outside the resolver + display-only responses.
- Live smoke (omnidev): the 4 board-task fail routes + status-change dispatch
  + redispatch behave identically to non-board tasks.

## Deliverable

omniagent commit(s) + SHAs + test/live evidence. Standing release loop: tasks
→ deploy.py dev → main → stable (never push stable while omnistable tasks
run). NOTE: until the fix ships, board-task fails block — recover manually via
the blocked-task recipe (REDISPATCH NOTE + PATCH status → running).
