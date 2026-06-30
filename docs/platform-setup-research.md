# Platform Setup Function — Feasibility Research

## Goal

Extend the platform plugin protocol so that platform plugins can expose a **`setup()`** method. When available, the omni-dashboard shows a purple **"Setup"** button on the `/platforms` page, left of the "Reinstall" button. Clicking it triggers the setup process.

For **Mattermost**, the setup would migrate the current Python `mm-setup.py` into the Rust `mattermost-platform` plugin code.

## Current Architecture

### Plugin Protocol (MCP-style JSON lines over stdio)

Each platform plugin is a standalone binary that communicates via JSON-lines on stdin/stdout:

- **`initialize`** → returns plugin name + capabilities
- **`deliver`** → send a message to a channel
- **`edit_message`** → edit an existing message
- **`delete_message`** → delete a message  
- **`react`** → add emoji reaction

The main request dispatch in `main.rs` (line 733):

```rust
let response = match request.method.as_str() {
    "initialize" => handle_initialize(req_id).await,
    "deliver" => ...
    "edit_message" => ...
    "delete_message" => ...
    "react" => ...
    _ => make_error(req_id, -1, &format!("Unknown method: {}", request.method)),
};
```

### Backend (omniagent)

- `server/plugins.rs` — REST API endpoints for plugin management:
  - `GET /api/plugins` — list all plugins
  - `POST /api/plugins/{name}/config` — update config
  - `POST /api/plugins/{name}/enable` / `disable` — toggle
  - `POST /api/plugins/{name}/install` — compile + register
  - `POST /api/plugins/{name}/reinstall` — recompile + reload
  - `DELETE /api/plugins/{name}` — uninstall

- `plugin/mod.rs` — defines `PluginManifest`, `PluginCapabilities`, `ConfigSchemaField`

  Current `PluginCapabilities`:
  ```rust
  pub struct PluginCapabilities {
      pub inbound: bool,
      pub outbound: bool,
  }
  ```

### Frontend (omni-dashboard)

- `src/pages/platforms.ts` — renders platform cards with buttons for:
  - Uninstall
  - **Reinstall** (cyan)
  - Install/Enable/Disable
  - Expand config

- Buttons are rendered inline in `renderPlatformsPage()` based on plugin status

### Mattermost Platform Plugin

- Source: `/opt/workspace/omni-stack/plugins/platforms/mattermost/src/main.rs` (1562 lines)
- Single `main.rs` file — MattermostClient + protocol handlers + WebSocket/polling inbound
- Config schema defined in `plugin.json` (7 fields: server_url, access_token, polling_enabled, polling_interval, channel_ids, bot_username, connection_mode)

### Current Setup Script

- `/opt/workspace/omni-stack/scripts/mm-setup.py` — Python script that:
  1. Reads config from env vars (MM_USERNAME, MM_USER_PASSWORD, etc.)
  2. Logs into Mattermost API
  3. Creates users (if not exist)
  4. Creates team
  5. Adds members
  6. Creates channel
  7. Creates bot account + token
  8. Updates `.env` with MATTERMOST_ACCESS_TOKEN and MATTERMOST_CHANNEL_IDS

## Proposed Architecture

### 1. Add `setup` capability to PluginCapabilities

In `plugin/mod.rs`:

```rust
pub struct PluginCapabilities {
    pub inbound: bool,
    pub outbound: bool,
    #[serde(default)]
    pub setup: bool,  // NEW
}
```

### 2. Add `POST /api/plugins/{name}/setup` endpoint

In `server/plugins.rs`, add a new route and handler:

```rust
.route("/api/plugins/{name}/setup", post(setup_plugin_handler))
```

The handler would:
1. Look up the plugin's manifest to check if it advertises `capabilities.setup = true`
2. If it's a platform plugin, send a `"setup"` JSON-RPC request to the running subprocess
3. The subprocess runs the setup logic (may take a while) and returns success/error
4. If it's not a platform plugin (or no running subprocess), spawn the binary with `"setup"` method, wait for result, then exit

**Alternative (simpler):** Instead of routing through the running subprocess, the backend can spawn the plugin binary with a `--setup` flag or send a one-shot `setup` request over stdio, wait for completion, and return the result. This avoids coupling to the running platform plugin's lifecycle.

### 3. Add `setup` method to platform protocol

In `main.rs` of the Mattermost plugin (and other platform plugins):

```rust
"setup" => handle_setup(req_id, &config).await,
```

Where `config` contains the setup parameters from the user (team name, channel name, etc.).

The `handle_setup` function would:
1. Read the config from the request params (or env vars if not provided)
2. Validate required fields (setup_team, setup_channel, bot_user)
3. Run the setup process: create team, channel, users, etc.
4. Return success with details (team_id, channel_id, bot_token)
5. On error, return error with descriptive message

### 4. Config fields for setup

Add these fields to the Mattermost `plugin.json` `config_schema`:

