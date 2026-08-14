# Log

## 2026-08-14

- Added `Todo/StopThreadSurgicalImplementation.md` (NEW): `POST /stop-thread/{id}` must be SURGICAL — it currently cancels the channel's processing token unconditionally (`src/server/mod.rs:486-497`), and the handler's prompt `tokio::select!` cancellation drops whatever thread is mid-`process_thread`, orphaning it in `status='processing'` forever (respawned handler only claims `pending`). Incident 2026-08-14: stopping thread 420 killed the dispatch-gate TESTER 412 mid-verification for 1h48m; its task kept a stale `thread_status='running'`. Fix: cancel the handler only when the target IS the active thread; always clear the stopped kanban thread's task `thread_status` (honor `StopRecovery::Block.clear_thread_status`, clear on Noop-when-set); handler cancellation branch skips its in-flight thread as a safety net. Mirrors kanban task (omniagent-dev workflow). Updated index.md.
- Added `Todo/KanbanStatusChangeDispatchImplementation.md` (NEW): dispatch a kanban task when its status is CHANGED (running→executor, testing→tester, review→reviewer, role-gated; stale pending/processing threads skipped to terminal `skipped` first); `POST /kanban/tasks/{id}/redispatch` recreates the role thread for a task already in running/testing/review WITHOUT changing status (no-op when a non-terminal thread exists or the role isn't defined); `POST /kanban/dispatch` simplifies to move-to-running via the shared dispatch code (no duplicate thread creation); startup recovery unified with the redispatch logic. Mirrors kanban task `task_18cbc3b0765efa85` (omniagent-dev workflow). Updated index.md. Amended post-creation: cross-task coordination note routing the stale-thread skip through the terminal-status-invariant task's single choke point (task_18cb83096b238872) when it exists. Chained to board tail `task_18cbb662fc71751d` after a dispatch mistake (thread 420 was auto-dispatched while the dispatch-gate tester was mid-verification; stopped + reset to todo + dependency added — serial-chain rule).
- Added `Todo/CacheFriendlyCompactionImplementation.md` (NEW): compaction must produce a stable summary block reused verbatim so DeepSeek prefix caching survives; align plugin char/token budgets with the core (plugin was at 100K chars vs 501K-char live threads → compaction every iteration → cached_tokens frozen at ~12K).
## 2026-08-13

- Added `Todo/MaxTokensTruncationRetryImplementation.md` (NEW, rewritten 2026-08-14): global `max_tokens_on_truncation` escalation — normal calls keep `max_tokens: 4096`, `finish_reason=length` retries ONCE with the larger budget + preserved reasoning + shorter-answer nudge, second truncation fails fast. Replaces the earlier per-role max_tokens design (threads.max_tokens column + migration + workflows.yml role fields) and the fail-fast-on-reasoning-only heuristic — both rejected by the operator 2026-08-14. Mirrors kanban task (omniagent-dev workflow). Updated index.md.
- Added `Todo/DefaultChannelsImplementation.md` (NEW): four default-channel
  settings (cli/schedule/hook/kanban) as selects over existing channels;
  platform-less channel = type cli; empty channel → thread created with '' then
  fails "no channel defined" with the record kept; remove kanban/cron/hook
  channel platforms + ensure_cron_channel. Mirrors kanban task (omniagent-dev
  workflow). Updated index.md.
- Amended channels.yml task body (task_18cb400db3daa540): 'kanban'/'cron' seed
  channels keep their names but have NO platform (platform-less = cli); the
  legacy `platform: kanban` / `platform: cron` values are gone from
  channels.yml; scheduler resolves 'cron' by NAME (sibling default-channels
  task replaces ensure_cron_channel with the default-schedule-channel setting).
- Added `Todo/PlanNormalizationImplementation.md` (NEW): eliminate the legacy
  `planning_mode` field everywhere — drop `planning_mode` columns from
  threads/kanban_tasks (channels/hooks/cron_jobs die with sibling table drops),
  remove the `PlanningMode` bool|string enum from tasks.yml (schedules/hooks)
  and the API/dashboard fields; single `plan` bool remains. Mirrors kanban task
  (omniagent-dev workflow). Updated index.md.
- Amended channels.yml task body (task_18cb400db3daa540): channels.yml identity
  is `platform` + `resource_identifier` ONLY (no external_id — always equal,
  derived for API compat); single `plan` bool field (not planning_mode —
  aligned with the normalization task); create_channel upserts by NAME and
  rewrites platform+resource_identifier when the same name arrives from a
  different platform (channel is not pinned to its first platform).
- Added `Todo/PluginRestartEndpointImplementation.md` (NEW): fix
  `POST /api/plugins/{type}/{source}/{name}/restart` to dispatch by type —
  `restart_plugin_handler` currently calls `reload_platform_plugin` only and
  silently no-ops for tools; route it through `reload_tool_plugin` for tools /
  `reload_platform_plugin` for platforms / provider refresh for providers.
  Also make `enable` a no-op when the plugin is already enabled (today it
  force-restarts the MCP client). Mirrors kanban task (omniagent-dev
  workflow). Updated index.md.

## 2026-08-12

- Added `Todo/HooksImplementation.md` (NEW): the versioned implementation plan for the
  event-driven Hooks system (thread_started / thread_finished / new_message) — hook
  definition fields, counter semantics (default 1, JSON per-scope counters, trigger+reset),
  scope resolution (global / channel by name or all / profile by name or all), both execution
  modes (agentic thread spawn + actions.yml action), infinite-loop protection (hook-caused
  threads/messages never re-trigger), and error isolation (hook failures never affect the
  main agent loop). Mirrors kanban task `task_18cb1c10324f7240` (omniagent-dev workflow,
  thread 74). Updated index.md.

## 2026-08-04

- Added `Todo/WorkflowImplementation.md` (NEW): the versioned implementation plan for the
  role-based kanban workflow (executor/tester/reviewer) — distills the full v6 research
  (`data/research/workflow-role-based-kanban.md`, working-tree only) into schema, status
  machine, fail-task matrix, retry semantics, prompt-plugin concerns, phases 0–7, and the
  integration test matrix. Updated index.md + relevant-index.md.
- Added mandatory verification + review-before-commit requirements after the Python
  prompt plugin shipped without MEMORY/skills (agent never functionally verified):
  - templates/dev-development.md: Testing section now MANDATORY before commit —
    functional end-to-end verification (call actual tools/endpoints, assert output,
    compare against reference/Rust original), add tests or capture evidence. New
    "Review before commit (MANDATORY)" section — re-read diff as reviewer, check exact
    tool names, `$env:VAR` vs `${VAR}`, scratch files.
  - templates/code-improvement.md: same upgrades.
  - skills/workspace-development.md: new "Verifying a plugin/tool deliverable" section
    (exact tool names, /mcp/execute functional calls, reference equivalence, env-ref
    resolution) + `${VAR}`-is-literal pitfall.
  - wiki Reference/Verification-and-Review.md (NEW): the requirements + why + report
    shape. index.md updated.

## 2026-08-03

- Established the 4-layer Agent Guidance Architecture (memory → templates → skills →
  wiki) and documented it in:
  - wiki Reference/Agent-Guidance-Architecture.md (the model, conventions, why it matters)
  - AGENTS.md (Agent Guidance Architecture section)
- Reworked guidance content to match the model:
  - MEMORY.md: now always-know only (filesystem access, tool capabilities, mount map,
    universal discipline). Removed task-shaped budget numbers and the research workflow
    (they moved to the dev/research templates). Fixed stale claim: filesystem_read now
    HAS offset/limit paging.
  - templates/dev-development.md: dev-flavor budget rules + large-file paging guidance.
  - templates/research.md (NEW): research-flavor workflow (batch fetches, notes-first,
    output quality + path) — research exploration is by-design heavy, so its budget
    rules differ from dev.
  - skills/workspace-development.md: concrete paging/grep examples, fixed stale
    filesystem_read claim.
- Corrected wiki Reference/Container-Mount-Map.md: the mount map is omni-stack →
  /opt/omni and /opt/workspace → /opt/workspace (old docs said /opt/data / omni-workspace).
- Added wiki Reference/Budget-and-Context.md: thread budget, compaction mechanics
  (tool-result excerpts), prompt context blocks, filesystem_read paging.
- Updated index.md and relevant-index.md.

## 2026-06-27

- Created wiki pages documenting:
  - Deployment Checklist: correct procedure for deploying compose services
  - Container Mount Map: volume mount mappings and their implications
- Updated AGENTS.md with:
  - Tool capability reference table
  - Docker & Deployment Pitfalls section (5 pitfalls)
- Updated MEMORY.md with:
  - No shell tool warning
  - Container volume mount map
  - Port checking limitation

