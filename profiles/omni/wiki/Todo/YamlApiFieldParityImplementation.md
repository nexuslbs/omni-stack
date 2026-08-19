# yml/API Field Naming Parity

> Status: **IMPLEMENTED 2026-08-19** (omnidev board task,
> task_18cd38571ab8c1d9) — omniagent `9c52028` + `f147c52` (docs),
> omni-dashboard `305199d` + `bc4e622`, omni-deployer `3833c0c` +
> `500e1a4`, omni-stack `f3ebfdf` (skill omniagent-api.md)
> Scope: omniagent API (src/server/*.rs), omni-dashboard TS consumers,
> omni-deployer tests.py

## Rule

Config YAML property names are the source of truth — every HTTP API JSON
field that differs from the yml property name is unified to the yml name.

## Rename map (omniagent `9c52028` — refactor, 10 src/server/*.rs files)

| Old API field | New field (= yml property) |
|---|---|
| `channel_id` / `channel_name` | `channel` |
| `workflow_id` | `workflow` |
| `schedule` (cron expression) | `cron` |
| `current_profile` / `current_provider` / `current_model` | `profile` / `provider` / `model` (bare) |

Affected routers: hooks, kanban, schedule, threads, messages, channels,
memory, overview, mod, platforms. Docs: `api-reference.md` updated to parity
names (omniagent `f147c52`).

## Audit results (all 9 config yml files)

- **RENAME-API**: channel/channel_id (tasks/boards/hooks/kanban/schedule/
  threads/messages/memory/overview), `workflow_id`→`workflow`,
  `schedule`(cron)→`cron`, `current_*`→bare (channels/status/platforms).
- **KEEP-DOCUMENTED (intentionally NOT renamed)**: `plan_mode` tri-state
  (workflows.yml) vs `plan` bool (API); `/stop/{channel_id}` URL path
  params (still channel_id); `schedule_task_id` (DB-only column, no API
  field); kanban history JSON keys (stored data, not config).
- **CONSISTENT (verified, no change)**: actions.yml, plugins.yml,
  remote.yml, settings.yml, boards.yml.

## No DB migration

DB columns `channel_id` / `workflow_id` / `schedule_task_id` are unchanged —
mapped 1:1 at the SQL boundary. **SQL/DB references (e.g. `threads.channel_id`
in queries, skills, wiki) remain valid**; only HTTP API JSON field names
changed. The dashboard rename also hit the threads API consumer: `ThreadRow`
had a duplicate `channel` field after the rename (TS2300) — fixed in
`bc4e622` along with 4 pre-existing type errors (channel-config, helpers,
actions, schedule-detail).

## Repo commits

| Repo | Commit | Content |
|---|---|---|
| omniagent | `9c52028` | refactor(api): unify API field names to yml property names |
| omniagent | `f147c52` | docs(api): api-reference.md updated to parity names |
| omni-dashboard | `305199d` | TS consumers renamed (api.ts/types.ts/hooks/hooks-detail/kanban-detail/schedule-detail/schedule-list/message-card/channel-status + 5 pages) |
| omni-dashboard | `bc4e622` | fix(tsc): threads.ts duplicate `channel` + 4 pre-existing type errors → tsc-clean |
| omni-deployer | `3833c0c` | tests.py API calls updated (channel_id→channel, workflow_id→workflow, schedule→cron, current_*→bare) |
| omni-deployer | `500e1a4` | tester fix: 3 stale `schedule`→`cron` spots in tests.py |
| omni-stack | `f3ebfdf` | skill omniagent-api.md: kanban create uses `channel` |

## Verification (all PASS)

- `cargo clippy --workspace --all-targets -- -D warnings` PASS
- `cargo test --workspace`: 539 passed, 0 failed, 9 ignored + plugin suites
  13/19 env-ignored, 0 failures
- Dashboard `npx tsc --noEmit` clean; `npx vite build` (285 modules)
- Live checks against a freshly built binary in the hermetic g45-verify env
  (thread 45); remaining unrelated group failures root-caused as
  pre-existing (documented in thread 45/46)

## Impact for agents

- API bodies now use yml names: `POST /kanban/tasks` body uses `channel`;
  schedules use `cron`; channels use bare `profile`/`provider`/`model`.
- `/stop/{channel_id}` path param unchanged; `plan_mode` only in
  workflows.yml; kanban history JSON keys unchanged.
- The canonical API reference is the skill `profiles/omni/skills/
  omniagent-api.md` (updated by `f3ebfdf`).
