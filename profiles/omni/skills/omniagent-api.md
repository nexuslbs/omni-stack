# OmniAgent API (generic `omniagent-api` tool)

Use this skill when the task needs kanban task CRUD, schedule/cron CRUD
(including DELETE), run-cron triggers, review decisions, plugin lifecycle
(enable/disable/config), actions, hooks, channels, settings, or MCP tool
execution through the core omniagent HTTP API.

The consolidated `builtin_omniagent-api` tool replaces the old `kanban_*` and
`cron_*` plugin tools: ONE generic HTTP client against the core API
(`http://localhost:8080`) — you never need to know the host/scheme/port.

## How to call the API

### From inside the agent (the builtin tool)

`builtin_omniagent-api` — call the core omniagent HTTP API with:

- `method` (required): `GET`, `POST`, `PATCH` or `DELETE`
- `path` (required): API path, e.g. `/kanban/tasks`, `/schedule`, `/api/plugins`
- `body` (optional): JSON object for POST/PATCH requests

The tool returns `HTTP <status>\n<response body>`. Errors (status >= 400,
or transport failures) come back as tool errors. The base URL
`http://localhost:8080` is derived internally — never pass it in the prompt.

### From a shell (interactive debugging)

The API listens on `localhost:8080` inside the omniagent container, so exec
into it and curl:

```sh
docker exec <container> curl -s http://localhost:8080/kanban/tasks
docker exec <container> curl -s -X POST http://localhost:8080/kanban/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Fix login bug","status":"todo","board":"default","profile":"omni"}'
docker exec <container> curl -s http://localhost:8080/api/plugins | head -c 2000
```

## Endpoint map

### Kanban — `/kanban/tasks...`

| Operation | Method + path | Body |
|---|---|---|
| List board tasks | `GET /kanban/tasks` | — |
| Task detail | `GET /kanban/tasks/{id}` | — |
| Create task | `POST /kanban/tasks` | `{"title","status","board","profile","channel","priority",...}` |
| Update fields | `PATCH /kanban/tasks/{id}` | partial fields |
| Change status (move column) | `PATCH /kanban/tasks/{id}/status` | `{"status":"running"}` |
| Change position | `PATCH /kanban/tasks/{id}/position` | `{"position":N}` |
| Delete task | `DELETE /kanban/tasks/{id}` | — |
| Dependencies | `GET/POST /kanban/tasks/{id}/dependencies` | POST: `{"depends_on_id":N}` |
| Remove dependency | `DELETE /kanban/tasks/{id}/dependencies/{depId}` | — |
| History | `GET /kanban/tasks/{id}/history` | — |
| Subtasks | `GET /kanban/tasks/{id}/subtasks` | — |
| Threads | `GET /kanban/tasks/{id}/threads` | — |
| Dispatch now | `POST /kanban/dispatch` | — |
| Redispatch | `POST /kanban/tasks/{id}/redispatch` | — |
| Workflows | `GET /workflows`, `PUT/POST/DELETE /workflows/{key}` | workflow def |
| Boards | `GET /boards`, `POST /boards`, `DELETE /boards/{key}` | board def |

Create task:

```json
{"title": "Fix login bug", "status": "todo", "board": "default",
 "profile": "omni", "channel": "kanban", "priority": 10}
```

### Schedule / cron — `/schedule...`

| Operation | Method + path | Body |
|---|---|---|
| List schedules | `GET /schedule` | — |
| Schedule detail | `GET /schedule/{id}` | — |
| Create schedule | `POST /schedule` | `{"id","enabled","channel","profile","cron","prompt","plan",...}` |
| Update schedule | `PATCH /schedule/{id}` | partial fields |
| **Delete schedule** | **`DELETE /schedule/{id}`** | — (removes from tasks.yml) |
| Toggle enabled | `PATCH /schedule/{id}/toggle` | — |
| Trigger now | `POST /schedule/{id}/run` | — |
| Schedule threads | `GET /schedule/{id}/threads` | — |
| Schedule subtasks | `GET /schedule/{id}/subtasks` | — |

### Review

- `POST /review` — manual/API review decision: `{"task_id","decision","comment"}`

### Plugins — `/api/plugins...` (NOTE the `/api` prefix!)

| Operation | Method + path | Body |
|---|---|---|
| List all plugins | `GET /api/plugins` | — |
| Plugin detail | `GET /api/plugins/{type}/{source}/{name}` | — |
| Enable | `POST /api/plugins/{type}/{source}/{name}/enable` | — |
| Disable | `POST /api/plugins/{type}/{source}/{name}/disable` | — |
| Restart | `POST /api/plugins/{type}/{source}/{name}/restart` | — |
| Update config | `POST /api/plugins/{type}/{source}/{name}/config` | `{"config":{"allow_unsafe_methods":"true"}}` |
| Install / reinstall | `POST /api/plugins/{type}/{source}/{name}/install` (+`/reinstall`) | — |
| Delete | `DELETE /api/plugins/{type}/{source}/{name}` | — |
| Git-install remote | `POST /api/plugins/install-git` | — |