```json
{
  "key": "setup_team",
  "label": "Setup Team Name",
  "type": "string",
  "required": false,
  "description": "Team to create during setup. Required for setup."
},
{
  "key": "setup_channel",
  "label": "Setup Channel Name",
  "type": "string",
  "required": false,
  "description": "Channel to create during setup. Required for setup."
},
{
  "key": "admin_user",
  "label": "Admin Username",
  "type": "string",
  "required": false,
  "description": "Admin account for setup (optional, defaults to first admin)"
},
{
  "key": "admin_password",
  "label": "Admin Password",
  "type": "secret",
  "required": false,
  "secret": true,
  "description": "Admin password for setup (optional)"
},
{
  "key": "test_user",
  "label": "Test Username",
  "type": "string",
  "required": false,
  "description": "Test user to create during setup (optional)"
},
{
  "key": "test_password",
  "label": "Test Password",
  "type": "secret",
  "required": false,
  "secret": true,
  "description": "Test user password (optional)"
}
```

These can be pre-filled via env var references in the plugin.json `env` block:

```json
"env": {
  "MM_SETUP_TEAM": "${MM_TEAM}",
  "MM_SETUP_CHANNEL": "${MM_CHANNEL}",
  ...
}
```

### 5. Frontend: purple "Setup" button

In `platforms.ts`, add the button in `renderPlatformsPage()` when the plugin has `manifest.capabilities.setup === true`:

```typescript
${p.manifest?.capabilities?.setup ? `
  <button type="button" class="plugin-setup-btn" style="background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.3);border-radius:6px;padding:0.25rem 0.5rem;cursor:pointer;font-size:0.75rem;color:var(--accent-purple);">Setup</button>
` : ""}
```

Wire the click handler in `wirePlatforms()` to call `POST /api/plugins/{name}/setup`.

## Feasibility

### ✅ Highly Feasible

| Component | Effort | Complexity |
|-----------|--------|------------|
| Backend: add `setup` field to `PluginCapabilities` | 1 file, ~3 lines | Trivial |
| Backend: add `POST /api/plugins/{name}/setup` route | 1 file, ~50 lines | Low |
| Backend: spawn plugin with setup method | Reuses existing subprocess spawning | Low |
| Mattermost: implement `handle_setup` in main.rs | ~300-400 lines | Medium (port mm-setup.py to Rust) |
| Mattermost: add setup config fields to plugin.json | ~50 lines | Trivial |
| Frontend: add purple Setup button | ~20 lines | Trivial |
| Frontend: wire click handler | ~30 lines | Low |

### Key Details

1. **The setup config fields are OPTIONAL in the schema** — the platform doesn't require them to function. They're only needed for the setup action.

2. **The setup action can be one-shot** — the backend spawns the plugin with `{"method": "setup", "params": {...}}` over stdio, waits for the response, and returns it to the frontend. It doesn't need to interfere with the running plugin's main loop.

3. **Error propagation** — if setup fails (e.g., missing required field), the plugin returns a JSON-RPC error with a descriptive message, which is shown to the user via toast.

4. **The Python mm-setup.py code can be directly translated to Rust** — the MattermostClient already has all the needed API calls (create_post, get_me, get_teams, get_users, etc.). The setup would need additional methods: `create_user()`, `create_team()`, `add_team_member()`, `create_channel()`, `add_channel_member()`, `create_bot_and_token()`.

5. **Token management** — the setup action could return a new access token. The backend could optionally update the plugin config automatically.

### Potential Pitfalls

- **Long-running setup**: The setup may take 30+ seconds (API calls + waiting). The HTTP request needs a generous timeout or use an async pattern (start setup, return immediately, poll for completion).
- **Plugin already running**: If the plugin is already running and connected, the setup may need to restart it afterward to pick up new config (channel IDs, token, etc.).
- **Config storage**: The setup may need to write back to the YAML config file and trigger a hot-reload. This requires the backend to have access to the data_dir path.

### Recommended Approach

1. **Short-term** (simplest): When user clicks "Setup", the backend spawns a one-shot process running the plugin binary with `--setup` flag and the config as env vars. The process exits after setup completes. This requires zero protocol changes.

2. **Long-term** (more elegant): Add `setup` to the platform protocol method dispatch. The backend sends a setup request to the running platform plugin via stdio, and the plugin processes it in its main loop. This allows the setup to have access to the running plugin's full state.

**Recommendation**: Start with approach 1 (one-shot) — it's simpler, doesn't affect the running plugin, and can be implemented entirely in the backend handler + plugin code.

## Files to Modify

| File | Change |
|------|--------|
| `omniagent/src/plugin/mod.rs` | Add `setup: bool` to `PluginCapabilities` |
| `omniagent/src/server/plugins.rs` | Add route + handler for `POST /api/plugins/{name}/setup` |
| `omni-stack/plugins/platforms/mattermost/plugin.json` | Add setup config fields + env mappings |
| `omni-stack/plugins/platforms/mattermost/src/main.rs` | Add `handle_setup()` + MatttmostClient setup methods |
| `omni-dashboard/repo/src/pages/platforms.ts` | Add Setup button + click handler |
| `omni-stack/.env.example` | Add MM_SETUP_* vars (optional) |
