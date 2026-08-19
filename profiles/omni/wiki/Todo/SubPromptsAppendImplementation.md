# Sub-Prompts: Append Pending User Prompts to Running Thread (parent_id)

> Status: planned (omnidev board task)
> Scope: omniagent core (src/agent/main_loop.rs, src/db/messages.rs,
> src/db/threads.rs, src/agent/helpers.rs, src/server/settings.rs,
> db-migrations) + omni-stack (config/settings.yml)

## Goal

When a channel has a user task RUNNING (thread cause=user, status
processing) and there are PENDING user tasks (also cause=user) for the same
channel, same profile, and same parent_id (or pending.parent_id == running
thread id), the NEXT LLM call of the running thread must APPEND the pending
prompt(s) into the running thread's full prompt. The pending thread is
marked skipped; a `sub_cause` message records the original thread id; the
appended prompt is part of the FULL prompt sent to the LLM (never dropped,
applied BEFORE compaction).

## Current state (verified 2026-08-18)

- **Thread model** (src/db/types.rs:380-405): `Thread { id, status, cause,
  channel_id, profile, provider, model, ..., parent_id, ... }`. New user
  messages create threads via `create_thread_with_cause` (src/db/threads.rs:
  593, status 'created' then claimed pending→processing, claim_thread :786).
  `parent_id` is resolved from `parent_external_id` (root_id metadata) at
  :662-690.
- **Messages schema** (db-migrations/src/lib.rs:486-501): `messages` has
  `role`, `content`, `thread_id`, `msg_type TEXT DEFAULT 'message'`,
  `msg_subtype TEXT`, `metadata JSONB`, `iteration_number`. NO
  `original_thread_id` column yet.
- **Message struct** (types.rs:341-358): has `msg_type`, `msg_subtype`
  fields. `MessageNew` (:362-377) mirrors it.
- **Main loop** (src/agent/main_loop.rs:623 `for _turn in 0..max_llm_calls`):
  each iteration (a) condense/compact tool called FIRST (:645-724), then (b)
  prune (:735), then (c) budget hint + notes (:760+), then (d) LLM call
  (:865). **Sub-prompt inclusion MUST happen BEFORE the condense call** so
  the appended prompt survives compaction and is in the full prompt.
- **Settings** (src/server/settings.rs): global integer settings live in the
  section tables (:193+), the writable whitelist (:736-754), and category
  mapping (:625-645). New settings need entries in all three + the
  settings.yml default.
- **Pending thread lookup exists**: `list_pending_threads`-style queries
  (threads.rs:773 `WHERE channel_id = :channel_id AND status = 'pending'`).
- **Skipped marking**: threads.rs:287-296 `mark_thread_terminal(...,
  "skipped")` is the single choke point for terminal skipped.

## Change

1. **Migration** (db-migrations/src/lib.rs): add
   `original_thread_id BIGINT` (nullable) to `messages` (the pending thread
   id that was marked skipped and whose prompt was appended). Keep
   `msg_subtype` as the human-readable reference (store the original thread
   id there too, per user: "subtype the original thread id").
2. **db/messages.rs**: add `original_thread_id` to MessageDb/Message/
   MessageNew + the SELECT/INSERT column lists (get_thread_messages :309,
   create_message). Add a helper `insert_sub_cause_message(pool, running
   thread_id, pending_thread_id, prompt_content, iteration)` inserting
   `role='sub_cause', msg_type='sub_cause', msg_subtype=<pending_thread_id>,
   original_thread_id=<pending_thread_id>, content=<pending prompt>,
   thread_id=<running thread id>`.
3. **db/threads.rs**: add a query
   `list_appendable_pending_threads(pool, channel_id, profile,
   running_thread_id)`:
   ```sql
   SELECT t.* FROM threads t
   WHERE t.channel_id = :channel_id
     AND t.profile = :profile
     AND t.cause = 'user'
     AND t.status = 'pending'
     AND NOT t.terminal
     AND (t.parent_id = :running_thread_id
          OR (t.parent_id IS NULL AND t.parent_id IS NULL))  -- same parent_id as running (incl. both null = same top-level)
     -- OR parent_id of pending == thread_id of current running task:
     AND (t.parent_id = :running_thread_id)
   ORDER BY t.id ASC
   ```
   (The user's exact condition: same channel + same profile + same
   parent_id as the running thread, OR pending.parent_id == running
   thread id. Implement as: `pending.parent_id IS NOT DISTINCT FROM
   running.parent_id OR pending.parent_id = running.id`.)
   Add `mark_thread_skipped_for_sub_prompt(pool, pending_id)` using the
   existing skipped choke point (threads.rs:287-296) + kanban updater if the
   pending thread has a task_id.
