# Log

## 2026-08-18 (Kanban API board validation)

Created `Todo/KanbanBoardValidationImplementation.md` — require `board` on
POST/PATCH /kanban/tasks when boards.yml present. Trigger: task_18cd061e85394a52
(hooks wiki/summaries) created via API without board sat in `todo` while the 15s
auto-dispatcher silently skipped it (kanban_dispatch.rs board gate); only after
PATCH set `board: dev` did it auto-dispatch. Verified: create handler validates
only title (src/server/kanban.rs:642), board inserted NULLIF → NULL; update
handler allows clearing board to NULL; `boards_enabled` + `task_board` helpers
already exist in src/boards.rs:175/186.

## 2026-08-18 (Hooks wiki/summaries spec)

Created `Todo/HooksWikiSummariesImplementation.md` — 2 agentic `thread_finished`
hooks (count 10): profile-scoped wiki/templates/skills maintenance + channel-scoped
summaries (existing `summaries` table, channel_id field). Verified: hooks engine
already has the event/scope/count/agentic infra + event payload
(`last_thread`/`current_thread`/`channel`/`profile`); the counter `meta`
(last_thread/last_message) is SHARED top-level across scope keys and must become
per-scope-key for per-profile/per-channel correctness; `generate_summary` tool in
the memory plugin is the auto-summary-creation code to remove (replace with a
minimal save-summary tool). 2 new skills to create: wiki-maintenance,
channel-summary.

## 2026-08-18 (deploy-suite-debugging skill)

Post-mortem of the actions-plugin saga (Aug 15–16, ~11.5h / 860 iterations /
16 iteration-cap resets / 6 compactions) distilled into NEW skill
`profiles/omni/skills/deploy-suite-debugging.md`:

1. **"tool not found" = ordering/registration bug first, harness second** — the
   actions_* tools failed because registration ran BEFORE install-git; no error
   points at the real cause (indirect-failure trap).
2. **Test incrementally**: run the failing group alone, then neighbors, only
   then the full deploy (30+ min per full run); every test must be
   self-contained — no dependence on a prior test having run.
3. **Reuse prior-execution context**: Smartness WS-1..6 durable working memory
   (notes.md per thread + context-*.json dumps + read guards + retry
   inheritance) is LANDED on omniagent main
   (f32e760/1c19ca5/cfad535/0443a96, verified live in the omnistable image:
   `plugins/tools/prompt/src/notes.rs` present) — check prior threads/notes
   before re-running, never re-derive state from scratch.

Skipped: weakening tests (assertions stay meaningful).

## 2026-08-16 (paperclip service task)

