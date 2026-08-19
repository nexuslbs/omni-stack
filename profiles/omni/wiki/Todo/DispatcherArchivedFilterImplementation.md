# Dispatcher: Archived Tasks Must Never Be Dispatched

> Status: **IMPLEMENTED 2026-08-19** (omniagent `070e8f4`; executor #27, tester #28 PASS, reviewer #29 APPROVE)
> Scope: omniagent core (src/kanban_dispatch.rs) + tests

## Goal

Archived kanban tasks must never be promoted/dispatched. Today the
dispatcher's scan SQL filters `status='todo'` only — `archived` is never
checked, so an archived task still in `todo` gets promoted and its executor
thread runs (observed 2026-08-18: task_18cd0a6c7ef43217 was archived but
promoted at 23:51, actively editing source until stopped).

## Root cause (verified)

`dispatch_todo_tasks` scan (src/kanban_dispatch.rs:137-143):

```sql
SELECT id, title, channel_id, board
FROM kanban_tasks
WHERE status = :status
ORDER BY priority ASC, position ASC
```

No `archived = false` predicate. The PATCH `archived:true` handler only flips
the flag; it does NOT move the status, so an archived task left in `todo` is
still picked up. (Workaround today: PATCH `status:blocked` too — blocked is
not scanned — but the dispatcher itself must be fixed.)

## Change

1. **src/kanban_dispatch.rs**: add `AND archived = false` (or
   `AND NOT archived`) to the scan SQL at :137-143. Also audit the OTHER
   status-promotion SQL in the same file (and any sibling dispatcher:
   `create_kanban_step_thread` / status-change dispatch paths) for the same
   missing archived filter.
2. **Tests**: add a unit/integration test — archive a `todo` task, run the
   dispatcher, assert it is NOT promoted (task stays `todo` + `archived`,
   no thread created). Prefer a test that would fail on the old SQL
   (archived task was promoted before the fix).

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- Grep: `grep -n "archived" src/kanban_dispatch.rs` shows the filter in the
  scan + dependency gate (deps_satisfied already treats archived as ok).
- Live check (optional, on omnistable): PATCH an archived `todo` task →
  dispatcher leaves it alone (no thread), even though status is still todo.

## Non-goals

- Do NOT change PATCH archived semantics (archived:true stays a flag).
- Do NOT change the dependency gate (archived deps already count as ok).
- Do NOT touch dispatch eligibility beyond the archived filter.

## Repos

- omniagent (src/kanban_dispatch.rs + tests)

## Deliverable

Commit + push to origin/main, report the commit SHA. Archived tasks are
never dispatched by the auto-dispatcher (or any status-change dispatch).

---

## Implementation (2026-08-19)

- omniagent **`070e8f45615c0e57c731fb4953c88977240a2568`** `fix(kanban):
  never dispatch archived tasks (scan SQL + status-dispatch gate)` (pushed
  origin/main, verified via GitHub API by tester #28 + reviewer #29):
  1. `src/kanban_dispatch.rs` — auto-dispatcher todo-scan SQL now
     `WHERE status = :status AND archived = false` PLUS a Rust-side backstop
     `scan_row_eligible(status, archived)` (NULL `archived` = not archived)
     filtering fetched rows; regression unit test added (would fail on the
     old SQL: archived task was promoted before the fix).
  2. `src/db/threads.rs` — `create_kanban_step_thread` now loads `archived`
     and returns `Ok(None)` for archived tasks — backstops ALL dispatch
     paths (status-change dispatch, /redispatch, startup redispatch,
     auto-dispatch).
- Tester verdict PASS (existing coverage is the right one; no new tests by
  tester), reviewer verdict APPROVE.
