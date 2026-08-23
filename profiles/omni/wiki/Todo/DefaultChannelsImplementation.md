# Default Channel Settings + CLI Platform (Implementation)

**Status:** IMPLEMENTED 2026-08-13 (omniagent `8e13237` — default cli/schedule/hook/kanban channel settings as selects over channels.yml; platform-less channel = cli; empty channel fails with 'no channel defined' but record kept). **AMENDED 2026-08-23:** `default_cli_channel` REMOVED — the binary has no CLI session mode and the only `/mcp/execute` caller (dashboard read-only `search_database`) never creates sessions, so the setting had no live consumer. Remaining settings: `default_schedule_channel`, `default_hook_channel`, `default_kanban_channel`.
**Date:** 2026-08-13
**Scope:** omniagent + omni-dashboard + omni-stack

## Goal

Four new writable settings — `default_cli_channel`, `default_schedule_channel`,
`default_hook_channel`, `default_kanban_channel` — each a **select** over the
existing channels (any platform: cli, mattermost, …). Remove the
`kanban`/`cron`/`hook` channel platforms entirely: a channel with no platform
is type `cli`. A thread with no channel is created with an empty channel
(`''` / NULL) and then FAILS with "no channel defined" — but the thread record
persists for reference.

## Why

- The seeded `kanban`/`cron` channels exist only as delivery sinks for
  kanban/schedule/hook threads. Making them selectable defaults (settings)
  instead of fixed platform channels removes the fake platforms and lets the
  operator point each sink at any real channel (e.g. a Mattermost channel where
  the bot posts the first message on thread creation — already works today via
  the executor seq-0 delivery path).
- A thread with no channel should still be recorded (audit/reference), then
  fail loudly — today `create_thread_with_cause` errors BEFORE insert when the
  channel is missing, so no record exists.

## Verified facts (do not re-derive)

- **Settings infra** (`src/server/settings.rs`): writable keys whitelist at
  :743-760 (HashSet); dynamic select options pattern = `enrich_provider_options`
  (:635-652) called from GET /settings (:690-696); `SettingMeta.field_type:
  "select"` with `options: Option<Vec<SettingOption>>`; settings values live in
  settings.yml (flat map from nested sections, :101-160). `default_profile`
  (:525) + `default_provider` (:440) are the existing select precedents.
- **Channel platform usage**: `Channel.platform` is `Option<String>`; NULL =
  no-platform (src/db/types.rs:371 comment "NULL means no-platform"). The
  executor only delivers to a platform when `channel.platform` is Some AND
  `resource_identifier` is Some (src/agent/executor.rs:154-168). A cli channel
  (no platform) therefore never attempts external delivery — correct.
- **Thread creation** (`src/db/threads.rs`): `create_thread_with_cause` (:592)
  resolves the channel at :611-614 — `get_channel_by_id(...).ok_or_else("Channel
  {} not found")` — i.e. missing channel = error BEFORE insert = no record.
  INSERT itself (:62-80) inserts `channel_id` directly; after Task I this column
  is TEXT (channel name), threads.channel_id NOT NULL (empty string allowed).
- **ensure_cron_channel** (`src/scheduler.rs:336-355`): creates/returns a
  'cron-session' channel with platform='cron'. Used as fallback at :174, :178,
  :591, :594 (scheduler tick/manual-run) and :867, :870 (fire_cron_job_by_id),
  and from hooks.rs:562. To be replaced by the default_schedule_channel /
  default_hook_channel settings.
- **Schedule channel resolution** (`src/scheduler.rs:828`): `resolve_channel_id(pool, def.channel)` → None = no channel → falls back to ensure_cron_channel (:864-871). New chain: def.channel → default_schedule_channel → '' (fail-with-record).
- **Hook channel resolution** (`src/hooks.rs:547-563`): `resolve_channel_id(def.channel)` → None → fallback thread.channel_id (:344) → else ensure_cron_channel (:562). New chain: def.channel → default_hook_channel → '' (fail-with-record).
- **Kanban dispatch** (`src/server/kanban.rs:2210-2215`): `channel_id = detail.channel_id` → None → error "Task has no channel_id" (no thread created). New chain: task.channel_id → default_kanban_channel → '' (thread created with empty channel, then fails with "no channel defined", record kept).
- **Kanban thread creation**: kanban executor thread is created with channel from the task (kanban_updater.rs / dispatch); thread.channel_id must accept the empty string.
- **CLI default** (`src/server/mod.rs:1056-1111`): MCP execute context already defaults platform "cli" + empty channel/thread when not provided. The default_cli_channel setting extends this: cli-originated threads with no channel resolve to default_cli_channel → '' (fail-with-record).
- **Dashboard** (`omni-dashboard`): settings page (src/pages/settings.ts) renders `select` from `meta.options` (:196-206) — server-enriched options render automatically. Channel selects need the server to populate options from the channel store (channels.yml after Task I).
- **Seeds**: `seed_kanban_channel`/`seed_cron_channel` (db-migrations/src/lib.rs:894-928) insert platform='kanban'/'cron' channels — Task I removes the DB seeds (channels from yml); this task ensures channels.yml seeds 'kanban'/'cron' with NO platform (= cli).

