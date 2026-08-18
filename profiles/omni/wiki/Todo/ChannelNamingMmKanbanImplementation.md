# `$new [name]` — Optional First Argument Creates/Updates a Channel By Name

> Status: planned (omnidev board task)
> Scope: omniagent core (src/commands.rs + src/platform/external/client.rs)

## Goal

The omnistable/omnidev `prepare` creates a Mattermost channel literally named
`mm-kanban` and posts `$new mm-kanban` so omniagent registers it. Today the
registered omniagent channel key is `mattermost-wkbugy5x` (ugly, derived from
the MM resource id), NOT `mm-kanban`.

**User-corrected design (2026-08-18):** `$new` accepts an OPTIONAL first
argument. When defined, it creates a channel with THAT name (or updates the
existing channel with that name — upsert by name). When absent, keep the
current `{platform}-{first8}` derivation (bare `$new` behavior unchanged).

## Root cause (verified)

`handle_new_external` (src/commands.rs:256-280) derives the channel name:

```rust
let name = format!(
    "{}-{}",
    platform,
    resource_identifier.chars().take(8).collect::<String>()
);
```

The `$new mm-kanban` TEXT is parsed (commands.rs:163 strips the `$new`
prefix via `parse_new_command`) but the name argument is DROPPED —
`handle_new_external(&pool, &plugin_name, &inbound.resource_identifier)`
(client.rs:793) receives only platform + resource id. MM channel
`mm-kanban` (id `wkbugy5xcff1teeqgnty5ck4io`) → key `mattermost-wkbugy5x`.

## Change

1. **omniagent — src/commands.rs `parse_new_command`**: accept an optional
   first argument. `$new` / `$new mm-kanban` / `//new` / `//new mm-kanban`
   all parse; `rest` after the prefix is the optional channel name
   (empty/whitespace = no name). Extend `NewCommand` with
   `name: Option<String>` (or pass the parsed name through).
2. **omniagent — `handle_new_external`**: add `name: Option<&str>` param.
   - When `name` is Some(non-empty): create a channel with key/name = `n`
     VERBATIM, or UPDATE the existing channel with that name (upsert by
     name — reuse `create_channel`'s existing `ON CONFLICT (name) DO
     UPDATE` path which already rewrites platform/resource_identifier; do
     NOT create a duplicate). This is `$new mm-kanban` → channel key
     `mm-kanban` pointing at the mm-kanban MM channel.
   - When `name` is None/empty: keep current `{platform}-{first8}`
     derivation (backwards compat for bare `$new`).
3. **omniagent — call site** (src/platform/external/client.rs:791-807):
   parse the name from `inbound.text` (after the `$new`/`//new` prefix) and
   pass it to `handle_new_external`.
4. **omni-stack — config/boards.yml**: change the `omnidev` board channel
   from `mattermost-wkbugy5x` to `mm-kanban`.
5. **omni-stack — config/channels.yml**: rename the `mattermost-wkbugy5x`
   key to `mm-kanban` (same platform/resource_identifier/profile/model/
   provider — runtime PATCH earlier set provider `deepseek`, model
   `deepseek-v4-flash`). Renaming the yml key IS the rename (PATCH cannot:
   channels.rs handler returns "Channel name is the yml key and cannot be
   renamed via PATCH").

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- `$new mm-kanban` → GET /channels shows key `mm-kanban` (platform
  mattermost, resource_identifier = MM channel id). Re-posting `$new
  mm-kanban` does NOT create a duplicate — it updates the existing
  `mm-kanban` channel.
- Bare `$new` still creates `{platform}-{first8}` (backwards compat).
- boards.yml `omnidev` → `channel: mm-kanban`; a task on the omnidev board
  with no channel_id resolves to channel `mm-kanban` (dispatcher
  resolve_task_channel fallback, kanban_dispatch.rs:260-263).

## Non-goals

- Do NOT change the Mattermost channel itself (it is already named
  `mm-kanban`).
- Do NOT rename other channels (mattermost-stable-channel etc.).
- Do NOT touch the board resolution chain (task > board > channel > global).

## Repos

- omniagent (src/commands.rs, src/platform/external/client.rs + tests)
- omni-stack (config/boards.yml, config/channels.yml)

## Deliverable

Commit + push to origin/main on BOTH repos, report the commit SHAs. After
landing, omnistable setup+prepare must register the channel as `mm-kanban`
(verify via GET /channels).