`{type}` ∈ `tools` | `providers` | `platforms`; `{source}` ∈ `built-in` |
`bundled` | `remote`.

Enable the fetch plugin:

```json
{"method": "POST", "path": "/api/plugins/tools/bundled/fetch/enable"}
```

### Actions — `/actions...`

| Operation | Method + path |
|---|---|
| List actions | `GET /actions` |
| Create action | `POST /actions` |
| Update action | `PUT /actions/{id}` |
| Delete action | `DELETE /actions/{id}` |
| Run action | `POST /actions/{id}/run` |

### Hooks — `/hooks...`

| Operation | Method + path |
|---|---|
| List hooks | `GET /hooks` |
| Create hook | `POST /hooks` |
| Update hook | `PATCH /hooks/{id}` |
| Toggle hook | `PATCH /hooks/{id}/toggle` |
| Fire hook | `POST /hooks/{id}/fire` |
| Delete hook | `DELETE /hooks/{id}` |

### Channels

| Operation | Method + path |
|---|---|
| List channels | `GET /channels` |
| Channel detail | `GET /channels/{id}` |
| Update channel | `PATCH /channels/{id}` |
| All channels | `GET /channels/all` |
| Platforms | `GET /platforms`, `GET /platforms/{name}/channels` |

### Settings

| Operation | Method + path |
|---|---|
| Read settings | `GET /settings` |
| Update settings | `PUT /settings` (partial) |

### MCP

| Operation | Method + path |
|---|---|
| List registered tools | `GET /mcp/tools` |
| Execute a tool | `POST /mcp/execute` — `{"name":"...","arguments":{...}}` |

## Examples

```
# List kanban board
builtin_omniagent-api(method="GET", path="/kanban/tasks")

# Create a kanban task in todo
builtin_omniagent-api(method="POST", path="/kanban/tasks",
    body={"title":"Fix login bug","status":"todo","board":"default","profile":"omni"})

# Move a task to running
builtin_omniagent-api(method="PATCH", path="/kanban/tasks/123/status", body={"status":"running"})

# Review decision
builtin_omniagent-api(method="POST", path="/review",
    body={"task_id":"123","decision":"approve","comment":"LGTM"})

# List cron schedules + trigger one
builtin_omniagent-api(method="GET", path="/schedule")
builtin_omniagent-api(method="POST", path="/schedule/nightly_cleanup/run")

# List plugins, enable one
builtin_omniagent-api(method="GET", path="/api/plugins")
builtin_omniagent-api(method="POST", path="/api/plugins/tools/bundled/fetch/enable")

# Check what tools are registered
builtin_omniagent-api(method="GET", path="/mcp/tools")
```

## Where to find the source code

The repo is https://github.com/nexuslbs/omniagent — it is NOT shipped in the
image. To read how omniagent works internally (builtin tools, plugins,
routers), clone it:

```
git clone https://github.com/nexuslbs/omniagent /opt/workspace/omniagent-src
```

Key files: `src/mcp/mod.rs` (builtin tools incl. `omniagent_api_tool`),
`src/server/*.rs` (the HTTP routers this skill documents), `src/db/*` (SQL),
`plugins/tools/*` and `plugins/platforms/*` (builtin plugins).

## Where to find docs INSIDE the running image

- **API reference / route table**: `/opt/omni/docs/api.md` (canonical),
  fallback `/app/docs/api.md` — always present in the release image
  (Dockerfile copies the repo-root `api-reference.md` after the release build). Re-derive:
  `docker exec <container> cat /opt/omni/docs/api.md`, or list
  `/opt/omni/docs`.
- **Builtin plugin manifests** (`plugin.json`: name, type, entrypoint,
  config_schema keys/types/defaults): `/app/plugins/tools/<name>/plugin.json`
  (in-image source) and `/opt/omni/plugins/tools/<name>/plugin.json`
  (runtime install). Platforms under `/app/plugins/platforms/`. Read any
  plugin's manifest to learn its tools, config fields and defaults without
  the source. E.g. `docker exec <container> cat /app/plugins/tools/fetch/plugin.json`.

## Notes

- The old `kanban_list-kanban-tasks` / `kanban_update-kanban-task` /
  `cron_list-cron-jobs` plugin tools are gone — use the generic tool instead.
- The `search` plugin provides read-only DB access (`search_database`) for
  inspecting threads/tasks/channels; prefer it over API endpoints for lookups.
- The core API binds `localhost:8080` inside the omniagent container — the
  generic tool reaches it directly, no extra config needed.
- Plugin endpoints carry the `/api` prefix (`/api/plugins/...`); the rest
  (kanban, schedule, hooks, actions, channels, settings) do not.
