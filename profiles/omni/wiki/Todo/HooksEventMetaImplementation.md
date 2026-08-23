# Hooks Event Meta + Event Object Implementation

**Status:** IMPLEMENTED (2026-08-17→18; omniagent `4dd2921`/`c2bf7d4` — event meta (last_thread/last_message) in counter JSON + event object delivery + no-channel/no-profile guard).
**Date:** 2026-08-16
**Scope:** omniagent hooks engine (`src/hooks.rs`) + hook_counters state shape

## Goal

Extend the hooks system so each hook's persisted counter JSON also tracks the
**last trigger context** (`meta.last_thread` / `meta.last_message`), and every
trigger delivers an **event object** to the hook's execution target:

- **action-mode** hooks: the action (tool call from actions.yml) receives the event.
- **agentic-mode** hooks: the event is embedded as JSON in the spawned thread's prompt.

The event object lets hooks react to *what happened since the last trigger*.

## Verified facts (do not re-derive — greps from 2026-08-16)

- Repo: `/opt/workspace/omniagent` (branch main). Dev env: omnidev-omniagent-1
  container maps /app → repo, cargo at /usr/local/cargo/bin/cargo,
  CARGO_HOME=/usr/local/cargo. Non-login shell:
  `docker exec omnidev-omniagent-1 bash -c 'export PATH=/usr/local/cargo/bin:$PATH CARGO_HOME=/usr/local/cargo; cd /app && <cmd>'`.
- **Counter storage**: `hook_counters (hook_key text PK, counter jsonb NOT NULL
  DEFAULT '{"global": 0}'::jsonb)` — single row per hook; the JSON is the
  per-scope counter document. Shape today:
  `{"global": N}` or `{"channel": {name: N}, "profile": {name: N}}`
  (see `counter_shape_matches_spec` test at `src/hooks.rs:681-695` — asserts
  EXACT equality; adding `meta` will require updating this test).
- **Engine** (`src/hooks.rs`, 696 lines): `HooksEngine` with 3 events —
  `thread_started`, `thread_finished`, `new_message` (constants at :43-45).
  Entry points: `fire_thread_started(thread_id)` (:96), `fire_thread_finished(thread_id)`
  (:103), `fire_new_message(thread_id, message_id)` (:110) — all fire-and-forget
  via `dispatch` (:118).
- **Fire call sites**:
  - `src/db/messages.rs:43` — `fire_new_message(saved.thread_id, saved.id)` after insert
  - `src/db/threads.rs:434` — `fire_new_message(msg.thread_id, saved.id)`
  - `src/db/threads.rs:747` — `fire_thread_started(thread.id)`
  - `src/db/threads.rs:91,102,833,1002` — `fire_thread_finished(thread_id)`
- **Pipeline**: `handle_event_with_message(event, thread_id, _message_id)` at
  `src/hooks.rs:231-264` — the `_message_id` param is currently **UNUSED**
  (underscore prefix; new_message fire sites DO pass it). Flow:
  1. `load_event_thread(thread_id)` (:187-200) — SELECT
     `t.id, t.channel_id, t.channel_id AS channel_name, t.profile, t.hook_caused`
     FROM threads; NOTE the threads table has NO `channel_name` column —
     `channel_id` IS the channel name (TEXT, the yml key per channels.yml).
  2. Infinite-loop guard: `if thread.hook_caused { return Ok(()) }` (:240-244).
  3. `load_enabled_hooks(event)` (:205-218) — parses tasks.yml fresh each event
     (file edits take effect without restart), resolves channel ids.
  4. Per hook: `scope_key(...)` (:464-484) — `global` → `"global"`; `channel` →
     channel name (None on named-target mismatch); `profile` → profile (None on
     mismatch). Out-of-scope hooks skipped.
  5. `record_and_maybe_trigger(hook, key, thread)` (:269-318) — tx: SELECT
     counter FOR UPDATE → `counter_increment` (:514) → if new value >= hook.count
     (`should_trigger`) → `counter_reset` (:521) → UPSERT counter → COMMIT →
     then `trigger(hook, thread)` AFTER commit (:310) so a failing trigger does
     not roll back the counter reset.
- **Trigger** (`trigger` at :323-331): `MODE_ACTION` → `run_action(hook)`; else
  → `run_agentic(hook, thread)`.
- **Agentic mode** (`run_agentic` at :336-411): resolves channel (hook explicit
  → triggering thread's channel → default_hook_channel → ''), profile (hook →
  thread), builds prompt (hook.prompt or default `"Hook '<name>' fired (event: <event>)"`),
  metadata `{"hook_id", "hook_name", "hook_event"}` (:367-371), then
  `queries::create_thread_with_cause(... hook_caused: true ...)` (:374-404).
