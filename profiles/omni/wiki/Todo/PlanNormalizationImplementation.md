# Normalize Planning to a Single `plan` Field (Implementation)

**Status:** IMPLEMENTED 2026-08-13 (omniagent `0c772e9` — planning_mode removed everywhere; single `plan` bool: DB columns dropped, tasks.yml enum removed, plugin APIs expose only plan)
**Date:** 2026-08-13
**Scope:** omniagent + omni-dashboard + omni-stack

## Goal

Eliminate the legacy `planning_mode` field everywhere. Omniagent has not gone
to production — there is no reason to keep a legacy duplicate. Normalize to a
single `plan` (bool) field: `planning_mode` TEXT column + `PlanningMode`
bool|string enum + API/dashboard fields all get dropped.

## Why

- `kanban_tasks` and `threads` tables carry BOTH `planning_mode` (TEXT, legacy)
  and `plan` (BOOL, derived). The migration backfilled `plan` from
  `planning_mode` (`db-migrations/src/lib.rs:160-209`), so `planning_mode` is
  dead weight — only `plan` is read at runtime.
- `tasks.yml` (schedules/hooks) uses a `PlanningMode` enum
  (`src/tasks_yaml.rs:130-137`) that accepts bool OR string and maps to the
  legacy pair via `to_legacy()`/`from_legacy()` (`:189-222`). The string forms
  (`"auto_plan"`, `"plan_with_subtasks"`, `"always"`…) collapse to the same
  bool — the enum exists only to keep the legacy column alive.
- Sibling Task I (channels.yml) was amended to ship `plan` (bool) in
  channels.yml from day one, so channels are already consistent with this task.
- Dashboard still renders `planning_mode` selects (kanban detail, hooks detail).

## Verified inventory (do not re-derive)

- **DB columns** (`db-migrations/src/lib.rs`): `threads.planning_mode` (:444,
  CREATE TABLE) + `threads.plan` (ALTER :162); `kanban_tasks.planning_mode`
  (:492) + `plan` (ALTER :173); `channels.planning_mode` (:411) — channels
  table DROPPED by Task I; `hooks.planning_mode` (:55) + `cron_jobs` (:559) —
  tables DROPPED by Task E. Only `threads` + `kanban_tasks` survive → drop
  their `planning_mode` columns.
- **`src/tasks_yaml.rs`**: `ScheduleDef.planning_mode` (:71-73),
  `HookDef.planning_mode` (:104), `PlanningMode` enum (:130-137),
  `to_legacy`/`from_legacy` (:189-222), `plan()`/`planning_mode_str()`
  (:240-248, :275-281), tests (:455, :467, :492, :570).
- **`src/server/kanban.rs`**: `planning_mode` in request/response structs +
  INSERT/UPDATE/SELECT (:164,:192,:219,:244,:336,:425,:519,:558,:668,:671,
  :684,:737,:880,:1019,:1077,:1100,:1117,:1188,:1222,:1249,:2009,:2188) —
  the `has_fields` gate at :1077 and CASE update at :1100.
- **`src/server/channels.rs`**: `ChannelEntry.planning_mode` + `ChannelRow`
  (:52,:72,:118,:140,:175,:196,:332,:353) — response-only.
- **`src/server/hooks.rs`**: (:72,:87-88,:106,:145,:179,:340,:434-435).
- **`src/server/schedule.rs`**: `from_legacy` uses (:469,:574).
- **`src/hooks.rs`**: engine metadata `planning_mode` (:159,:166-167,:183,
  :364-366).
- **`src/agent/fail_thread.rs`**: INSERT INTO kanban_tasks with
  `planning_mode` column (:1592,:1766).
