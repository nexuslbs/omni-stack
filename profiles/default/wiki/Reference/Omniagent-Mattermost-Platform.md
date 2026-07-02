# OmniAgent Mattermost Platform

> Architecture, setup, operational invariants, and failure-recovery design.

## Architecture Overview

The Mattermost platform plugin (`plugins/platforms/mattermost/`) is a **standalone Rust binary** that communicates with the omniagent core via **stdin/stdout JSON-RPC** (plugin protocol). The omniagent core spawns it as a subprocess and manages its lifecycle.

### Communication Flow
```
OmniAgent Core (Rust) ←──stdio──→ Mattermost Plugin Binary (Rust)
                                           │
                                           ↓
                                    Mattermost REST API
                                    (mattermost:8065)
```

### Capabilities
- **Outbound** — Send, edit, delete messages via Mattermost REST API
- **Inbound** — Receive messages via WebSocket (default) or polling (fallback)
- **Setup** — Create teams, channels, users, bots, and tokens

### Connection Modes
- `websocket` (default) — Real-time event stream, lower latency, fewer API calls
- `polling` — HTTP poll every N seconds (configurable via `polling_interval`)

## Channel Discovery — NO MATTERMOST_CHANNEL_IDS

**The `MATTERMOST_CHANNEL_IDS` environment variable has been removed.**

The plugin discovers channels automatically at runtime via the Mattermost API:

1. `get_teams()` — which teams the bot is a member of
2. `get_user_channels()` — all channels within those teams
3. `discover_channels()` — collected and deduplicated

When the plugin starts, it calls `discover_channels()` to find all channels the bot belongs to. For WebSocket mode, it auto-discovers and listens for all channels. For polling mode, it polls all discovered channels.

When omniagent needs to deliver a message to a specific Mattermost channel, it:
1. Looks up the channel in the **omniagent `channels` table** (platform='mattermost')
2. Reads the `resource_identifier` column — which is the Mattermost channel ID
3. Passes it to the plugin's `deliver` method as `params.resource_identifier`

**The omniagent channels table is the single source of truth for channel mapping.** Channels are registered when:
- A setup run creates the setup channel
- An inbound message is received from a new channel (auto-registered by omniagent core)

## Setup Process

The setup (`POST /api/plugins/mattermost/setup`) performs a one-time initialization:

1. **Authenticate** — Login as admin to get elevated API access
2. **Find/create team** — Using `setup_team` config value
3. **Find/create setup channel** — Using `setup_channel` config value
4. **Create/find admin user** — First admin or specified by `admin_user`
5. **Create/find bot user** — Using `bot_user` / `bot_password`
6. **Register bot** — Create bot account via `/api/v4/bots`
7. **Create personal access token** — For the bot user (via admin API)
8. **Add bot to team and channel** — So it can receive messages
9. **Return credentials** — Token, team_id, channel_id, bot_user_id

The returned token is written to `.env` as `MATTERMOST_ACCESS_TOKEN`.

## Design Invariants (THE 3 RULES)

### Rule 1: No MATTERMOST_CHANNEL_IDS — Use DB Channels

**Do NOT use `MATTERMOST_CHANNEL_IDS` anywhere.**

- Channel IDs live in the **omniagent `channels` table** with `platform='mattermost'`
- The `resource_identifier` column holds the Mattermost channel ID
- When you need a channel ID, query the DB: `SELECT * FROM channels WHERE platform = 'mattermost' AND resource_identifier = '<mm_channel_id>'`
- When you need to find which Mattermost channels are active: query channels where `platform = 'mattermost' AND closed = false`
- Auto-registration of new channels happens on inbound messages — the omniagent core creates a DB channel entry when it receives a message from a channel it hasn't seen before

**Files to check for removal when modifying the platform:**
- `.env` — remove `MATTERMOST_CHANNEL_IDS` line
- `mm-setup.py` — no longer writes to `MATTERMOST_CHANNEL_IDS`
- `scripts/*.py` — no references to `MATTERMOST_CHANNEL_IDS`
- `README.md`, `AGENTS.md` — no documentation of `MATTERMOST_CHANNEL_IDS`
- Skill files — update any references
- `docker-compose.yml` / `docker-compose.mm.yml` — no env var mapping

### Rule 2: Env Changes Reload Without Restart

**Do NOT restart the omniagent container to pick up .env changes.**

