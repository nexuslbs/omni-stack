# Channel Naming: `$new <name>` Creates a Channel Named `<name>` (mm-kanban)

> Status: planned (kanban task TBD)
> Scope: omniagent core (src/commands.rs + src/platform/external/client.rs) + omni-stack (config/boards.yml, config/channels.yml)

## Goal

The omnistable/omnidev `prepare` creates a Mattermost channel literally named
`mm-kanban` and posts `$new mm-kanban` so omniagent registers it. Today the
registered omniagent channel key is `mattermost-wkbugy5x` (ugly, derived from
the MM resource id), NOT `mm-kanban`. Boards.yml must be able to reference the
channel as `mm-kanban`.

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

1. **omniagent — src/commands.rs `handle_new_external`**: accept an optional
   `name: Option<&str>` argument. When provided (non-empty), use it VERBATIM
   as the channel key/name (`mm-kanban`); fall back to the current
   `{platform}-{first8}` derivation when absent (backwards compat for bare
   `$new` / `//new`). The call site at client.rs:793 must pass the name from
   the inbound text (parse `$new <name>` / `//new <name>`; the current
   `parse_new_command` rejects arguments — extend it or parse at the call
   site). Keep `external_id`/`resource_identifier` = the MM channel id.
2. **omni-stack — config/boards.yml**: change the `omnidev` board channel
   from `mattermost-wkbugy5x` to `mm-kanban`.
3. **omni-stack — config/channels.yml**: rename the `mattermost-wkbugy5x`
   key to `mm-kanban` (same platform/resource_identifier/profile/model/
   provider — the runtime PATCH earlier set provider `deepseek`, model
   `deepseek-v4-flash`). This is the LIVE channel the running stack uses;
   renaming the yml key is the rename (PATCH cannot rename: channels.rs
   handler returns "Channel name is the yml key and cannot be renamed via
   PATCH").

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- `$new mm-kanban` on a fresh registration creates channel key `mm-kanban`
  with platform `mattermost`, resource_identifier = MM channel id.
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
