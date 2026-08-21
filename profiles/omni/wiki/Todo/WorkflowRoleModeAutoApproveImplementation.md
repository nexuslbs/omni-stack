# Workflow Role Mode (agent/action) + Auto-Approve

**Status:** IMPLEMENTED (2026-08-14→17; omniagent `fe68972` role mode agent|action + auto_approve/review_on_fail + action_id, `15c92e9` runtime, `8a21a17`/`3d577e9` routing; omni-deployer GROUP 40/41 regression).
**Date:** 2026-08-17
**Scope:** omniagent (workflows.yml parsing, step-thread creation, kanban_updater routing, fail_thread transitions) + omni-dashboard (workflows page: mode + action selects, auto_approve checkbox) + omni-stack (workflows.yml example)

## Goal

Extend `workflows.yml` so each role (executor/tester/reviewer) can declare an
execution **mode**: `agent` (default — the current agent loop) or `action`
(execute a predefined action from actions.yml INSTEAD of the agent loop),
mirroring how hooks and schedule/cron already support `mode: agentic|action`.
Plus a workflow-level **`auto_approve`** property: when enabled the workflow
has no effective reviewer, tasks reaching review go straight to `done`, and the
"goes to review on fail" flag is ignored (treated as false; the dashboard
disables/unchecks it).

## Verified facts (do not re-derive — greps from 2026-08-17)

- Repos: `/opt/workspace/omniagent` (main), `/opt/workspace/omni-dashboard`
  (main), `/opt/workspace/omni-stack` (main).
- `workflows.yml` shape (config/workflows.yml:1-51): workflow-level
  profile/provider/model/plan_mode/retries/clear_executions_on_review +
  `roles:` with per-role template/profile/provider/model/plan_mode/retries.
  Parsed by `src/workflows.rs`: `WorkflowDefaults` (:66-74: profile, provider,
  model, plan_mode, retries), `WorkflowRole` (:78-84: template + flattened
  overrides), `Workflow` (:87-97: defaults + clear_executions_on_review +
  roles). `validate()` (:145-183): executor role required; tester/reviewer
  roles require non-empty template. `resolve_role()` (:264-290) merges
  role-overrides onto workflow defaults → `ResolvedWorkflowRole`.