- Added `Todo/PaperclipServiceImplementation.md` (NEW): add a `paperclip`
  service to omni-stack compose — profiles `paperclip` + `all` (user's `full`
  mapped to the repo's umbrella profile `all`), pinned fixed GHCR sha
  (verified: newest release v2026.722.0 = commit e55d702 = `sha-e55d702`;
  GHCR has no semver tags, only sha-*/latest/canary/nightly/beta; `latest`
  points to a NEWER build than the newest release — do NOT use it).
  Integration decision (researched): paperclip ships the OFFICIAL
  `@paperclipai/mcp-server` (30+ typed tools + `paperclipApiRequest` escape
  hatch, Node stdio, config = API URL + key) → use it as an external MCP
  plugin via a thin omni-plugins wrapper. Rejected: custom Python plugin
  (maintenance burden as paperclip expands), skill+fetch (boilerplate).
  Fallback: thin fetch-based plugin (agent defines path/params/body).
  Mirrored as an omnistable mm-kanban dev-workflow task.

## 2026-08-16 (subtasks task completed)

- Task `task_18cc62fa1b4db34c` (Subtasks improvement) **DONE** via omnistable
  omniagent-dev workflow: executor 170 iters (92.4% cache), tester 27 iters
  (PASS, 83.0% aggregate / 90% steady-state), reviewer 26 iters (APPROVE).
  Deliverables on origin/main: omniagent `f81f91b` (efd95aa feat: unified
  manage_subtasks tool + extract_plan_steps markdown parser + user-role
  appended enforcement + retries 3→1 + categorizer fix + TOOL_GUIDANCE 13;
  f81f91b fix: numeric-string ids) — 16+8 unit tests; omni-deployer `fe4a913`
  GROUP 35 (noop test-tool-caller plan-mode e2e); omni-stack `89b8ba2`
  (allowed_tools 6× subtasks_*, template guidance). Full suite green twice
  (499 passed). Live MCP E2E against real DB confirmed manage_subtasks
  add/list/update/get_counts/delete + thread_subtasks rows. Caveat (both
  executor+tester honest, verified): running omnidev binary predates commits
  → GROUP 35 live agent-loop run deferred to next omnidev restart.

## 2026-08-16 (subtasks improvement task)

- Updated `Todo/SubtasksImprovement.md` (Planned → In implementation): added
  user-spec testing requirements — (1) automated tests with the noop provider
  `test-tool-caller` (fake agent driving tools through the real agent loop via
  JSON scripts, GROUP 12/13/14 pattern on the dedicated mattermost-test-channel);
  (2) real manual end-to-end tests: create a real omnidev dev-workflow task
  that asks the omnidev agent to run a task using subtasks, verify it runs
  successfully (subtasks created from plan → updated → thread `completed`,
  never force-failed); manual runs by BOTH executor and tester, kept SHORT
  (3-6 steps, no long builds, no local-state changes except a throwaway test
  project), omnidev only. Refreshed verified line refs (prompt_builder.rs now
  at plugins/tools/prompt/src/, response_handler.rs:323, config.rs:230/329/412,
  main_loop.rs:911/1630 injections, enable_subtasks=should_plan at main_loop
  .rs:65). Mirrored as an omnistable mm-kanban dev-workflow task (chained
  after SSH plugin task).

## 2026-08-16 (SSH plugin + subtasks research)

- Added `Todo/SshPluginImplementation.md` (NEW): builtin `ssh` tool plugin
  (plugins/tools/ssh/, mcp-server-ssh) — ssh_run/ssh_copy/ssh_status over the
  ssh/scp CLIs (present in image), keys/config from `{OMNI_DIR}/data/ssh/`
  (ssh_dir config, chmod 600 enforcement), background-task integration
  (wait-task/poll-task/cancel-task), agnostic of use; remote-development
  workflow lives in a skill + template, not the plugin; 5 registration points
  (Cargo members, Dockerfile dep-cache COPY, plugins.yml, config.json
  allowed_tools, plugin_tests.rs); G34 integration tests (local throwaway
  sshd preferred, fake-shim fallback). omnidev-only; mirrored as an omnistable
  mm-kanban dev-workflow task.
- Added `Todo/SubtasksImprovement.md` (NEW): research spec — subtasks are
  inert (0 rows in thread_subtasks): manage_subtasks tool never registered,
  write tools disabled in allowed_tools, auto-create expects JSON steps while
  real plans are `<plan>` markdown, prompt never references them, enforcement
  would force-fail if they existed. Path A-lite: add real manage_subtasks
  tool, parse markdown plans, enable tools, prompt guidance, token-safe
  enforcement (retries=1, user-role appended injection, no 3-round nudge).

## 2026-08-16

- Added `Todo/PythonTelegramPlatformImplementation.md` (NEW): Python telegram
  platform plugin in omni-plugins — platform protocol + Telegram Bot API
  (outbound send/edit/delete + inbound getUpdates polling); mock-based testing
  (no real token — never reuse hermes' bot); G33 integration tests against the
  mock; real full test needs a fresh @BotFather token for omniagent.
  omnidev-only; mirrored as an omnistable mm-kanban dev-workflow task.

## 2026-08-16 (external MCP task)

- Added `Todo/McpExternalServersImplementation.md` (NEW): external/agnostic MCP
  server support — add the 7 modelcontextprotocol Reference Servers (Everything,
  Fetch, Filesystem, Git, Memory, Sequential Thinking, Time) as remote MCPs via
  the plugin API with ≥1 live tool call each; extend the cargo-only install API
  for Python (requirements.txt) / NodeJS (package.json) deps; external OS
  binaries belong in the image, not the API; integration tests ≥1 tool per
  server with correct-return assertions. omnidev-only; mirrored as an omnistable
  mm-kanban dev-workflow task (depends on the done Kanban Boards task).
- Committed wiki spec `Todo/KanbanBoardsImplementation.md` + index/log updates
  (the boards task itself completed earlier today: omniagent 311e4f7,
  omni-dashboard de2ab45+fb4ba1c, omni-stack 2ef0569, omni-deployer c64f81e —
  GROUP 31 board integration tests).

## 2026-08-16 (boards spec creation)

- Added `Todo/KanbanBoardsImplementation.md` (NEW): boards concept for kanban
  — `config/boards.yml` in OMNIDIR (gated by file presence so omnistable is
  unaffected), `kanban_tasks.board` column, invalid-board tasks skipped by the
  dispatcher and failed truthfully on any thread-creation path (reusing
  `fail_thread`), resolution order extended to
  Workflow Role > Workflow > Kanban Task > Board > Channel > Global Settings,
  dashboard board selector (localStorage redirect, No-board reset, create/edit
  modals, delete-with-confirmation, move-to-board on task details). Dev-only;
  mirrored as an omnistable mm-kanban dev-workflow task (kanban board was
  empty — first task, no dependency chain).

## 2026-08-15

- Added `Reference/Omni-Deployer.md` (NEW): deploy harness reference — deploy.py
  dev pipeline (verified exit 0, run #10), noop-only rule (deploy DB has no LLM
  secrets; cron channel pinned to noop/test-tool-caller via
  `patch_deploy_channels_noop()`), omnistable safety invariant
  (`DEV_STOP_EXCLUDE={"omnistable"}`; omnistable only via
  `omnistable.py`/`omnistable.env`), fresh-DB-every-run constraint, root-owned
  config writes (sudo mv), schema facts that bite tests (channels table dropped
  → channel_id is a NAME; seq-0 role='cause'; task-delete detaches threads),
  test-fix patterns table (wf9 drain, atomic tasks.yml, g29/g30 races, query
  args), quick shared-tool-test iteration snippet, secrets hygiene, sqlx
  offline-cache sync notes (prepare.py `-- --tests`, chown after container
  runs). Updated index.md.

- SYNCED plugin sqlx offline caches after run #10 surfaced drift: omniagent
  `f0c3c44` (memory: 11 stale removed + 19 missing added; query: 165 entries
  never committed — now complete), and omni-deployer `1937e6e` (prepare.py
  plugin step now `cargo sqlx prepare -- --tests` so test-module queries stay
  in the cache instead of leaving a dirty tree every run).

- Completed `Todo/DeployPyDevRunImplementation.md` + kanban task
  `task_18cbd58896d6500b`: `python3 deploy.py dev` now exits 0 (run #10,
  2026-08-15) — pretests fmt/check/clippy/unit green, api_tests + plugin_tests
  green, Python integration PASS 1 + PASS 2 both ALL TESTS PASSED, shared tool
  tests 156/156 (22 tools × 3 states), omni-stack restored clean, omnistable
  never stopped (7 containers up, /health ok). Task moved to done via API with
  a completion record. The 1,238 executor threads failed on 401s — LLM key
  credits hit 0 at ~11:00 (user clarification), not a code failure. Harness
  fixes pushed to nexuslbs/omni-deployer (`8da7bd9`): noop channel pin, wf9
  channel drain, atomic tasks.yml writes, g29/g30 race fixes, query tool args
  aligned to post-migration schema.

## 2026-08-15 (earlier)

- Added `Reference/DeepSeek-Prefix-Cache.md` (NEW): root-cause + fix report for
  the systemic LLM prefix-cache misses. Symptom: thread 514 cached_tokens
  frozen at exactly 7,424 (static preamble) with 6.9% hit rate; ALL threads
  5–12%. Root cause: DeepSeek hoists `system`-role messages into the cache key;
  `upsert_system_message` remove-and-reinserts the Budget/Working Notes/
  Auto-Saved Reads blocks with changing text every iteration, breaking the
  byte-identical prefix at the static head on every call. Reproduced
  empirically (probe_final2.py: user-role rides 98.8%→99.7%, system-role
  frozen at 7,424). Fix: omniagent `9c5bb60` upserts dynamic context blocks as
  USER role (stays at conversation tail). Verified: omnidev threads 395/396 at
  52%/66.5% aggregate, steady-state 90–93%. Updated index.md.

- Added `Todo/DeployPyDevRunImplementation.md` (NEW): run `python3 deploy.py dev`
  in /opt/workspace/omni-deployer to successful completion (build → dbs →
  migrations → pretests → shared tool tests → start), fixing issues mid-run.
  deploy.py dev WILL stop omnidev (fine/expected) but must NEVER stop omnistable
  — the agent's own stack; verified `STOP_TARGETS["omnideploy"] =
  ["omnidev","omnistable"]` (shared.py:398-402) currently stops both, so the
  task first fixes the deploy script (mode-aware: dev stops only omnidev, CI
  clean-slate preserved), then runs deploy.py dev to exit 0, then verifies
  omnistable-* containers still running. Normal omniagent-dev task (no
  workspace routing). Mirrors kanban task (chained to board tail
  task_18cbcd7a8c4a6f5e). Updated index.md.

- IMPLEMENTED `Todo/KanbanStatusChangeDispatchImplementation.md` (omniagent `18d723f`): PATCH /kanban/tasks/{id}/status now dispatches the mapped role thread (running→executor, testing→tester, review→reviewer, role-gated; stale pending/processing threads skipped to terminal `skipped` first via the `mark_thread_terminal` choke point); NEW POST /kanban/tasks/{id}/redispatch recreates the role thread for a task already in running/testing/review without changing status (no-op when an active thread exists or the role isn't defined); POST /kanban/dispatch simplified to move-to-running through the shared dispatch code (duplicate thread-creation removed); startup recovery unified (skip_all_pending_threads marks terminal then redispatches stuck workflow-column tasks). Spec updated with implementation summary.

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


## 2026-08-16 (SSH plugin task COMPLETED)

- Task `task_18cc5aff745ee42c` (SSH Plugin, omniagent-dev workflow) DONE — threads 79 (executor, 152 iters, 92.0% cache), 80 (tester, 17 iters, 89.0%), 81 (reviewer, 31 iters, 92.5%) all terminal; tester PASS + reviewer APPROVE.
- Deliveries (all origin/main, 0/0):
  - omniagent `04f56d6` (492bd03 feat ssh-plugin + 04f56d6 plugin_tests): plugins/tools/ssh/ mcp-server-ssh — ssh_run/ssh_copy/ssh_status agnostic wrappers over ssh/scp (run_git subprocess hygiene, kill_on_drop, BatchMode, -F config, ssh_dir chmod-600 + re-verify), 15 unit tests.
  - omni-deployer `a69bac7`: GROUP 34 integration tests + _run_g34.py driver — verified independently: 3/3 PASS against REAL local sshd.
  - omni-stack `468d0e0`: plugins.yml ssh enable, config.json allowed_tools, dev-development.md remote paragraph, new remote-development skill.
- Live check: /api/plugins shows ssh built-in tool, status enabled.
- Note: /dev/null was missing in omnidev container mid-task (broke ssh-keygen/git) — recreated as char device; executor recovered.

## 2026-08-16 (hooks event meta task)

- Added `Todo/HooksEventMetaImplementation.md` (NEW): hooks counter JSON
  (`hook_counters.counter`) gains a top-level `meta` object with
  `last_thread`/`last_message` = the previous trigger's `current_thread` /
  `current_message`. Every trigger builds + delivers an event object
  (`last_thread`, `last_message`, `current_thread`, `current_message`,
  `channel`, `profile`) — action-mode hooks receive it merged into the action
  tool-call arguments (`arguments["event"]`), agentic-mode hooks embed it as
  JSON in the spawned thread's prompt. `new_message` events use the (currently
  unused) message_id param; thread events use the thread's last message id
  (global max messages.id when the thread has none). NEW guard: threads with
  empty channel_id or profile never trigger hooks. Existing hook-caused loop
  protection stays. No schema/migration change (JSONB shape only).
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  paperclip task (serial chain).

## 2026-08-17 (cleanup + core dispatcher task)

- Added `Todo/CleanupAndCoreDispatcherImplementation.md` (NEW): two-part task.
  (1) Extend the daily age-based cleanup (`src/main.rs:277-302`, currently
  messages + summaries only) to also delete old terminal threads (messages →
  thread_subtasks → threads, parent_id self-ref handled, non-terminal kept)
  and old kanban_history (no FK); reuse existing `delete_after_days` setting
  (default 30) with a NEW 0 = disabled guard (today 0 would delete everything).
  (2) Move the kanban dispatcher into core: extract `dispatch_handler`
  (src/server/kanban.rs:2285) into an in-process function + background loop in
  main.rs (no HTTP round-trip, no cron), new `kanban_dispatcher_interval`
  setting default 15s, remove `kanban_dispatcher` tool from the actions plugin
  (keep the other 3) + `builtin_kanban_dispatcher` from actions.yml. Fresh
  stacks currently have NO auto-dispatch (tasks.yml schedules commented out) —
  the core loop fixes this. HTTP /kanban/dispatch stays for tests.
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  hooks-event-meta task (serial chain).

## 2026-08-17 (actions plugin → omni-plugins task)

- Added `Todo/ActionsPluginPythonOmniPluginsImplementation.md` (NEW): after the
  core-dispatcher task removes `kanban_dispatcher` from the built-in actions
  plugin, the remaining 3 action tools (hindsight_populator, relevance_indexer,
  setup_knowledge_pipeline) move to a NEW python MCP plugin in
  omni-plugins/tools/actions/ (copy the tools/memory python pattern —
  plugin.json + mcp-config.json + server.py with psycopg2). Rationale (user):
  ops-side tools evolve/are replaced without releasing a new omniagent version.
  omniagent: delete plugins/tools/actions/ + Cargo workspace member + refs.
  omni-stack: remote.yml + plugins.yml source: remote. Same observable behavior
  (watermark, relevant-index.md, tasks.yml knowledge_pipeline schedule).
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  cleanup+core-dispatcher task (serial chain).

## 2026-08-17 (skills gap task)

- Added `Todo/SkillsGapImplementation.md` (NEW): closes the skills lifecycle
  loop. Verified from omnistable DB: `skills_create-skill` 0 calls,
  `skills_view-skill` 0 calls, `skills_list-skills` 3 calls (old threads
  61-63) — the agent never creates or reads skills, yet follows the 7
  hand-written skill descriptions injected into every prompt. Three fixes:
  (1) prompt plugin `get_skills` (main.rs:1188) renders the file's FIRST LINE
  as description — a create_skill file starting with `---` frontmatter would
  show as `- <name>: ---`; parse frontmatter `description:` with fallback to
  `#`-stripped line, and support the SKILL.md dir layout. (2) create_skill
  writes flat `<cat>/<name>.md`; align with Hermes conventions
  (skills/<cat>/<name>/SKILL.md + license + metadata.hermes.tags/
  related_skills + "Use when" description ≤1024). (3) prompt nudge: the
  "read one with view_skill" line never fires — add an actionable create
  trigger. Notes plugin verified healthy (63 calls, threads 71-90, durable
  working memory) — explicitly out of scope. Skills stays Rust built-in (no
  python port exists).
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  actions-python task (serial chain).

## 2026-08-17 (plugin consolidation task)

- Added `Todo/PluginConsolidationImplementation.md` (NEW): one consolidation
  pass over the plugin surface, per user direction. (1) prompt: Rust built-in
  stays default; omni-plugins tools/prompt python port (exists, unwired) is the
  experimental channel — keep both, document the source switch. (2) telegram:
  remove stale core manifest (points at nonexistent binary); python platform
  in omni-plugins (ddbc385) is real — wire remote. (3) hindsight: move to
  omni-plugins (may stay Rust), wire remote keep disabled, remove from core.
  (4) search(358)+query(929)+metrics(401) → single search plugin, tools kept
  and renamed search_* (7 tools). (5) fetch/skills/notes stay. (6) cron+kanban
  → ONE generic core builtin `omniagent-api` tool in src/mcp/mod.rs (same
  family as builtin_wait-task; kanban plugin is already a pure HTTP client,
  cron is duplicated by the core /schedule API) + ADD the missing
  DELETE /schedule/{id} (dashboard never had a delete — verified git history)
  + a skill md documenting the API surface. Verified builtin registration
  points: src/mcp/mod.rs :387-508 builtin_* tools. Non-goals: no touching
  docker/filesystem/git/ssh/plugin-manager/mattermost (security-sensitive);
  no prompt behavior change; no db-migrations.
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  skills-gap task (serial chain) — last in chain.

## 2026-08-17 (workflow role mode + auto-approve task)

- Added `Todo/WorkflowRoleModeAutoApproveImplementation.md` (NEW): per-role
  `mode: agent|action` in workflows.yml (default agent, mirroring hooks/schedule
  action semantics). Action-mode roles execute the actions.yml tool call via
  the plugin manager (reuse scheduler::resolve_action/handle_action_mode
  pattern) instead of spawning an agent loop; step-thread creation hooks in
  create_kanban_step_thread (db/threads.rs:1115). Action-mode routing (user
  rule): executor fail → blocked, tester fail → review (NOT executor re-run —
  differs from agent-mode D5), reviewer fail → blocked; interruption retries
  use the existing engine_transition guard (same-step re-run until retries+1,
  then blocked). New workflow-level `auto_approve` (default false): reviewer
  ignored, review→done directly, review_on_fail forced false; new
  `review_on_fail` flag (default false): when true failed steps go to review
  instead of blocked. Dashboard workflows page: role Mode select (action
  select replaces template select in action mode), auto_approve + review_on_fail
  checkboxes (review_on_fail disabled/unchecked under auto_approve). Verified:
  NO existing mode/auto_approve/review_on_fail anywhere (grep zero); workflows
  CRUD via /workflows PUT (server/kanban.rs:111-114); actions.yml is the action
  select source; agent-mode routing + retry guard stay untouched when flags
  are false. No db-migrations.
- Kanban task queued (todo) on the omniagent-dev workflow, depends on the
  plugin-consolidation task (serial chain) — last in chain.
- **2026-08-17 (fail-thread routing fix task)**
  - Added `Todo/FailThreadRoutingReviewOnFailImplementation.md` (NEW): fix the
    double normalization in fail_thread.rs (engine_transition re-normalizes the
    already-normalized fail-thread step: "" → "executor" → "invalid" → blocked;
    F0 must re-run the executor); wire `review_on_fail=true` into the fail
    matrix — tester F0 → review (reviewer decides), only the reviewer can send
    blocked (explicit fail or reviewer retry limit, plus skip), non-reviewer
    blocked/invalid/retry-limit → review; tester adds unit + integration tests
    for (1) go-to-executor and (2) tester-fail-without-target, each with the
    flag true and false.
  - Observed live (task_18cc95fc8fbba9e0 thread #112): tester called
    fail-thread with NO workflow_step → task BLOCKED ("invalid workflow_step
    for status testing") instead of executor re-run; reviewer thread #110 with
    explicit workflow_step="running" correctly created re-run thread #111.
  - Kanban task queued (todo) on the omniagent-dev workflow, depends on the
    workflow-mode task (task_18cc95fc8fbba9e0), before the deploy.py dev task
    — deploy task re-chained to depend on this new task.

2026-08-17 (2): Applied max_tokens_on_truncation 16384 -> 32768 live in omnistable via PUT /settings (API shape: {"updates":[{"name":"...","value":"..."}]}, writes {data_dir}/config/settings.yml + hot-reloads global config). First PUT got wiped by reviewer thread 117 spawn (executor config-restore `git checkout HEAD -- config/...` — known channel-wipe pattern applies to settings too). Durable fix: committed to omni-stack HEAD (6203a5e) so config-restores restore 32768, not 16384. Verified: git HEAD, disk, live API all 32768. Note: API write_settings_file reorders sections (kanban_dispatcher_interval moved to unsorted) — cosmetic, loader flattens sections; restored original layout before commit.

2026-08-17 (3): Analysis: 29 of 117 threads (~25%) since Aug 15 hit max_tokens=4096 cap (finish_reason=length) and needed the 16k escalation; 2 (threads 108, 115) exhausted even 16k and hit FailFast "giving up truthfully" — both marked completed (the FailFast bug). Decision: raise base max_tokens to 8192 via PUT /settings (live 8192 + committed cf2ebbd so config-restores keep it). max_tokens_on_truncation already 32768. New expectation: 8k base absorbs most truncations on first attempt; escalation budget only for rare large outputs.

2026-08-17 (4): DeepSeek provider max_tokens question — Hermes config has NO max_tokens (agent.max_tokens=None → provider default; only bedrock path falls back to 4096). Provider opencode-go deepseek-v4-flash per models.dev cache: context 1,048,576 / output 128,000 tokens. Decision: raise omniagent max_tokens 8192→16384 and max_tokens_on_truncation 32768→65536 (well within 128k output cap). Applied live via PUT /settings + committed 6c9b958 (wipe-safe in HEAD). NOTE: kanban task_18ccb0a9ec956199 Subtask 3 still says 8k/32k defaults — update to 16k/64k when implementing.

2026-08-17 (5): User decision — max_tokens & max_tokens_on_truncation should default to NONE (provider default; never cap output arbitrarily). Code currently u32 everywhere (AgentConfig, CompletionRequest, llm_proxy, JSON body always includes max_tokens) → task_18ccb0a9ec956199 Subtask 3 rewritten: add Option<u32> support end-to-end (config.rs, llm/mod.rs body building, llm_proxy.rs, main_loop effective_max_tokens), settings.yml keeps 16k/64k explicit overrides. Also added Subtask 4: remove thread_summary_tokens entirely (summary+planning calls get max_tokens: None; prompt instructs "reasonably brief"; no cap → task can never fail on summary limit). settings.yml line 18 thread_summary_tokens: 2048 to be removed by the task. Applied live values remain 16384/65536 (committed 6c9b958).

2026-08-17 (5b): CORRECTION to task_18ccb0a9ec956199 Subtask 4 — summary/planning calls must NOT hardcode max_tokens: None. They use the SAME cfg.config_snapshot().max_tokens (Option<u32>, MAY be None) as normal messages. thread_summary_tokens is still removed (no separate small cap), but the global max_tokens (16384 live) applies to summaries/planning too. Task body updated.

2026-08-18 (deploy-suite-debugging skill): Post-mortem of the actions-plugin
saga (Aug 15–16, ~11.5h / 860 iterations / 16 iteration-cap resets / 6
compactions) distilled into NEW skill `profiles/omni/skills/deploy-suite-debugging.md`:
(1) "tool not found" = ordering/registration bug first, harness second — the
actions_* tools failed because registration ran BEFORE install-git; no error
points at the real cause (indirect-failure trap). (2) Test incrementally: run
the failing group alone, then neighbors, only then the full deploy (30+ min
per full run); every test must be self-contained — no dependence on a prior
test having run. (3) Reuse prior-execution context: Smartness WS-1..6 durable
working memory (notes.md per thread + context-*.json dumps + read guards +
retry inheritance) is LANDED on omniagent main (f32e760/1c19ca5/cfad535/0443a96,
verified live in the omnistable image: plugins/tools/prompt/src/notes.rs
present) — check prior threads/notes before re-running, never re-derive state
from scratch. Skipped: weakening tests (assertions stay meaningful).

2026-08-18 (omnidev board convention): Created `omnidev` board in
config/boards.yml — the canonical board for ALL new omniagent development
tasks. The dev workflow (omniagent-dev) is defined AT THE BOARD level
(workflow: omniagent-dev, channel: mattermost-wkbugy5x [mm-kanban MM channel
wkbugy5xcff1teeqgnty5ck4io], profile: omni, plan: true); tasks on this board
carry NO workflow_id/channel_id/profile of their own and fall back to the
board (resolution chain: task > board > channel > global). Moved the Kanban
board-validation task from board dev to omnidev: recreated as
task_18cd0853ef74a388 (board: omnidev, workflow_id/channel_id/profile NULL),
chained depends_on task_18cd061e85394a52, archived the old
task_18cd074f62d194f2. API note: PATCH cannot clear workflow_id to NULL
(empty string = keep existing); moving a task to a board-defaulted workflow
requires recreate-via-API + archive-old.

2026-08-18 (channel naming + dashboard workflow display): Two new planned specs. (1) ChannelNamingMmKanban: `$new <name>` drops the name text — handle_new_external (src/commands.rs:256-280) derives `{platform}-{first8}` = mattermost-wkbugy5x for the mm-kanban MM channel; change: pass the name from `$new mm-kanban` verbatim as the channel key, boards.yml omnidev channel -> mm-kanban, rename channels.yml key. (2) DashboardBoardWorkflowDisplay: BoardConfig.workflow exists in the API but the dashboard never shows a board's workflow and the board modal workflow field is free-text; change: workflow select from fetchWorkflows() + workflow display in board selector/choose-buttons. Both mirrored as omnidev board tasks.

2026-08-18 (remove channel cause): User: "channels.yml should not have a cause field; the omniagent API that stores/reads it also shouldn't." Verified inventory: ChannelDef.cause (channels_yaml.rs:100-101 + default_cause :122 + validate :300-304), Channel.cause (types.rs:306 + Default :326), CreateChannelParams.cause (:252), ChannelEntry.cause (server/channels.rs:59/:83), constructions at commands.rs:274 ($new), plugins_setup.rs:582 (setup), settings.rs:968 + threads.rs:2153 tests; channels.yml has 10 cause lines. No behavioral consumer, no dashboard/deploy-test read. Spec: RemoveChannelCauseImplementation; mirrored as omnidev board task.