- **Action mode** (`run_action` at :415-445): `scheduler::resolve_action(data_dir,
  action_id)` (:379-411) → `McpToolCall { name: tool_name, arguments: entry.params }`
  from actions.yml; executed via `plugin_manager.snapshot_registry().execute(...)`.
  `entry.params` is the action's static `params:` JSONB.
- **HookDef** (`src/tasks_yaml.rs:95-125`): `enabled, channel, profile, plan,
  event, scope, target, count, prompt, action, mode, template` (+ display_name).
- **Server API** (`src/server/hooks.rs:42-51`): GET/POST `/hooks`,
  GET/PATCH/DELETE `/hooks/{id}`, PATCH `/hooks/{id}/toggle`,
  POST `/hooks/{id}/fire`. `fire_hook_by_id` (`src/hooks.rs:532-580`) is the
  manual-fire path (no counter increment; builds a synthetic `EventThreadRow`).
- **Threads schema** (relevant cols): `channel_id TEXT NOT NULL` (may be `''`),
  `profile TEXT NOT NULL` (may be `''`), `hook_caused BOOL NOT NULL DEFAULT false`,
  `status TEXT NOT NULL`, `terminal BOOL NOT NULL DEFAULT false`.
- **Messages schema** (relevant cols): `id bigint PK`, `thread_id bigint NOT NULL`,
  `channel_id TEXT` (nullable), `thread_sequence int`, `created_at timestamptz`.
- **Existing e2e tests**: GROUP 27 in omni-deployer `scripts/tests.py:7437+`
  (hooks counter trigger/reset, scope filtering, infinite-loop protection, both
  execution modes, error isolation). `_h27_sql` runs psql via psycopg2 inside
  the omniagent container; `_h27_api` is raw urllib against `{BASE}`.

## Requirements (user spec, 2026-08-16)

### 1. Counter JSON gains a `meta` object

The persisted counter document (`hook_counters.counter`) gains a top-level
`meta` object with two integer fields:

```json
{
  "global": 0,
  "channel": { "...": 0 },
  "profile": { "...": 0 },
  "meta": {
    "last_thread": 123,
    "last_message": 456
  }
}
```

`last_thread`/`last_message` = the ids of the thread and message of the **last
time the hook was triggered** (i.e. the previous trigger's `current_thread` /
`current_message`). Before the first trigger, `meta` may be absent or null;
when a trigger happens, `meta` is written with that trigger's
`current_thread`/`current_message`. The counter increment/reset logic must not
clobber `meta` (it lives at the top level, alongside `global`/`channel`/`profile`).

### 2. Every trigger delivers an EVENT OBJECT

When a hook triggers (counter reaches `count`), the hook builds an event object
and delivers it to the execution target:

```json
{
  "last_thread": 100,
  "last_message": 200,
  "current_thread": 123,
  "current_message": 456,
  "channel": "mattermost-<hex>",
  "profile": "omni"
}
```

- `last_thread` / `last_message`: from the stored `meta` (previous trigger).
  Absent/null on the first trigger (omit or null — pick one, be consistent, and
  document it).
- `current_thread`: the triggering thread's id — becomes the new `last_thread`.
- `current_message`: the triggering message's id — becomes the new `last_message`.
- `channel`: the channel of the thread that triggered the event.
- `profile`: the profile of the thread that triggered the event.

**Delivery per mode:**

- **Action mode** (`MODE_ACTION`): the action receives the event — the
  `McpToolCall.arguments` built from actions.yml `params` is augmented with the
  event (e.g. `arguments["event"] = <event object>`, merged with the static
  params). The tool called by the action can then read the event from its
  arguments.
- **Agentic mode** (default): the event is embedded as JSON in the spawned
  thread's prompt — the prompt becomes
  `"<hook prompt>\n\nEvent: <json>"` (or a clearly delimited JSON block). The
  exact formatting is up to the implementer but MUST include the full event
  object as JSON in the prompt text.

### 3. current_message resolution per event type

- **`new_message`** events: `current_message` = the message id passed to
  `fire_new_message` (the `_message_id` param — start using it). The thread is
  already resolved from the message (`saved.thread_id` / `msg.thread_id`), so
  the event's `channel`/`profile` come from that thread.
