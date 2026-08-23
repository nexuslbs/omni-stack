# Plugin Restart Endpoint — Fix `/restart` to Handle All Plugin Types (Implementation)

**Status:** IMPLEMENTED 2026-08-13 (omniagent `0245407` — /restart dispatches by type (tool/platform/provider); enable is a no-op when already enabled)
**Date:** 2026-08-13
**Scope:** omniagent (single repo change)

## Goal

`POST /api/plugins/{type}/{source}/{name}/restart` must actually restart a
plugin of ANY type (tool / platform / provider). Today it only handles
platforms — for a tool plugin it silently does nothing. Also, `enable` on an
already-enabled plugin must be a NO-OP (idempotent), not a forced restart.

## Why

- Restarting a tool plugin (e.g. the docker `mcp-server-compose` MCP server
  after swapping its binary) currently requires the `/enable` hack: calling
  `POST /api/plugins/tools/built-in/docker/enable` on an already-enabled
  plugin forces a client teardown + re-spawn. That is semantically wrong —
  `enable` should do nothing when the plugin is already enabled, and there
  should be a dedicated restart endpoint.
- The route `POST /api/plugins/{type}/{source}/{name}/restart` EXISTS
  (`src/server/mod.rs:192-196`) but the handler ignores `p_type` and calls
  only `reload_platform_plugin` — for tools it looks up platform restart
  signals, finds none, tries `start_platform_plugin`, fails to find a
  platform config, logs an error, and returns `{"success": true}` anyway.
- The correct tool-restart code (`reload_tool_plugin`,
  `src/server/plugins_reload.rs:213-250`) already exists — it does
  `remove_client → initialize_single_server → remove_server_tools →
  register_tools` — but it is ONLY reachable via the config-update handler
  (`src/server/plugins.rs:141-143`) or install/reinstall paths
  (`src/server/plugins_install.rs:119, 226`). There is no direct route.

## Verified inventory (do not re-derive)

- **Route**: `src/server/mod.rs:192-196` — `/api/plugins/{type}/{source}/{name}/restart` → `restart_plugin_handler`.
- **Handler bug**: `src/server/plugins_enable.rs:168-174` — `restart_plugin_handler` destructures `Path((_p_type, _source, name))`, ignores the type, and calls `reload_platform_plugin(&state, &name)` unconditionally.
- **`reload_platform_plugin`**: `src/server/plugins_reload.rs:49-85` — signals a restart via `platform_restart_signals` map, or `start_platform_plugin` if not running. Platform-only.
- **`reload_tool_plugin`**: `src/server/plugins_reload.rs:213-250` — the correct tool path: `remove_client(name)` → `initialize_single_server(data_dir, name)` → `remove_server_tools` + `register_tools`. No route calls it directly today.
- **enable already-enabled branch**: `src/server/plugins_enable.rs:25-44` — when `entry.enabled && entry.source == source`, it currently FORCE-RESTARTS: platform → `reload_platform_plugin`, tool → `remove_client` + `initialize_single_server` + `register_tools`. This must become a no-op.
- **Type dispatch**: `src/plugins_yaml.rs:115-123` — `PluginYamlType::from_type_str("tools")` → `Tool`; validate_plugin_type (`src/server/plugins_types.rs:33-43`) allows `tools|platforms|providers`. The provider restart path (from enable handler `src/server/plugins_enable.rs:101-104`): `crate::llm::refresh_provider_metadata()` + `super::plugins_env::reload_plugins(state.clone()).await`.

## Change (single file: `src/server/plugins_enable.rs`)

1. **`restart_plugin_handler`** (`:168-174`): use `p_type` →
   `PluginYamlType::from_type_str(&p_type)` and dispatch:
   - `Tool` → `reload_tool_plugin(&state, &name).await`
   - `Platform` → `reload_platform_plugin(&state, &name).await`
   - `Provider` → `refresh_provider_metadata()` + `reload_plugins`
   Return `{"success": true}` as today.
2. **`enable_plugin_handler`** (`:25-44`): when already enabled
   (`entry.enabled && entry.source == source`), return the plugin detail
   WITHOUT restarting — remove the `remove_client`/`initialize_single_server`
   block and the `reload_platform_plugin` call from that branch. Only the
   not-yet-enabled path (below `:44`) keeps its start logic.

## Non-goals / DO NOT CHANGE

- No new route needed — `/restart` already exists; fix its dispatch.
- Do NOT touch `reload_tool_plugin` / `reload_platform_plugin` internals.
- Do NOT touch install/reinstall/config handlers (`plugins_install.rs`,
  `plugins.rs` update_config_handler).
- Do NOT touch the dashboard, omni-stack, or db-migrations.
- Do NOT set `SQLX_OFFLINE=true` in any gate (dev overlay already sets false).

## Verification gates (BARE commands — no `cd`, no env redefs)

```bash
cargo check --workspace --all-targets
cargo test -p omniagent --lib
cargo fmt --check
cargo clippy -p omniagent -- -D warnings
```

Add a unit test for the new dispatch (e.g. assert `restart` routing calls the
tool path — or at minimum that `from_type_str` maps `"tools"` → Tool; the
handler itself is async/state-bound, so a pure helper for type→action
selection is the testable seam).

## Deliverable

- Commit + push to origin/main of `/opt/workspace/omniagent`.
- Report the commit SHA.
