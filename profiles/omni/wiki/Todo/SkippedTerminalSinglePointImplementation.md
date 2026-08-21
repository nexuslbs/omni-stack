# Terminal Status Invariant: skipped/completed/failed/interrupted ⇒ terminal=true (Implementation)

**Status:** IMPLEMENTED 2026-08-14 (omniagent `44799c4` — terminal status invariant: skipped/failed/interrupted/system always terminal=true)
**Date:** 2026-08-13
**Scope:** omniagent

## Goal

Every thread in a terminal status — `skipped`, `completed`, `failed`,
`interrupted` (and `system`) — MUST have `terminal = true`. There must be a
single choke point that flips a thread to any terminal status, and it must set
`terminal = true`. Ideally the invariant is also enforced at the DB level so it
can never regress.

## Why (verified)

A terminal-status thread with `terminal=false` looks like active work to any
code that checks `terminal` (e.g. a dispatch gate `WHERE terminal = false`
would block a channel forever). Observed live on channel 4: **13 `skipped`
rows with `terminal=false`** (left by the operator stop at 2026-08-13 20:07 via
`stop_handler`).

## Verified inventory (do not re-derive) — live matrix + write sites

**Live matrix (omnistable, all channels):**
- `completed` 101 rows → ALL `terminal=t` ✅
- `failed` 166 rows → ALL `terminal=t` ✅
- `interrupted` 9 rows → ALL `terminal=t` ✅
- `skipped` 27 rows → **13 `terminal=f` + 14 `terminal=t`** ❌ ← the bug
- `system` (init threads) → set via `set_thread_system` (terminal=true) ✅

**Correct funnel — completed/failed/interrupted go through ONE place:**
- `src/db/threads.rs:805-837` `complete_thread()` sets `status = :status,
  ended_at = NOW(), iterations = …, terminal = true WHERE id = :id AND NOT
  terminal`. Called from `response_handler.rs:352` with final_status
  failed/interrupted/completed (computed at `:313-350`), and from
  `fail_thread.rs:49` + `helpers.rs:63` with "failed".
- `src/db/threads.rs:87-93` `set_thread_system` — terminal=true ✅
- `src/db/threads.rs:102-107` `set_thread_failed` — terminal=true ✅

**BUGGY — skipped WITHOUT `terminal=true` (bypass complete_thread):**
1. `src/server/mod.rs:334` (stop_handler):
   `UPDATE threads SET status = 'skipped' WHERE channel_id = :channel_id AND status IN ('pending','processing')`
   — no ended_at, no terminal. **Source of the 13 bad rows.**
2. `src/server/mod.rs:543` (close_handler): identical statement — same bug.
3. `src/db/threads.rs:876` (skip_channel_threads per-thread loop):
   `UPDATE threads SET status = 'skipped' WHERE id = :id` — no ended_at, no terminal.
4. `src/db/threads.rs:1034` (skip_all_pending_threads startup loop):
   `UPDATE threads SET status = 'skipped', ended_at = now() WHERE id = :id` — ended_at yes, terminal NO.
5. `src/db/threads.rs:296` (create-message path, closed-channel skip):
   `UPDATE threads SET status = :status WHERE id = :id AND NOT terminal` — sets 'skipped' without terminal=true.

**CORRECT skipped site (canonical shape to follow):**
6. `src/db/threads.rs:961` (`skip_thread`, single-thread): status='skipped',
   ended_at=NOW(), terminal=true, iterations=MAX(iteration_number).
7. `src/platform/external/client.rs:1882` (message-deleted path): same full shape.

## Design direction (executor decides cleanest implementation)

- Extract ONE canonical helper in `src/db/threads.rs` (e.g.
  `mark_thread_terminal(pool_or_tx, thread_id, status)`) that performs the full
  UPDATE — status + ended_at + terminal=true + iterations — for ANY terminal
  status, transaction-capable. Route ALL skipped sites (1-5) through it.
  Sites 6-7 already match; refactor to the same helper if practical.
- Add a **DB CHECK constraint** so the invariant is structural:
  `CHECK (status NOT IN ('skipped','completed','failed','interrupted','system') OR terminal = true)`
  — via `db-migrations/src/lib.rs` (ALTER TABLE threads ADD CONSTRAINT …).
  This is the only schema change; the 13 bad rows MUST be backfilled first
  (`UPDATE threads SET terminal = true WHERE status='skipped' AND terminal =
  false`) or the constraint add fails.
- Keep each site's semantics: stop/close still skip + block kanban tasks;
  skip_channel_threads / skip_all_pending_threads still re-schedule
  kanban-linked threads; create-message path still only touches `NOT terminal`
  rows.
- Grep-verified zero remaining inline terminal-status UPDATEs outside the
  helper after the change.

## Non-goals / DO NOT CHANGE

- Do NOT change the re-schedule logic (R3 Phase 6) inside skip_channel_threads /
  skip_all_pending_threads.
- Do NOT change stop/close handler kanban-task blocking semantics.
- Do NOT touch the kanban workflow status machine (kanban_updater.rs) or
  fail_thread.rs transition logic — only thread terminal-write paths and the
  new constraint.
- Do NOT change the dispatch gate behavior (separate task).
- The working tree contains SIBLING WIP from in-flight tasks (channels.yml,
  plan normalization, default channels, cron/hooks, channel_subscriptions,
  plugin restart, max_tokens, dispatch gate). Commit ONLY your own files.
- Migration must be ORDER-INDEPENDENT vs sibling tasks that touch
  db-migrations/src/lib.rs: additive constraint + backfill only.

## Verification gates (bare canonical commands — omnidev container, project_dir /opt/workspace/omni-stack, env_file /opt/workspace/omni-deployer/omnidev.env, service omniagent)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  SQLX_OFFLINE=true in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- If SQL text changed: run `cargo sqlx prepare --workspace` ONCE at the end
  with DATABASE_URL set, commit changed `.sqlx/` files, verify CI path once
  with `SQLX_OFFLINE=true cargo check --workspace --all-targets`
- Grep audit: `grep -rn "status = 'skipped'" src/` only matches the helper;
  no inline terminal-status UPDATEs outside it.
- DB audit (must be clean):
  `SELECT status, terminal, count(*) FROM threads WHERE status IN ('skipped','completed','failed','interrupted','system') GROUP BY status, terminal`
  → no row with a terminal status and `terminal=f`.
- Live check on omnidev: `POST /stop/<channel>` then re-run the DB audit →
  every skipped row `terminal = t`; constraint accepts the writes.

## Deliverable

- Commit + push to origin/main: **omniagent**. Report the commit SHA.
