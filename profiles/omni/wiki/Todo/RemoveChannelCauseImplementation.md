# Remove `cause` From Channel Model (yml + API)

> Status: planned (omnidev board task)
> Scope: omniagent core (src/channels_yaml.rs, src/db/types.rs, src/db/channels.rs, src/server/channels.rs, src/commands.rs, src/server/plugins_setup.rs) + omni-stack (config/channels.yml)

## Goal

`cause` is not relevant in the context of a channel. Remove it from the
channels.yml schema, the ChannelDef/Channel/CreateChannelParams/ChannelEntry
structs, the channel API response, and every construction/validation site.
(Thread cause stays — `threads.cause` / messages role='cause' are a
different concept and are NOT in scope.)

## Current state (verified 2026-08-18)

`cause` is a legacy leftover from the pre-channels.yml DB era. Today it is
stored in channels.yml, validated to one of `user|cron|system|setup`, and
serialized into every channel API response — but NO code behaves differently
based on it (readonly/closed/plan are separate fields; the dashboard never
reads channel cause; deploy tests assert nothing about it).

## Change inventory (grep-verified file:line)

### omniagent — remove field + all references

1. `src/channels_yaml.rs`
   - `ChannelDef.cause: String` field (:100-101) + `default_cause()` fn (:122) — remove both
   - `validate_channel` cause check (:300-304: `if !matches!(def.cause.as_str(), ...)`) — remove
   - doc comments mentioning cause (:18, :23, :99) — drop the cause phrase
   - unit tests referencing cause: :341 (`k.cause`), :384-395 (`cause: "user"` + `c.cause`), :408-423 (same), :430-440 (`bad_cause` fixture + validation error test — DELETE the bad-cause test), :463-464 — update/delete
2. `src/db/types.rs`
   - `Channel.cause: String` (:306) + `Default` impl entry (:326) — remove
   - `CreateChannelParams.cause: String` (:252) — remove
3. `src/db/channels.rs`
   - `def_to_channel`: `cause: def.cause.clone()` (:28) — remove
   - `create_channel`: `d.cause = p.cause.clone()` (:99) — remove
4. `src/server/channels.rs`
   - `ChannelEntry.cause: String` (:59) + `From<Channel>` `cause: c.cause` (:83) — remove
   - module doc (:14) — drop "cause" from the not-editable list
5. `src/commands.rs` `handle_new_external` (:274: `cause: "user"`) — remove the field from the CreateChannelParams literal
6. `src/server/plugins_setup.rs` (:582: `cause: "setup"`) — remove
7. `src/server/settings.rs` test (:968: `cause: "system"`) — remove from the ChannelDef literal
8. `src/db/threads.rs` test `test_channel` (:2153: `cause: "test"`) — remove

### omni-stack — drop the yml keys

`config/channels.yml`: remove all 10 `cause:` lines (every channel entry has
one: mattermost-* user/setup, cron/kanban/g30-* system).

### NOT in scope

- `threads.cause`, messages `role='cause'`, `/api/threads/filters` `causes`
  filter — thread concept, stays.
- Dashboard: no channel-cause reads exist (only msg-role cause labels).
- deploy tests: no channel-cause assertions exist.

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- `grep -rn "cause" src/channels_yaml.rs src/db/channels.rs
  src/server/channels.rs` → only doc/comment remnants acceptable, zero field
  reads; `grep -n "cause" config/channels.yml` → empty.
- `GET /channels` response: no `cause` key on any entry (API + dashboard
  proxy both).
- Channel create via `$new` and setup-plugin channel creation still work
  (no cause in the CreateChannelParams literal compiles away cleanly).

## Non-goals

- Do NOT touch thread cause / message role cause / filters.
- Do NOT change channel behavior (readonly/closed/plan semantics).
- Do NOT rename remaining fields.

## Repos

- omniagent (all 8 source files above)
- omni-stack (config/channels.yml)

## Deliverable

Commit + push to origin/main on BOTH repos, report the commit SHAs. The
channel API and channels.yml must no longer carry `cause`.
