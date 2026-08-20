# Field Resolution — resolve fallback fields ONCE at load

**Principle (user decision 2026-08-19, do not re-litigate):** ANY place that
uses fields that have fallbacks — kanban task fields (workflow, channel,
profile, plan, provider, model) being ONE such case, but ALSO channel fields,
provider/model fields, settings fields — anywhere there is a fallback chain —
MUST resolve the fallbacks FIRST, before any shallow use of the raw fields.
Resolve as EARLY as possible: compute the effective values once, right after
the row/config is loaded, and let consumers use the RESOLVED struct.

**The rule:** never shallow-read a field that has a fallback chain.

- Behavior paths (dispatch, fail routing, thread creation, role resolution,
  provider/model selection) consume the RESOLVED values only.
- Display-only API responses (`GET /kanban/tasks`, `/channels`, `/threads`)
  keep the RAW stored fields — the API reports what is stored, behavior uses
  what is resolved.

---

## 1. Kanban task fields — `resolve_task_defaults`

Chain: `Workflow Role > Workflow > Kanban Task > Board > Channel > Global
Settings`.

| Field | Fallback order |
|---|---|
| `workflow_id` | task → board.workflow (boards.yml) → none (plain task) |
| `channel_id` | task → board.channel → `default_kanban_channel` setting → `""` |
| `profile` | task → board.profile → channel.profile → default profile |
| `plan` | task → board.plan |
| `template` | task → board.template |

Resolver (omniagent `src/resolution.rs`):

- `TaskFallbackFields` — the raw columns that participate in the chain.
- `ResolvedTaskDefaults { workflow_id, channel_id, profile, plan, template }`
- `resolve_task_defaults(data_dir, &TaskFallbackFields) -> Result<ResolvedTaskDefaults, String>`

Fail-loud semantics (mirrors `boards::task_board`): when `boards.yml` exists
and the task's board is NULL or unknown → `Err` (the caller fails the thread
with a clear "invalid board" message — see `fail_kanban_thread_no_board`).
When `boards.yml` is absent the board contributes nothing and the task
behaves exactly like a non-board task. Never a silent empty fallback that
changes behavior.

Consumers (all use the resolved struct, none read the raw fields):

- `src/agent/fail_thread.rs` — `manual_review_decision`, `engine_transition`
  (the live fail-routing bug: board tasks carried NULL `workflow_id`, so a
  reviewer reject lost the workflow and landed on `blocked` instead of
  creating an executor rework thread).
- `src/db/threads.rs` — `create_kanban_step_thread` (dispatch,
  status-change dispatch, `/redispatch`, startup recovery all funnel here),
  `dispatch_task_for_status`.
- `src/kanban_dispatch.rs` — dispatch scan uses the shared
  `effective_channel_name` (no per-consumer resolver).
- `src/kanban_action.rs` — receives the pre-resolved context.
- `src/server/kanban.rs` — transitions operate on resolved values.

## 2. Channel fields — `resolve_channel` / `effective_channel_name`

Chain: explicit channel name → `default_<key>` channel setting → `""`.

- `effective_channel_name(data_dir, explicit, setting_name)` — data-dir
  parameterized mirror of `channels_yaml::resolve_default_channel`: an
  explicit name wins (even when unknown — the caller then fails the thread
  with "channel not found", never silently substitutes the default); else the
  named default-channel setting, but only when it names a known channel; else
  `""` (the caller fails the thread with "no channel defined").
- `ResolvedChannel { name, profile, provider, model }` —
  `resolve_channel(data_dir, explicit, setting_name)` carries the channel's
  channels.yml field overrides (profile/provider/model).
- Channel profile/provider/model fall back to global settings at thread
  identity resolution (below).

## 3. Provider/model — `ResolvedThreadProviderModel`

Chain: thread-stamped → channel → profile → global settings → env
(`LLM_PROVIDER`/`LLM_MODEL`, with `openai`/`gpt-4` fallbacks).

- The canonical resolver is `db::threads::resolve_thread_identity`,
  called ONCE at thread creation (`create_thread_with_cause`) and persisted
  on the thread row; running threads never re-resolve it.
- `src/resolution.rs` exposes the `ResolvedThreadProviderModel` projection
  (provider + model) for consumers that only need those two fields.

## 4. Settings — resolved-at-load snapshot

- `src/server/settings.rs` — `load_settings_file(data_dir)` reads
  settings.yml (nested sections) into a flat key map.
- `src/agent/config.rs` — `AgentConfig` is the resolved-at-load snapshot:
  every field is read once via `get(key, default)`; consumers read the
  snapshot fields and NEVER re-apply defaults.
- `src/resolution.rs::effective_channel_name` uses the same settings map for
  the `default_*` channel keys.

---

## Why this matters (the triggering bug)

Fail routing in `src/agent/fail_thread.rs` used to resolve the workflow ONLY
from `kanban_tasks.workflow_id`. Board-based tasks (board=omnidev, workflow_id
NULL) therefore lost their workflow entirely: `has_wf=false`,
`has_executor_role=false` → `route_fail_tool` F1 ("running") → `blocked`.
Live: reviewer thread 51 called `builtin_fail-thread workflow_step="running"`;
`kanban_history` #127 recorded "no executor role in workflow for status
review"; the task blocked instead of an executor rework thread. With the
resolver, the board supplies the workflow/channel/profile/plan at load and the
fail matrix routes exactly as for explicit-field tasks.

## Regression tests

`src/resolution.rs` unit tests cover: plain task (boards disabled), board task
gets board defaults (THE bug), task wins over board, invalid board fails
loud, `default_kanban_channel` setting fallback, profile chain
(task → board → channel → default), effective channel name chain, channel
field overrides, resolved provider/model projection, settings snapshot.
