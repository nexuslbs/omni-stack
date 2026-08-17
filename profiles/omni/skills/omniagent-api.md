# OmniAgent API (generic `omniagent-api` tool)

Use this skill when the task needs kanban task CRUD, schedule/cron CRUD (including
DELETE), run-cron triggers, or review decisions through the core omniagent HTTP API.
The consolidated `builtin_omniagent-api` tool replaces the old `kanban_*` and
`cron_*` plugin tools: ONE generic HTTP client against the core API
(`http://localhost:8080`).

## The tool

`builtin_omniagent-api` — call the core omniagent HTTP API with:

- `method` (required): `GET`, `POST`, `PATCH` or `DELETE`
- `path` (required): API path, e.g. `/kanban/tasks`, `/schedule`, `/schedule/{id}`
- `body` (optional): JSON object for POST/PATCH requests

The tool returns `HTTP <status>\n<response body>`. Errors (status >= 400) come
back as tool errors.

## Kanban task CRUD (`/kanban/tasks...`)

| Operation | Method + path | Body |
|---|---|---|
| List board tasks | `GET /kanban/tasks` | — |
| Task detail | `GET /kanban/tasks/{id}` | — |
| Create task | `POST /kanban/tasks` | `{"title","status","board","profile","channel_id","priority",...}` |
| Update fields | `PATCH /kanban/tasks/{id}` | `{"title","description","priority",...}` |
| Change status (move column) | `PATCH /kanban/tasks/{id}/status` | `{"status":"running"}` |
| Change position | `PATCH /kanban/tasks/{id}/position` | `{"position":N}` |
| Delete task | `DELETE /kanban/tasks/{id}` | — |
| Dependencies | `GET/POST /kanban/tasks/{id}/dependencies` | POST: `{"depends_on_id":N}` |
| Remove dependency | `DELETE /kanban/tasks/{id}/dependencies/{depId}` | — |
| History | `GET /kanban/tasks/{id}/history` | — |
| Subtasks | `GET /kanban/tasks/{id}/subtasks` | — |
| Threads | `GET /kanban/tasks/{id}/threads` | — |

## Schedule / cron CRUD (`/schedule...`)

| Operation | Method + path | Body |
|---|---|---|
| List schedules | `GET /schedule` | — |
| Schedule detail | `GET /schedule/{id}` | — |
| Create schedule | `POST /schedule` | `{"id","enabled","channel","profile","cron","prompt","plan",...}` |
| Update schedule | `PATCH /schedule/{id}` | partial fields |
| **Delete schedule** | **`DELETE /schedule/{id}`** | — (removes from tasks.yml; 404 if id unknown) |
| Toggle enabled | `PATCH /schedule/{id}/toggle` | — |
| Trigger now | `POST /schedule/{id}/run` | — |
| Schedule threads | `GET /schedule/{id}/threads` | — |
| Schedule subtasks | `GET /schedule/{id}/subtasks` | — |

## run-cron (legacy endpoint)

- `POST /run-cron/{schedule_id}` — manually fire a cron job by id (proxied from
  the dashboard; `crate::scheduler::fire_cron_job_by_id`).

## Review decision

- `POST /review` — manual/API-only review decision for a kanban task
  (spec §8 R12, `manual_review_decision`).

## Examples

```
# List kanban board
builtin_omniagent-api(method="GET", path="/kanban/tasks")

# Create a kanban task in todo
builtin_omniagent-api(method="POST", path="/kanban/tasks",
    body={"title":"Fix login bug","status":"todo","board":"default","profile":"omni"})

# Move a task to running
builtin_omniagent-api(method="PATCH", path="/kanban/tasks/123/status", body={"status":"running"})

# List cron schedules
builtin_omniagent-api(method="GET", path="/schedule")

# Create a cron schedule
builtin_omniagent-api(method="POST", path="/schedule",
    body={"id":"nightly_cleanup","enabled":true,"channel":"cron","profile":"omni",
          "cron":"0 3 * * *","prompt":"Run nightly cleanup"})

# Manually trigger a schedule
builtin_omniagent-api(method="POST", path="/schedule/nightly_cleanup/run")

# DELETE a schedule (NEW — the gap the dashboard never had)
builtin_omniagent-api(method="DELETE", path="/schedule/nightly_cleanup")

# Review decision
builtin_omniagent-api(method="POST", path="/review",
    body={"task_id":"123","decision":"approve","comment":"LGTM"})
```

## Notes

- The old `kanban_list-kanban-tasks` / `kanban_update-kanban-task` /
  `cron_list-cron-jobs` plugin tools are gone — use the generic tool instead.
- The `search` plugin provides read-only DB access (`search_database`) for
  inspecting threads/tasks/channels; prefer it over API endpoints for lookups.
- The core API binds `localhost:8080` inside the omniagent container — the
  generic tool reaches it directly, no extra config needed.