- **Step-thread creation**: `src/db/threads.rs:1115 create_kanban_step_thread`
  — loads task, board gate, resolves workflow role, resolves channel/profile/
  plan/template, creates the step thread. THIS is where action mode plugs in
  (resolve role mode; if action, execute the tool call instead of spawning an
  agent thread — pattern: scheduler's `handle_action_mode`).
- **Action execution pattern** (copy from scheduler): `src/scheduler.rs:379
  resolve_action(data_dir, action_id)` reads `actions.yml` → `McpToolCall`
  (tool_name + params). `handle_action_mode` (:441-540) executes via
  `plugin_manager.snapshot_registry().execute(&tool_call, app_context)`,
  creates a system thread with the result (success or error), marks terminal.
  `create_action_thread` (:574+) creates thread + seq-0 cause + seq-1 result.
- **Mode precedent (hooks/schedule)**: tasks.yml comment (:25) `# action:
  some-action  # presence implies mode=action (else agentic)`; hooks.yml (:42)
  `# action: some-action` + `# mode: agentic  # explicit mode override`.
  hooks.rs constants MODE_AGENTIC/MODE_ACTION (:51-52); HookRow has `mode` +
  `action_id` (:154-156).
- **Routing on completion** (`src/agent/kanban_updater.rs`):
  - `route_completed_thread(step, errored, has_reviewer, has_tester)` (:311-327):
    review+ok → Done; review+err → BlockedInconclusiveReview; testing+ok →
    ReviewWithThread / ReviewManual; testing+err → TesterErrorToExecutor
    (executor re-run); running+ok+tester → TestingWithThread; other err →
    BlockedHalfFinished.
  - `update_kanban_task_from_thread` (:28-54): failed/interrupted/skipped →
    `engine_transition` (fail_thread.rs:749) with RerunKind; `Ok(None)` = blocked
    or no transition.
  - Engine transition enforces retry guard inside a transaction (limit =
    retries + 1): interrupted → same-step re-run until guard hit, then blocked
    (fail_thread.rs:719-747, WS-5 notes inheritance).
  - D5: tester error → executor re-run (not blocked) TODAY; user's new action
    mode spec CHANGES this for action-mode roles (see Requirements).
- **Dashboard workflows page**: `src/pages/workflows.ts` — list rendering
  (:135-184), form `openForm` (:270-289) with selects (profile/provider/model/
  template/plan — templateOptions :337-346), `handleSave` → `upsertWorkflow`
  (:658). Workflows CRUD API: `/workflows` GET/PUT/POST/DELETE
  (src/server/kanban.rs:111-114, upsert_workflow_handler validates via
  `WorkflowsFile::validate` then saves workflows.yml).
- **actions.yml** (config/actions.yml): map of action id → {enabled,
  tool_name, params, description, is_builtin}. This is the source for the
  dashboard action select.
- NO existing `review_on_fail` / `auto_approve` / per-role `mode` anywhere
  (grep across omniagent/src + omni-dashboard/src returned zero) — all new.

## Requirements

### 1. Per-role `mode` + `action` in workflows.yml (default `agent`)

- `WorkflowRole` gains `mode: Option<String>` (`agent` | `action`, default
  `agent` when absent — mirror hooks/schedule semantics) and `action_id:
  Option<String>` (the actions.yml key used when mode=action).
- Validation: mode must be `agent`|`action`; when mode=action, action_id is
  REQUIRED and must resolve to an enabled action in actions.yml (validate at
  parse time when actions.yml is readable; otherwise fail at thread-creation
  time with a clear error). When mode=agent, template applies as today
  (tester/reviewer still require non-empty template — action-mode roles do NOT
  need a template).
- Step-thread creation (`create_kanban_step_thread`): when the resolved role
  has mode=action, execute the action tool call via the plugin manager
  (resolve_action + execute, copy scheduler::handle_action_mode) and create a
  terminal system thread recording the result (success or error) instead of
  spawning an agent thread. Record the action mode in the thread (reuse
  `threads.cause`/msg_type conventions from create_action_thread — do NOT
  invent new columns; use msg_type like scheduler's action path).

### 2. Action-mode routing (replaces agent routing for action roles)

- **Executor (running) action**: success → next role (testing if tester
  exists, else review/done per normal flow); failure → `blocked` (NOT
  executor re-run; actions are deterministic tool calls — no retry loop).
- **Tester (testing) action**: success → review (as today); failure → `review`
  (USER RULE: tester error goes to review, NOT blocked and NOT executor
  re-run — the review step decides; differs from D5 agent behavior).
- **Reviewer (review) action**: success → `done`; failure → `blocked`
  (inconclusive review, as today's BlockedInconclusiveReview).
- Interruption/max-LLM retries: "retries in interruption due to max LLM calls
  work per normal, repeating the same role until the max retries, and when max
  retries reached go to blocked" — the existing engine_transition retry guard
  (limit = retries + 1, interrupted → same-step re-run, guard hit → blocked)
  is UNCHANGED for agent mode and applies to action-mode threads the same way
  (an action thread that is interrupted/errors re-runs the SAME role until the
  guard, then blocked).
- Implementation note: route_completed_thread + update_kanban_task_from_thread
  need to know the role's mode. Derive it from the workflow (task.workflow_id
  → resolve_role(step) → mode) — or store the mode on the thread row at
  creation (check threads schema for a usable field; if none, resolve from
  workflow at routing time — prefer workflow resolution, no migration).

### 3. Workflow-level `auto_approve` property (default false)

- `Workflow` gains `auto_approve: bool` (default false, serde default).
- When auto_approve=true:
  - The workflow effectively has NO reviewer: a reviewer role may still be
    defined in yml but is IGNORED (no review thread created; tasks never enter
    a review step with a reviewer). Simpler: validate that no reviewer role is
    used when auto_approve=true, or just ignore it — pick the ignore approach
    so existing workflows can flip the flag without editing roles.
  - Tasks that would go to review (`ReviewWithThread`/`ReviewManual`) go
    **directly to `done`** instead.
  - The "goes to review on fail" flag is **ignored / treated as false**:
    executor/tester failures → `blocked` directly (that is already the
    behavior when the flag is false, so auto_approve just forces it).
- The "review on fail" flag itself: there is NO existing flag — the task
  should ADD a workflow-level `review_on_fail: bool` (default false) so the
  semantics are explicit and the dashboard can show the checkbox the user
  described. When review_on_fail=true, failed executor/tester steps go to
  review (a review thread is created for the failure) instead of blocked.
  When auto_approve=true, review_on_fail is forced to false (ignored) and the
  dashboard checkbox is disabled + unchecked.
  - NOTE: today tester errors go to executor re-run (D5). With review_on_fail
    the user wants failure → review (not re-run). Keep agent-mode D5 executor
    re-run as-is EXCEPT when review_on_fail=true → review. The task must
    define the exact matrix and test it (see Verification gates).

### 4. Dashboard workflows page

- **Role mode select**: per role (executor/tester/reviewer), a Mode select
  (Agent | Action, default Agent) in the edit form. When Mode=Action, the
  Template select is REPLACED by an Action select (options from actions.yml —
  enabled actions, id + description; `/actions` endpoint exists at
  src/server/mod.rs:251-255). When Mode=Agent, the Template select shows as
  today. Action-mode roles must still allow profile/provider/model/plan_mode/
  retries fields.
- **auto_approve checkbox**: workflow-level checkbox. When checked, the
  "review on fail" checkbox is disabled and unchecked (and the reviewer role
  row is hidden/marked ignored). On save, auto_approve + review_on_fail are
  persisted to workflows.yml via the existing upsert.
- Upsert handler must accept the new fields (it already takes `Json<Workflow>`
  — the serde structs pick them up; just ensure validation doesn't reject
  action-mode roles without templates).

### 5. omni-stack example

- Update `config/workflows.yml` comments to document `mode: agent|action` +
  `action_id` + `auto_approve` + `review_on_fail`. Do NOT change live workflow
  behavior (omniagent-dev stays mode=agent, auto_approve=false).

## Non-goals / DO NOT CHANGE

- Do NOT change hooks/schedule/cron action mode (already works).
- Do NOT change agent-mode routing defaults: executor success → testing,
  tester success → review, reviewer success → done, D5 tester error →
  executor re-run (all unchanged when review_on_fail=false and auto_approve=false).
- Do NOT change the engine_transition retry guard mechanics (same-step re-run
  until retries+1, then blocked) — only its CALLERS/routing may change.
- No db-migrations change (no new columns — mode resolved from workflows.yml;
  if a thread column is genuinely needed, prefer workflow resolution instead).
- Do NOT touch action execution itself (resolve_action/execute are reused).

## Verification gates

- cargo check/clippy/test/fmt clean (baseline ~433+ / 0 failed; new unit tests
  for: mode parse/validate, action-mode thread creation routes to tool
  execution, routing matrix incl. action-mode tester-fail→review,
  auto_approve → review→done + review_on_fail forced false,
  review_on_fail=true → fail→review thread).
- Live (omnidev, isolated): a throwaway workflow with executor mode=action
  (use an existing enabled action like `builtin_relevance_indexer` or a
  noop/test action) — dispatch a task, verify the tool runs (no agent loop),
  thread terminal, task transitions to testing/review per the matrix; verify
  auto_approve workflow: task → done without reviewer; verify review_on_fail
  checkbox disabled when auto_approve checked in the dashboard.
- Dashboard: workflows page renders mode/action/auto_approve/review_on_fail;
  action select replaces template select in action mode; save round-trips to
  workflows.yml.

## Deliverable

Commit + push to origin/main. Repos: omniagent (workflows.rs mode/action/
auto_approve/review_on_fail, create_kanban_step_thread action path, routing
matrix, tests), omni-dashboard (workflows page form changes), omni-stack
(workflows.yml docs). Report commit SHAs, the routing matrix (role × mode ×
outcome), action-mode thread evidence, auto_approve evidence, and the
dashboard round-trip. Do NOT claim done until all gates pass.