4. **main_loop.rs — sub-prompt injection** (BEFORE the condense call at
   :645): each iteration, if the feature is enabled (settings), check the
   iteration-percent gate (see settings), then query appendable pending
   threads; for each (cumulative char budget permitting):
   - read the pending thread's cause (seq-0) message content (the user
     prompt),
   - `insert_sub_cause_message(...)` into messages table,
   - `mark_thread_skipped_for_sub_prompt(pending_id)`,
   - push a `ChatMessage::user(...)` (or a dedicated role/format) into the
     in-memory `messages` vec with the appended prompt content,
   - increment the running sub-prompt char counter.
   Loop must stop when: no more pending threads, OR the next prompt would
   exceed `sub_prompt_max_chars` cumulative, OR the iteration-percent gate
   says no. When the char limit is hit, set the loop-local flag false so no
   further lookups happen (even in later iterations).
5. **Char budget bookkeeping**: a local (loop-scoped) `used_sub_prompt_chars:
   usize` starts at 0, incremented per appended prompt, PERSISTED across
   iterations of the SAME thread run (it lives in the `for _turn` loop, so
   local state naturally persists across iterations). After reaching the
   limit (or when the next prompt would exceed it), set
   `sub_prompts_exhausted = true` and skip the lookup entirely on
   subsequent iterations.
6. **Settings** (src/server/settings.rs + config/settings.yml):
   - `sub_prompt_max_chars` (integer, default e.g. 4000): cumulative char
     budget for appended sub-prompts per running thread.
   - `sub_prompt_iteration_percent` (integer, default 50): max percent of
     LLM-call iterations that may look for sub-prompts. 0 disables the
     feature; 100 = check before every call (unless char budget / other
     blocker). Gate: only check when
     `current_iter * 100 <= iter_limit * sub_prompt_iteration_percent` (i.e.
     current iteration is within the first N% of the iteration budget).
   Add both to the section table (`general`), writable whitelist, and
   category mapping, with settings.yml defaults.
7. **Prompt format**: the appended sub-prompt must be in the FULL prompt.
   Recommended: a `ChatMessage::system` or `user` message with a clear
   header (`=== Sub-Prompt (from thread <pending_id>, appended) ===\n
   <pending prompt>`) so the LLM treats it as an additional instruction to
   finish. Include it in the `messages` vec BEFORE the condense call so
   compaction preserves it.

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- Migration: `\d messages` shows `original_thread_id BIGINT`.
- Unit test: a pending user thread (cause=user, same channel/profile,
  matching parent_id) is appended + marked skipped + sub_cause message
  recorded; char budget stops further appends; iteration-percent gate stops
  lookups after the threshold.
- Integration (omnistable): send a message to a channel while a user thread
  is running → the running thread's next prompt contains the appended text;
  the pending thread becomes `skipped` terminal; messages row has
  `msg_type='sub_cause'`, `msg_subtype=<pending_id>`,
  `original_thread_id=<pending_id>`.
- `GET /settings` shows `sub_prompt_max_chars` and
  `sub_prompt_iteration_percent`; PUT updates them live.

## Non-goals

- Do NOT change thread status semantics outside this feature (kanban/cron/
  hook threads are untouched — feature only matches cause=user pending
  threads with the parent_id condition).
- Do NOT auto-dispatch pending threads into new LLM runs (they are skipped,
  their prompt appended).
- Do NOT touch the prompt plugin's compact logic (the append happens in
  core BEFORE the condense tool call).

## Repos

- omniagent (db-migrations/src/lib.rs, src/db/types.rs, src/db/messages.rs,
  src/db/threads.rs, src/agent/main_loop.rs, src/agent/helpers.rs,
  src/server/settings.rs + tests)
- omni-stack (config/settings.yml defaults)

## Deliverable

Commit + push to origin/main on BOTH repos, report the commit SHAs. A
running user thread picks up pending same-context user prompts as
sub-prompts (marked skipped, recorded in messages.original_thread_id),
bounded by char + iteration-percent settings.