- **plugins/tools/actions/src/main.rs:297**: `PlanningMode::Str("plan_with_subtasks")`.
- **plugins/tools/query/.sqlx/*.json**: cached SELECTs referencing
  `planning_mode` (channels + kanban_tasks queries) — refresh offline cache.
- **omni-dashboard**: `src/lib/api.ts:237,347`, `src/lib/hooks.ts:27`,
  `src/lib/kanban-detail.ts:277,283,319,397,446` (planning_mode select UI),
  `src/lib/hooks-detail.ts:86,225`.
- **omni-stack**: `config/tasks.yml` header comments mention `planning_mode`.

## Design

1. **DB migration** (`db-migrations/src/lib.rs`, order-independent vs Task E/I):
   `ALTER TABLE threads DROP COLUMN IF EXISTS planning_mode; ALTER TABLE
   kanban_tasks DROP COLUMN IF EXISTS planning_mode;` (channels/hooks/cron_jobs
   planning_mode dies with their table drops). `plan` stays as-is.
2. **`src/tasks_yaml.rs`**: delete the `PlanningMode` enum + `to_legacy`/
   `from_legacy`. `ScheduleDef.planning_mode: Option<PlanningMode>` →
   `plan: Option<bool>`; same for `HookDef`. Replace `plan()` helpers with
   direct field reads; delete `planning_mode_str()`. Update unit tests.
3. **Consumers**: `src/server/schedule.rs`, `src/server/hooks.rs`,
   `src/hooks.rs`, `src/agent/fail_thread.rs` — use `def.plan` /
   `hook.plan` directly; drop the metadata `planning_mode` key.
4. **`src/server/kanban.rs`**: remove `planning_mode` from request/response
   structs, INSERT/UPDATE/SELECT SQL, `has_fields` gate (:1077), CASE update
   (:1100), and all bindings. Keep `plan` boolean semantics unchanged.
5. **`src/server/channels.rs`**: remove `planning_mode` from `ChannelEntry`/
   `ChannelRow` (channels.yml already ships `plan` per Task I).
6. **plugins/tools/actions**: `plan: true` instead of
   `PlanningMode::Str("plan_with_subtasks")`.
7. **omni-dashboard**: remove `planning_mode` from types + the planning-mode
   select UI in kanban-detail.ts / hooks-detail.ts; keep `plan` (bool) display.
8. **omni-stack**: update `config/tasks.yml` header comment to `plan: true`.
9. **.sqlx offline cache**: `cargo sqlx prepare --workspace` after SQL changes.

## Non-goals / DO NOT CHANGE

- Do NOT touch `workflows.yml` `plan_mode` (role plan override — separate
  concept, not the legacy column).
- Do NOT change `plan` semantics, `resolve_thread_plan` priority, or
  `max_iterations_for_plan` budgets.
- Do NOT touch channels.yml (Task I owns it; already uses `plan`).
- Do NOT resurrect `planning_mode` anywhere, including API responses
  (dashboard is being updated in the same task).
- Task E owns dropping cron_jobs/hooks tables; Task I owns dropping the
  channels table. This task only drops `planning_mode` columns on
  threads/kanban_tasks (order-independent).

## Verification gates

- `cargo check --workspace --all-targets` (clean). NOTE: the omnidev dev
  overlay sets `SQLX_OFFLINE: "false"` — builds validate every query against
  the LIVE dev DB at compile time. Do NOT set `SQLX_OFFLINE=true` in the dev
  loop (that forces the stale `.sqlx/` cache → no-cached-data errors → the
  sqlx-prepare dance). `SQLX_OFFLINE=true` is only for CI (Dockerfile) and is
  verified once at the end, after `cargo sqlx prepare --workspace`.
- `cargo test --workspace` (baseline ~445 passed / 0 failed).
- `cargo fmt --check` (clean).
- `npm run build` in omni-dashboard (clean).
- Grep audit: `grep -rn "planning_mode" src/ plugins/` → 0 hits in omniagent;
  `grep -rn "planning_mode" src/` → 0 hits in omni-dashboard; no
  `planning_mode` in omni-stack config.
- Migration proof on a live-copy DB: columns gone, `plan` values preserved
  (backfilled booleans unchanged).

## Deliverable

Commit + push to origin/main. Repos: omniagent (migration, tasks_yaml.rs,
kanban.rs, channels.rs, hooks.rs, schedule.rs, fail_thread.rs, actions plugin,
.sqlx refresh, tests) + omni-dashboard (planning_mode removal) + omni-stack
(tasks.yml comment). Report commit SHAs + grep audit + migration proof.
