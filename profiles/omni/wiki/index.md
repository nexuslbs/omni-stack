# OmniAgent Wiki

## Index

- **Todo/**
  - [Hooks Implementation](./Todo/HooksImplementation.md): Plan of action for the event-driven Hooks system (thread_started/thread_finished/new_message) — counters, scopes, execution modes, loop protection, error isolation
  - [Workflow Implementation](./Todo/WorkflowImplementation.md): Plan of action for the role-based kanban workflow (executor/tester/reviewer) — schema, status machine, fail matrix, phases, test matrix
  - [Plan Normalization Implementation](./Todo/PlanNormalizationImplementation.md): Drop the legacy `planning_mode` field everywhere (kanban_tasks/threads columns, tasks.yml PlanningMode enum, API, dashboard) — single `plan` bool
  - [Default Channels Implementation](./Todo/DefaultChannelsImplementation.md): Default cli/schedule/hook/kanban channel settings (selects over existing channels); platform-less channel = cli; empty channel → fail-with-record
  - [Plugin Restart Endpoint](./Todo/PluginRestartEndpointImplementation.md): Fix `/api/plugins/{type}/{source}/{name}/restart` to dispatch by type (tool/platform/provider); make `enable` a no-op when already enabled
  - [Max Tokens + Truncation Retry](./Todo/MaxTokensTruncationRetryImplementation.md): Global `max_tokens_on_truncation` escalation — normal calls keep max_tokens 4096, truncated responses retry once with a larger budget + preserved reasoning, still truncates → fail fast
  - [Stop-Thread Surgical](./Todo/StopThreadSurgicalImplementation.md): POST /stop-thread/{id} must affect ONLY the target thread — no unconditional channel-handler cancel that orphans a different processing thread; stopped kanban thread clears its task's thread_status
  - [Deploy.py dev Run](./Todo/DeployPyDevRunImplementation.md): run `python3 deploy.py dev` in omni-deployer to successful completion, fixing issues mid-run; deploy must stop omnidev (fine) but NEVER omnistable (the agent's own stack) — fix STOP_TARGETS["omnideploy"] accordingly
  - [Kanban Status-Change Dispatch + /redispatch](./Todo/KanbanStatusChangeDispatchImplementation.md): status change dispatches the mapped workflow role (running→executor, testing→tester, review→reviewer); stale threads skipped first; new /redispatch endpoint recreates the role thread without changing status; dispatcher action simplified to move-to-running; startup recovery unified
  - [Cache-Friendly Compaction](./Todo/CacheFriendlyCompactionImplementation.md): Stable summary block reused verbatim so DeepSeek prefix caching survives compaction; align plugin budgets with core
- **Reference/**
  - [Agent Guidance Architecture](./Reference/Agent-Guidance-Architecture.md): The 4-layer guidance model (memory → templates → skills → wiki), what goes where, and conventions
  - [Budget & Context Mechanics](./Reference/Budget-and-Context.md): Thread budget, compaction behavior, prompt context blocks, filesystem_read paging
  - [Deployment Checklist](./Reference/Deployment-Checklist.md): How to deploy services correctly via compose
  - [Container Mount Map](./Reference/Container-Mount-Map.md): Volume mount mapping between host and container (omni-stack → /opt/omni, NOT /opt/data)
  - [Omniagent Mattermost Platform](./Reference/Omniagent-Mattermost-Platform.md): Mattermost platform architecture, setup, invariants, and recovery
  - [Verification & Review Requirements](./Reference/Verification-and-Review.md): Mandatory functional verification + review-before-commit for code deliverables (plugins, tools, services)
- **Log**
  - [log.md](./log.md): Change log

## Key Facts

- You have NO shell/terminal tool. All operations go through MCP tools.
- Docker operations: `docker_compose` MCP tool only.
- File operations: `filesystem_*` MCP tools only. `filesystem_read` supports
  offset/limit char-based paging; `filesystem_search` matches file names only.
- Port checking via `fetch_fetch` is unreliable from inside the container — use `docker_compose ps`.
- Container mount map: `/opt/workspace` == `/opt/workspace`; omni-stack == `/opt/omni`;
  omniagent == `/app`.
