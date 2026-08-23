# Kanban API: Require `board` on Task Create/Edit when Boards Enabled

> Status: **IMPLEMENTED** (2026-08-18, omniagent `9a7f8c0`, pushed to origin/main)
> Scope: omniagent core (src/server/kanban.rs) — omnistable + omnidev (shared repo)

## Goal

The omniagent kanban API must **require `board`** when creating or editing a task
**while boards are enabled** (boards.yml exists). Today the API accepts tasks with
NULL board, and the auto-dispatcher (kanban_dispatch.rs:170-181) **silently skips**
board-less/unknown-board tasks — they sit in `todo` forever with no error surfaced
to the caller. This is a silent-failure trap observed live on 2026-08-18: task
`task_18cd061e85394a52` (hooks wiki/summaries) was created via `POST /kanban/tasks`
without `board`, sat in `todo` for ~20+ minutes while the 15s auto-dispatcher
silently ignored it; only after `PATCH /kanban/tasks/{id} {"board":"dev"}` did it
auto-dispatch (thread 2, dev-executor, processing).

## Verified facts (do not re-derive)

### API does NOT validate board (confirmed live + in source)

- `CreateTaskRequest.board` is `Option<String>` (src/server/kanban.rs:176).
- `create_task_handler` (src/server/kanban.rs:638-726) validates ONLY the title
  (line 642-645: "Title is required"). `board` is inserted via
  `NULLIF(:board, '')::text` (line 697) — missing/empty board → NULL. No
  boards_enabled check, no known-board check.
- `UpdateTaskRequest.board` is `Option<String>` (src/server/kanban.rs:204).
- `update_task_handler` (src/server/kanban.rs:1044+) validates title emptiness
  (1086-1090), status (1093-1100), at-least-one-field (1103-1118), and the
  active-workflow immutability guard (1071-1083) — but NOT board. The UPDATE sets
  `board = CASE WHEN :board = '' THEN board ELSE NULLIF(:board, '')::text END`
  (line 1136) — a client may also clear an existing board by sending `board: ""`
  (which NULLIFs to NULL), producing a board-less task with NO error.
- Board is NOT validated on status change / position / redispatch either — but the
  user requirement is specifically create + edit.

### Validation helper already exists

- `src/boards.rs:175-177` `boards_enabled(data_dir)` → true iff
  `{data_dir}/config/boards.yml` exists.
- `src/boards.rs:186-206` `task_board(data_dir, board: Option<&str>)` →
  - boards disabled → `Ok(None)` (board field is inert);
  - boards enabled + `None` → `Err("task has no board")`;
  - boards enabled + unknown name → `Err("task board 'X' not found in boards.yml")`;
  - boards enabled + found → `Ok(Some(cfg))`.
- The dispatcher already uses the same gate semantics (kanban_dispatch.rs:150-181:
  boards_enabled → filter tasks whose `board` names a board in the file).
- `data_dir` is available in the server state (`AppState` — check the existing
  handler field access pattern; the create/update handlers already use
  `state.pool`).

### Current boards.yml (omni-stack, shared)

```yaml
boards:
  main:
    channel: kanban
    profile: omni
    workflow: omniagent-dev
    plan: false
  dev:
    channel: mattermost-stable-channel
    profile: omni
    workflow: omniagent-dev
    plan: true
  plain:
    channel: kanban
    profile: omni
```

## Requirements

1. **POST /kanban/tasks** (`create_task_handler`):
   - When `boards_enabled(data_dir)`:
     - `board` MUST be present and non-empty in the request body, else
       `400 Bad Request` with a clear message ("board is required when boards are
       enabled (boards.yml present)");
     - the board MUST name an existing board in boards.yml, else 400
       ("task board 'X' not found in boards.yml") — reuse `task_board()`.
   - When boards are disabled: keep current behavior (board optional/inert).
2. **PATCH /kanban/tasks/{id}** (`update_task_handler`):
   - When boards are enabled, the resulting task must always have a valid board:
     - if `body.board` is `None` (field not sent) → keep existing (already-valid)
       board, unchanged;
     - if `body.board` is `Some("")` or `Some` unknown → 400 (do NOT allow
       clearing/removing the board to NULL, and do NOT allow an unknown board);
     - if `body.board` is `Some(valid)` → update to it.
   - When boards are disabled: current behavior (board optional/inert, clearing
     allowed).
3. Consistent error messages and status codes: 400 for missing/unknown board.
4. The dispatcher gate stays as-is (it already skips invalid boards) — the API
   validation prevents invalid tasks from being created in the first place. No
   dispatcher change needed (non-goal).

## Non-goals / DO NOT CHANGE

- DO NOT change the dispatcher's skip behavior (kanban_dispatch.rs) — only the
  API surface prevents invalid tasks.
- DO NOT change boards.yml contents or the boards CRUD API.
- DO NOT require board when boards.yml is absent (board feature inactive) —
  omnidev/omnistable legacy behavior for stacks without boards.yml.
- DO NOT touch the dashboard or other endpoints.
- DO NOT write `SQLX_OFFLINE=true` anywhere — CI-only.

## Verification gates (executor must run all)

- `cargo fmt --check`
- `cargo check --workspace --all-targets`
- `cargo clippy --workspace -- -D warnings`
- `cargo test` (add unit tests for the new validation: boards-enabled create with
  missing board → error; unknown board → error; valid board → ok; boards-disabled
  → ok with no board; update clearing board → error when enabled)
- Live smoke (API is inside the container; use `docker exec`):
  - `POST /kanban/tasks` without `board` while boards.yml present → 400 with
    "board is required";
  - `POST /kanban/tasks` with `board: "dev"` → 201/success;
  - `PATCH /kanban/tasks/{id}` with `board: ""` → 400;
  - confirm the created task auto-dispatches via the 15s in-process dispatcher
    (thread appears; no manual POST /kanban/dispatch needed).

## Deliverable

- Commit + push to `omniagent` (src/server/kanban.rs validation + tests) — report
  the commit SHA. No omni-stack changes expected (boards.yml untouched).

---

## IMPLEMENTED — 2026-08-18

- **Commit**: omniagent `9a7f8c0` — `feat(kanban): require board on task
  create/update when boards.yml present` (pushed to origin/main, HEAD == origin).
- **Verification (all green)**:
  - Executor (thread 5) implemented and pushed; tester threads 7 + 10 verified:
    unit tests cover boards-enabled create missing board → error, unknown board →
    error, valid board → ok, boards-disabled → ok, update clearing board → error.
  - Reviewer (thread 9) independently re-verified code + git history → APPROVED.
  - Live smoke (thread 11, via the omnidev-toolbox isolated stack — see skill
    `live-smoke-toolbox.md`): new binary built from HEAD `9a7f8c0`;
    - POST without board → **HTTP 400** "board is required when boards are
      enabled";
    - POST with unknown board → **HTTP 400**;
    - POST with `board: "dev"` → success;
    - PATCH clearing board (`""`) → **HTTP 400**;
    - PATCH keeping existing valid board → ok;
    - created task **auto-dispatched** via the in-process 15s dispatcher
      (thread spawned, no manual dispatch); smoke artifacts deleted + verified
      empty via DB query afterwards.
- **Caveat (still true)**: the RUNNING deployed stack may run a pre-change binary —
  unit/integration tests + toolbox smoke validate the new code, but the live API
  keeps old behavior until the stack is rebuilt/restarted (see thread 10).