## Design

1. **Settings** (`src/server/settings.rs`): add 4 writable select settings:
   `default_cli_channel`, `default_schedule_channel`, `default_hook_channel`,
   `default_kanban_channel`. Add to `writable_keys` (:743-760). Add
   `enrich_channel_options(meta, data_dir)` mirroring `enrich_provider_options`
   (:635-652): options = channel NAMES from the channel store (channels.yml
   after Task I; channels table before it lands — read whichever the channel
   loader exposes). Enrich all 4 in GET /settings.
2. **Channel store**: channels.yml (Task I) keeps 'kanban'/'cron' seed entries
   with NO platform (platform-less = cli). No `platform: kanban` / `platform:
   cron` anywhere.
3. **Empty-channel fail-with-record** (`src/db/threads.rs:592`): when the
   resolved channel is empty ('' / None), the thread INSERT proceeds with the
   empty channel_id (record created for reference), then the creation path
   returns/marks an error "no channel defined" (thread marked failed /
   terminal so it is never picked up by the executor). Do NOT error before
   insert. messages.channel_id nullable → NULL; threads.channel_id NOT NULL →
   ''.
4. **Channel resolution chains** (each: explicit → default setting → empty):
   - kanban: task.channel_id → default_kanban_channel → '' (server/kanban.rs:2210, kanban_updater.rs)
   - schedule: def.channel → default_schedule_channel → '' (scheduler.rs:828, :864-871; remove ensure_cron_channel calls)
   - hook: def.channel → thread.channel_id → default_hook_channel → '' (hooks.rs:547-563; replace ensure_cron_channel :562)
   - cli: caller-provided channel → default_cli_channel → '' (server/mod.rs MCP execute path + any cli thread creation)
   All default settings resolve a channel NAME from the channel store; unknown name → treated as empty (fail-with-record).
5. **Remove ensure_cron_channel** (scheduler.rs:336-355): delete the
   'cron-session' channel creation; scheduler resolves default_schedule_channel
   instead (channels.yml must have a 'cron' entry OR the operator sets
   default_schedule_channel to an existing channel; keep a channels.yml 'cron'
   seed so default = 'cron' works out of the box).
6. **Default values**: settings defaults point at the seeded names — kanban →
   'kanban', schedule → 'cron', hook → '' (operator picks), cli → '' (operator
   picks; or a seeded cli channel if desired).
7. **Dashboard**: nothing new needed for rendering (server-enriched select
   options); verify the 4 selects appear in the settings page with channel
   names and PATCH persists them. Optionally show the channel's platform in the
   option label ("kanban (cli)").

## Non-goals / DO NOT CHANGE

- Do NOT touch the kanban/schedule/hook WORKFLOW semantics, plan resolution,
  or thread budgets.
- Do NOT touch channels.yml table-drop migration (Task I owns it).
- Do NOT reintroduce `planning_mode` (Task J owns that).
- Do NOT add per-channel delivery logic for cli: a cli channel simply never
  delivers externally (executor.rs:154-168 already skips when platform is
  None) — only the channel resolution changes.
- Do NOT create 'cron-session' anymore.

## Verification gates

- `cargo check --workspace --all-targets` (clean). NOTE: the omnidev dev
  overlay sets `SQLX_OFFLINE: "false"` — builds validate every query against
  the LIVE dev DB at compile time. Do NOT set `SQLX_OFFLINE=true` in the dev
  loop (that forces the stale `.sqlx/` cache → no-cached-data errors → the
  sqlx-prepare dance). `SQLX_OFFLINE=true` is only for CI (Dockerfile) and is
  verified once at the end, after `cargo sqlx prepare --workspace`.
- `cargo test --workspace` (baseline ~445 passed / 0 failed).
- `cargo fmt --check` (clean). `npm run build` in omni-dashboard (clean).
- Grep audit: no `ensure_cron_channel`, no `platform: kanban` / `platform:
  cron` / "cron-session" in src/ or channels.yml; 4 default_*_channel settings
  present in GET /settings with channel options.
- LIVE (omnidev, isolated DB): unset a kanban task's channel → thread created
  with '' channel → fails "no channel defined" → record visible in DB; set
  default_kanban_channel → same task dispatches to that channel; a cli channel
  (no platform) listed in GET /channels as platform cli/empty; schedule/hook
  defaults honored.

## Deliverable

Commit + push to origin/main. Repos: omniagent (settings, channel resolution
chains, empty-channel fail-with-record, remove ensure_cron_channel, tests) +
omni-dashboard (verify/option-label touch-up) + omni-stack (channels.yml seed
without kanban/cron platforms + docs). Report commit SHAs, grep audit, and the
live-check evidence.