- **`thread_started` / `thread_finished`** events: `current_message` = the
  thread's **last message** — the highest `messages.id` for that thread. If the
  thread has **no messages**, use the **last message id in the DB** (global max
  `messages.id`) — per user spec ("the last message id in the db, if the thread
  has no message"). If the DB has no messages at all, null/absent.

### 4. Guards (new + existing)

- **NEW — no channel/profile guard**: hooks must NOT be triggered by threads
  (or messages from threads) whose thread has an **empty `channel_id`** or an
  **empty `profile`**. Add the check in the event pipeline (after
  `load_event_thread`), so the event loop returns early and no hook is evaluated.
  (Per user: "The hooks should not be triggered by threads/messages from threads
  that have no channel or profile.")
- **EXISTING — hook-caused guard stays**: hook-caused threads (and their
  messages) never trigger events — the `thread.hook_caused` check at
  `src/hooks.rs:240-244` already does this; keep it. Verify the new_message path
  also passes through it (it does — `fire_new_message` → `handle_event_with_message`
  → same guard).

### 5. Scope note

For hooks scoped to a specific channel (or profile), the event's `channel` (or
`profile`) field will always have the same value. That is expected — the event
follows the standard shape regardless of scope.

## Design decisions (verify before implementing)

- `meta` lives at the top level of the counter JSON, alongside `global` /
  `channel` / `profile`. The counter accessors (`counter_get` :487,
  `counter_set` :495, `counter_increment` :514, `counter_reset` :521) operate on
  the counter sections; `meta` is written separately by a new helper
  (e.g. `meta_update(counter, last_thread, last_message)`) called when a
  trigger fires — inside the SAME tx that resets the counter (so meta + reset
  are atomic), and the event object is built from the meta value read in that
  same tx.
- The event must be built from the PRE-trigger meta (the last trigger's ids) —
  read `meta` before updating it; deliver the event with the OLD values; persist
  the NEW values (`current_thread`/`current_message`) as the next `meta`.
- `run_action` currently takes `(&HookRow)` only — it needs the event to merge
  into arguments; thread the event (or the triggering `EventThreadRow` +
  message id + meta) through `trigger` → `run_action` / `run_agentic`. Update
  `fire_hook_by_id` (:532) manual-fire path accordingly (manual fire has no
  triggering thread: event = {last_thread: from meta or null, last_message:
  same, current_thread: null/absent, current_message: null/absent, channel:
  hook/channel default, profile: hook/profile default} — document the shape).
- Action arguments merge: keep the static `params` and ADD the event under a
  well-known key (`event`). Do not overwrite static params with the same name —
  pick the merge order and document it (e.g. `params` first, `event` wins on
  collision, or event first; pick one and say so).
- The `counter_shape_matches_spec` unit test (:681) will fail once `meta` exists
  — update it to include `meta` and add new unit tests for `meta_update`,
  event-building (first trigger vs subsequent), and the no-channel/profile guard
  logic (extract the guard into a pure function for testability if needed).

## Non-goals / DO NOT CHANGE

- Do NOT change the events supported (thread_started / thread_finished /
  new_message), the scope semantics, the count threshold semantics, or the
  hook-caused loop protection.
- Do NOT change the hooks REST API surface (`src/server/hooks.rs` routes).
- Do NOT touch `db-migrations` (no schema change needed: `hook_counters.counter`
  is JSONB — `meta` is a data-shape change only, no column/index/migration).
- Do NOT change actions.yml files or any action definitions.
- Do NOT touch cron/schedule behavior.
- Keep GROUP 27 e2e tests passing (they run against a live stack in
  omni-deployer `scripts/tests.py`); extend the GROUP (or add a new GROUP) with
  assertions for `meta.last_thread`/`last_message` persistence + the event
  object reaching action/agentic targets, following the existing `_h27_*`
  helpers pattern.

## Verification gates

Run inside omnidev-omniagent-1 (cwd /app, PATH=/usr/local/cargo/bin:$PATH,
CARGO_HOME=/usr/local/cargo). The omnidev dev overlay sets SQLX_OFFLINE=false
— do NOT set SQLX_OFFLINE=true in the dev loop (CI-only); verify once at the
end after `cargo sqlx prepare --workspace` with DATABASE_URL set if the queries
changed (they may not — the hooks queries are unchanged; only Rust logic
changes).

- `cargo check --workspace --all-targets` (clean).
- `cargo clippy --workspace --all-targets -- -D warnings` (clean).
- `cargo test --workspace --release` (baseline ~433+ passed / 0 failed in
  omniagent lib; new unit tests for meta + event building + guard added).
- `cargo fmt --check` (clean).
- Grep audit: no `_message_id` unused param remains in `handle_event_with_message`
  (it must be used); `meta` handled in every counter read/write path.
- e2e (omnidev, isolated DB): create a hook (new_message, count 1, action mode
  with a test action that echoes its arguments) → POST a message → verify the
  action received `arguments["event"]` with correct current_* / channel /
  profile and last_* null on first trigger → trigger again → verify
  `meta.last_thread`/`last_message` equal the first trigger's current_* →
  verify a thread with empty channel_id/profile does NOT trigger any hook →
  verify a hook-caused thread does NOT trigger hooks. Agentic mode: verify the
  spawned thread's seq-0 message content contains the event JSON.

## Deliverable

Commit + push to origin/main (omniagent). Report commit SHA(s), the unit tests
added, and the e2e evidence (event object received by action, meta persistence,
both guards). Do NOT claim done until all gates pass.