The omniagent has a **`POST /api/reload`** endpoint that:
1. Re-reads `.env` line by line
2. Calls `std::env::set_var()` for each key/value pair
3. Refreshes the process environment in-place

This is also called automatically during:
- **Startup** — `main.rs` calls `refresh_env_from_file()` before registering plugins
- **Platform config update** — `reload_platform_plugin()` refreshes env before restarting the subprocess
- **Tool plugin reload** — `reload_tool_plugin()` refreshes env before reconnecting

**How to pick up new .env values after editing:**
```bash
# Via HTTP (from Vagrant host or any machine that can reach :8080)
curl -X POST http://localhost:8080/api/reload

# Then if a platform plugin's config changed, trigger its config update
# via the dashboard UI or POST /api/plugins/{name}/config
```

**Technical detail:** Docker captures the `.env` into the container environment at `docker compose up` time. Subsequent `docker compose restart` does NOT re-read the `.env` file. The `refresh_env_from_file` function works around this by reading the file from disk inside the container at runtime.

### Rule 3: No Re-Setup on Container Restart

**DO NOT re-run setup after a container restart.**

The setup is a **one-time** operation that should never need to repeat. Here's why:

1. **Tokens persist in `.env`** — The setup writes the token to `MATTERMOST_ACCESS_TOKEN` in `.env`. On container restart, `refresh_env_from_file()` at startup loads it into the process environment. If no separate `.env` volume is used, the token is embedded in the Docker env at container creation time.

2. **Token recovery on invalidation** — If the token becomes invalid (expired, revoked, or the container was rebuilt with stale Docker env vars):
   - The mattermost plugin fails to authenticate (403 from `get_me()`)
   - It logs the error and keeps trying to reconnect
   - The **admin should reload the env** (`POST /api/reload`) or **re-run setup** only if the token truly cannot be recovered
   - **Future improvement:** The plugin could auto-recover by logging in with admin credentials stored in config/admin_password, generating a new token, and writing it to `.env` automatically

3. **Fundamental guarantee:** Setup creates durable state (team, channel, bot user) in Mattermost itself. Neither Mattermost DB state nor the omniagent `.env` is lost on container restart. The only thing that can go stale is the token, because:
   - Docker captures env vars at `compose up`, not `compose restart`
   - If the token was updated in `.env` after `compose up`, the running process won't see it until `refresh_env_from_file` is called
   - `main.rs` calls `refresh_env_from_file` on startup, and the reload endpoint covers runtime changes

## Startup Flow

On omniagent container start:

1. `main.rs` calls `dotenvy::dotenv()` to load `.env` variables
2. `refresh_env_from_file()` is called to override any stale Docker env vars with current `.env` contents
3. External platform plugins are loaded from `platforms.yml` config
4. For the Mattermost plugin:
   - An `ExternalPlatformClient` is created, reading the `MATTERMOST_SERVER_URL` and `MATTERMOST_ACCESS_TOKEN` from env
   - The plugin binary binary is spawned as a subprocess
   - The plugin connects to Mattermost via WebSocket (or polling)
   - It auto-discovers all channels the bot is a member of
5. The cron scheduler starts polling for due jobs

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MATTERMOST_SERVER_URL` | Yes | Mattermost server URL (e.g. `http://mattermost:8065`) |
| `MATTERMOST_ACCESS_TOKEN` | Yes | Bot personal access token |
| `MATTERMOST_CONNECTION_MODE` | No | `websocket` (default) or `polling` |
| `MATTERMOST_POLLING_INTERVAL` | No | Seconds between polls (default: 15, min: 5, max: 300) |

**NOT used (removed):**
- ~~`MATTERMOST_CHANNEL_IDS`~~ — Use DB channels table instead

## Troubleshooting

### Token invalid after restart
1. Check that `.env` has the correct `MATTERMOST_ACCESS_TOKEN`
2. Call `POST /api/reload` to refresh the process environment
3. If the token was truly lost, re-run setup via the dashboard or `POST /api/plugins/mattermost/setup`

### Plugin won't connect
1. Check `docker logs omni-stack-omniagent-1` for `mattermost_platform` log lines
2. Verify `MATTERMOST_SERVER_URL` is reachable from inside the omniagent container
3. Check if the Mattermost server is healthy

### Channels not being received
1. The bot user must be added to the channel in Mattermost
2. The plugin auto-discovers channels via the API — if the bot isn't a member, it won't see it
3. After adding the bot to a new channel in Mattermost, it should be auto-discovered within the next polling cycle or WS event
