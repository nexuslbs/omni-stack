# Dashboard: Show Board Workflow + Workflow Select in Board Create/Edit

> Status: **IMPLEMENTED 2026-08-18** (omni-dashboard `16bb503` board workflow select + display; kanban task_18cd0a6e10e9c45d DONE) — board modal workflow is a select of workflows.yml keys, boards show workflow+channel
> Scope: omni-dashboard (src/lib/kanban-boards.ts, src/lib/kanban-board.ts, src/lib/api.ts)

## Goal

The dashboard must display each board's workflow, and board create/edit must
let the user pick a workflow from a select populated from workflows.yml —
not a free-text input.

## Current state (verified 2026-08-18)

- **API**: `BoardConfig.workflow?: string` exists (api.ts:261); `GET /boards`
  returns it; `fetchWorkflows()` (api.ts:590) lists workflows.yml keys
  (`omniagent-dev`, `wf_probe_final`).
- **Board modal** (kanban-boards.ts openBoardModal :125-231): ALREADY has a
  `board-form-workflow` field — but as a FREE-TEXT `<input>`, not a select.
  Same for channel/profile/template (free text is fine for those; workflow
  must become a select of known workflow keys).
- **Board display**: the board selector (`wireBoardControls` :242) and the
  "choose a board" buttons (`loadBoard` :147-175) show ONLY the board key —
  no workflow, no channel. Nothing on the kanban page shows a board's
  workflow.

## Change

1. **Workflow select in board modal**: replace the `board-form-workflow`
   text input with a `<select>` populated from `fetchWorkflows()` (keys of
   workflows.yml) + a `(none)` option. When opening the modal (create or
   edit), load workflows async, then render the select with the current
   `b.workflow` selected. `readBoardForm()` keeps reading `#board-form-
   workflow`'s value (select value = workflow key or "" for none).
   Handle the empty-workflows case (no workflows.yml → single "(none)"
   option, field effectively read-only).
2. **Display workflow on boards**: in `wireBoardControls`, render the
   selected board's workflow (and channel) next to the select — e.g. a
   muted label `workflow: omniagent-dev · channel: mm-kanban` (only the
   fields that exist). In `loadBoard`'s "choose a board" buttons, append
   the workflow under the key (small muted text) so the choice is informed.
3. **Keep free-text for channel/profile/template/priority** — only workflow
   becomes a select (its values come from a fixed file: workflows.yml).

## Verification gates

- `npm run build` clean (no TS errors).
- `npx vitest run` — existing kanban-boards tests pass; add a test for
  `renderWorkflowSelect`/workflow-options helper if extracted (pure
  function: options from WorkflowEntry[] + current value).
- Manual: create a board with workflow selected from the dropdown → GET
  /boards shows `workflow: <key>`; edit board → select shows the saved
  workflow; board selector shows the workflow label.
- When workflows.yml has 2 keys, the select offers exactly those 2 + none.

## Non-goals

- No omniagent core changes (API already returns workflow).
- No board CRUD behavior changes (only UI field type + display).
- Do NOT change the task card/detail pages (task-level workflow_id is a
  separate concern; this task is about BOARD workflow display only).

## Repos

- omni-dashboard (src/lib/kanban-boards.ts, src/lib/kanban-board.ts,
  src/lib/api.ts if helpers needed + tests)

## Deliverable

Commit + push to origin/main, report the commit SHA. After landing, the
dashboard kanban page shows each board's workflow and the board modal's
workflow field is a select of workflows.yml keys.
