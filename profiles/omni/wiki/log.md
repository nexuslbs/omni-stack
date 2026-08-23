# Log
## 2026-08-23 (docs — generic README/AGENTS + omni-root config/ re-track)

- Rewrote README.md + AGENTS.md to be **generic** (identical for the seed omni-stack and custom forks like omni-root): README documents services, COMPOSE_PROFILES, tunnel env vars, S3 backup/restore, config/*.yml files, and the plugin story (bundled plugins in omniagent, install/enable on the fly, remote plugins via config/remote.yml for separation of concerns) with NO seed-vs-fork mention; AGENTS.md has a very brief seed-vs-fork distinction only (omni-stack = no config/ nor plugins/ tracked; custom forks may track them).
- omni-root: re-tracked `config/` (10 files: README, actions, boards, channels, models, plugins, remote, settings, tasks, workflows — customized live config incl. channels.yml pins, settings.yml without default_cli_channel) via `git add -f` (gitignore documents fork commits as the supported path).
- Same README/AGENTS copied to both repos; pushed to main.

## 2026-08-21 (docs task — remaining Todo pages verified against commits)

- External/Agnostic MCP Servers **IMPLEMENTED** (`92c8b40` — Python/NodeJS dep install; 7 reference servers in remote.yml)
- Paperclip Service **IMPLEMENTED** (compose service + omni-plugins tools/paperclip wired)
- Plugin Consolidation **IMPLEMENTED** (`4aed9ef`/`9422f50` — omniagent-api tool, search merge, telegram+hindsight dropped)
- Skills Gap **IMPLEMENTED** (`b29dd2e`/`285bb10`/`571a2a2` — frontmatter fix, view_skill, create_skill layout)
- Python Telegram Platform **WIRED** (remote.yml platforms/telegram; mock-API test suite not yet verified)


## 2026-08-21 (docs task — README/AGENTS/wiki pass across the four omni repos)

Docs-only pass reflecting implemented kanban work: omniagent `e356833` (README+AGENTS),
omni-dashboard `3790aa9` (README), omni-stack `b72d744` (README+AGENTS) + `f446df8` +
`acc8ed8` (Todo pages marked IMPLEMENTED: hooks, workflow, boards, plan-normalization,
default-channels, terminal-invariant, dispatch-gate, core-dispatcher, stop-thread),
omni-deployer `afdc758` (README+AGENTS). This entry additionally marks
DashboardBoardWorkflowDisplay (`16bb503`, task_18cd0a6e10e9c45d) and
MaxTokensTruncation (`a8f4569`, task_18cb78c5045bae48) IMPLEMENTED.

## 2026-08-21 (docs task_18cd5aff66039e6f — wiki Todo statuses aligned with shipped code)

README/AGENTS docs pass across omniagent/omni-dashboard/omni-stack/omni-deployer. Wiki pass: marked IMPLEMENTED the Todo pages for hooks (HooksImplementation), role-based workflows (WorkflowImplementation), kanban boards (KanbanBoardsImplementation), hooks event meta (HooksEventMetaImplementation), and workflow role mode/auto-approve (WorkflowRoleModeAutoApproveImplementation) — all verified against omniagent commits and kanban board done tasks; index.md entries updated to match.

## 2026-08-20 (task 17 fallback-resolution executor COMPLETE — omniagent `8e238d2`)

Task 17 "Resolve fallback fields ONCE at load — universal resolution pattern"
(task_18cd45eecd7f6dab) executor thread 71 COMPLETE, pushed to origin/main.
omniagent HEAD `1bdcde0`: `8e238d2` feat(resolution) — new `src/resolution.rs`
(569 lines, 10 unit tests): `TaskFallbackFields`/`ResolvedTaskDefaults` via
`resolve_task_defaults(data_dir, fields)` (chain task → board → channel → global
settings; fail-loud invalid board mirroring `task_board` semantics),
`effective_channel_name()` data-dir-parameterized shared channel resolver,
`ResolvedChannel` + `ResolvedThreadProviderModel` + settings-snapshot helper;
wired into ALL Phase-1 consumers — fail_thread.rs `manual_review_decision` +
`engine_transition` (THE live bug: board tasks had NULL workflow_id → reviewer
reject landed on `blocked` instead of an executor rework thread), db/threads.rs
`create_kanban_step_thread` (status-change dispatch /redispatch / startup
recovery all funnel there), kanban_dispatch.rs (local resolve_task_channel →
shared effective_channel_name), src/lib.rs; plus `1ee21e4` fmt, `296061c`
untrack smoke-test artifacts, `1bdcde0` sqlx offline-cache regen
(SQLX_OFFLINE=true builds). omni-stack `0720d81` = Reference/Field-Resolution.md
(documentation deliverable). Verified: 10/10 unit tests pass incl. the
board-task regression, fmt clean, SQLX_OFFLINE cargo check passes, clippy no new
warnings; only the pre-existing ssh-plugin env-dependent test fails. **Phase 1 +
shared pattern done; Phases 2-4 (channel fields / provider-model / settings
snapshot) remain; GROUP 47 live smoke (board-task reviewer-reject → rework
thread + kanban_history "Creating thread #N") pending the tester step.** The
2026-08-19 workflow_id mitigation (below) can be retired once this ships in a
release.

## 2026-08-20 (models.yml task COMPLETE — `cb6c092`/`cf311c3`/`21a65bd`/`38175b3`)

Task 16 provider/model overrides via config/models.yml (task_18cd408ead8bcbbd)
fully through the loop, all on origin/main: executor thread 68 — omniagent
`cb6c092` (feat: src/models_yaml.rs 700+ lines, PROVIDER_METADATA overlay,
plugins_yaml models overlay + synthetic plugin-less providers,
refresh_plugin_models reworked to write models.yml — no plugin mutation,
GET/PUT /api/models validate-before-atomic-write, fail-loud on malformed yml)
+ `cf311c3` (fix: plugin flag always serialized + get_plugin models.yml
overlay), omni-stack `0f16ae1` (config/models.yml sample + wiki
Reference/Models-Yml.md) + `aa3ea8f` (memory promotion: isolated-OMNI_DIR
live-smoke pattern), omni-dashboard `21a65bd` (feat: /models page + shared
plugin-import refactor); tester thread 69 PASS — added omni-deployer
`38175b3` GROUP 46 (4 tests; coverage was genuinely missing — `git grep -i
models scripts/tests.py` had zero matches at HEAD); reviewer thread 70
APPROVE.

## 2026-08-19 (compact+prune+budget → prompt-plugin-ONLY COMPLETE — omniagent `e8239a0`)

Task 15 (task_18cd3a6885fdee06) through the full loop, all on origin/main:
executor thread 64 verified already-done state (omniagent `e8239a0`: core
`prune_old_tool_results`/`PruneConfig`/`context_dump` deleted, main_loop.rs
772-773 passes soft/hard token budgets as REQUIRED compact-messages params,
prune + auto-notes moved inside compact-messages, plugin PluginConfig loses
budget fields + handle_condense removed; omni-deployer `0553cbc` GROUP 11
budget params + p8 prune-in-compact + p9 custom-plugin stub; omni-stack
`fde68b7` Reference/Budget-and-Context.md — context management is
plugin-owned); tester thread 65 PASS — found + fixed **2 real bugs** in
0553cbc's tests (omni-deployer `f76d74f`, pushed); reviewer thread 67
APPROVE. Grep gates 0 hits (prune_old_tool_results|PruneConfig in src/);
budget keys remain only as global settings (config.rs:250-253/359-362 reads
prompt_token_budget_hard/soft, defaults soft 100000 / hard 500000; settings.rs
whitelist); LLM-cache ≥95% gate still to be measured live post-deploy.

## 2026-08-19 (dead-code removal COMPLETE — omniagent `614a3dd`)

Task 14 (task_18cd39ea0dcbf109) through the full loop: executor thread 58
`614a3dd` (chore(dead-code): remove get_recent_summaries, condense_messages +
sweep — 6 files, +3/−393 pure deletion, no behavior change); tester thread 60
PASS (existing GROUP 24 + 20.1 + 20.6 coverage passes on a fresh-HEAD binary;
independent greps 0 hits); reviewer thread 61 APPROVE (read every diff).

## 2026-08-19 (mitigation — workflow_id on pending omnistable kanban tasks)

Until the fail-routing fix (task 17) ships in a release, the running omnistable
binary blocks reviewer/tester fails on board-based tasks (workflow_id NULL →
"no executor role in workflow" → blocked; see FailRoutingBoardFallback
spec). Mitigation applied via the API (PATCH /kanban/tasks/{id}
{"workflow_id": "omniagent-dev"}, the field name the RUNNING binary accepts —
the `workflow` key from the repo's yml/API parity rename is not live yet):
- Set on todo tasks 13 (task_18cd39ea0c185171), 14 (task_18cd39ea0dcbf109),
  15 (task_18cd3a6885fdee06), 16 (task_18cd408ead8bcbbd), 17
  (task_18cd45eecd7f6dab) — same value the omnidev board resolves, semantic
  no-op for dispatch, fixes fail routing.
- task_18cd3920aeeea608 (task 12, RUNNING thread 52) REJECTED by the API:
  "workflow_id cannot be changed while the task is active" (workflow
  immutability guard). Stays NULL — if its tester/reviewer fails it will block;
  manual recovery stands (REDISPATCH NOTE + PATCH status → running).
- Done tasks untouched (workflow_id NULL, verified).

## 2026-08-19 (task 17 broadened — universal fallback-resolution pattern)

User correction: the resolve-fallbacks-first principle is NOT limited to kanban
task fields. ANY field with a fallback chain — kanban task fields being ONE
case, also **channel fields, provider/model fields, settings fields — anywhere
such fallbacks exist** — must be resolved FIRST, early, close to load.
`Todo/FailRoutingBoardFallbackImplementation.md` rewritten: universal pattern
with per-domain resolvers resolved at load (kanban task → board → channel/
global; channel effective name + profile/provider/model; thread provider/model
→ channel → profile → settings → env; settings resolved-at-load snapshot),
phased application (Phase 1 kanban = the live bug, Phase 2 channels, Phase 3
provider/model, Phase 4 settings), one shared resolver per domain (no
per-consumer resolvers), display APIs keep raw fields, regression tests per
domain, Reference/Field-Resolution.md documenting the rule. Task 17 body +
title updated to match (PUT 2026-08-19).

## 2026-08-19 (task 17 generalized — resolve task fallbacks once at load)

User principle (refines the fail-routing board-fallback bug): ANY code that
uses kanban task fields with fallbacks — workflow, channel, profile, plan,
provider, model, similar — MUST resolve them FIRST before shallow use of the
raw fields; the fix applies to ALL such cases; resolve fallbacks as EARLY as
possible (closer to where values are loaded). `Todo/
FailRoutingBoardFallbackImplementation.md` rewritten to the generalized scope:
ONE shared `resolve_task_defaults` (task → board → channel/global settings,
per the documented resolution order) computed right after the task row loads;
ALL consumers switch to resolved values — fail_thread.rs (engine_transition +
manual-review + re-run thread creation), db/threads.rs thread creation,
kanban_dispatch.rs (replace the local resolve_task_channel), status-change
dispatch, /redispatch, startup recovery, kanban_action.rs context,
server/kanban.rs transitions. Display-only API keeps raw fields; behavior uses
resolved. Regression tests per consumer (board-task F1/F2/F3/F0, dispatch/
redispatch, thread-creation plan/profile/provider/model from board; non-board
unchanged). Task 17 body updated to match (PUT 2026-08-19).

## 2026-08-19 (reviewer template + fail-routing board-fallback bug)

Task 12 (budget unification) went BLOCKED not because the reviewer misbehaved
but because of an ENGINE BUG: reviewer thread 51 called builtin_fail-thread
with workflow_step="running" (correct F1 executor-rework request), yet the
task landed on blocked. Root cause: fail routing in src/agent/fail_thread.rs
(engine_transition ~830-847, manual-review ~290-297) resolves the workflow
ONLY from kanban_tasks.workflow_id — board-based tasks (board=omnidev, e.g.
task_18cd3920aeeea608) have workflow_id NULL (the board carries the workflow),
so has_wf=false → route_fail_tool F1 → blocked ("no executor role in workflow
for status review", kanban_history #127). The dispatch path DOES apply the
board fallback — the fail router diverges.

Actions:
1. **dev-reviewer template improved** (profiles/omni/templates/dev-reviewer.md):
   explicit failure-routing hierarchy — fixable issues → ALWAYS
   workflow_step "running" (executor rework); re-verification → "testing";
   "blocked" LAST RESORT ONLY (retry limit / mis-scoped / unfixable); plus a
   VERIFY-the-transition step (known gap: board tasks may land on blocked —
   report it if so). Rejection with findings = rework request, never a block.
2. **New Todo spec + task 17** (FailRoutingBoardFallbackImplementation.md):
   shared workflow resolution helper (task → board → workflow) used by
   dispatch + fail routing; regression tests for board-task F1/F2/F3/F0;
   live verification. At the end of the chain after models.yml (16).
   Until the fix ships, board-task fails block — recover via REDISPATCH NOTE
   + PATCH status → running (done manually for task 12 → thread 52 running).

## 2026-08-19 (exact budget fallback chain — user-specified)

User pinned the token budget fallback (folded into tasks 12/15/16):
- **Soft budget**: model_config soft (models.yml model_config.<model>) →
  provider soft (models.yml providers.<name>) → global settings
  `prompt_token_budget_soft` (settings.yml).
- **Hard budget**: same chain with hard values.
- **Defaults**: settings.yml must define soft = **100000**, hard = **500000**
  as the fallback defaults (task 12 renamed the keys and must set these
  values; earlier "e.g. 200000/100000" defaults superseded).
- max_tokens / max_tokens_on_truncation follow the same chain (model >
  provider > settings).
- Resolved by omniagent per thread and passed as compact-messages
  `soft_budget`/`hard_budget` params (tasks 12/15); prompt plugin agnostic.
- Task 16 spec req 3 now documents the exact 3-step chain; task 15 spec notes
  the chain is owned by the models.yml task; task 12 body defaults updated.

## 2026-08-19 (budget architecture v2 — global settings + compact-messages params)

User decision v2 (supersedes the "budgets in prompt plugin only" part of
task 15): hard/soft budgets are **GLOBAL SETTINGS in omniagent**
(`prompt_token_budget_hard/soft`, AgentConfig `token_budget_hard/soft` from
task 12) and the **compact-messages tool receives them as PARAMS**
(`soft_budget`/`hard_budget`). The prompt plugin has NO budget config and
stays AGNOSTIC of models.yml — omniagent resolves the effective per-thread
budgets (model > provider > settings, the models.yml task feeds this) and
passes them in. Updates applied:
- Task 12 body: core fields RENAMED to token_budget_* (global settings — the
  earlier defer-to-task-15 scope update superseded); plugin token budgets stay
  INTERIM until task 15's params interface; char budgets removed everywhere.
- Task 15 spec + body: architecture rule v2 (global budgets + params; core
  KEEPS the budget fields, removes only the pruning USE); compact-messages
  REQUIRES soft/hard budget params; gates updated (no prune in core; budget
  keys present as global settings).
- Task 16 spec + body: budget precedence flow — omniagent resolves model >
  provider > settings and passes as compact-messages params; prompt plugin
  agnostic of models.yml.

## 2026-08-19 (models.yml task refined — Import on /models page)

User refinement folded into `Todo/ModelOverridesConfigImplementation.md`
(task 16, task_18cd408ead8bcbbd) requirement 10 + Import gate:
- /models page gains an **Import** button mirroring the plugins pages import
  (src/lib/plugin-import.ts showImportModal): paste a URL to a models.yml-LIKE
  file (any filename), fetch (direct + /api/fetch-remote fallback), parse
  `providers`, compare against local models.yml (GET /api/models) →
  per-provider actions: `add` (not present), `override` (present, different
  config — "will overwrite"), `same` (identical config — "already exists",
  removable from the import set); marked actions pending; Confirm & Execute
  applies via the omniagent API ONLY (PUT /api/models merge — never replaces
  the whole file; import never deletes local entries).
- **Reuse/extract the shared code from plugin-import.ts** (one generalized
  fetch/parse/compare/mark/execute implementation for both imports) — the only
  differences: models.yml-like schema (provider definitions, not
  url/path/ref) and target config/models.yml via the models API. Refactor must
  be behavior-preserving for plugin import (regression gate).
- Import gate added: add/override/same rendering, merge-only execution,
  second same-URL import shows all same, plugin import regression check.

## 2026-08-19 (models.yml task refined — refresh upsert + /channels-style page)

User refinements folded into `Todo/ModelOverridesConfigImplementation.md`
(task 16, task_18cd408ead8bcbbd):
1. **Refresh button → models.yml upsert (universal contract)**: every model
   field with a refresh button (providers page, channel model selector,
   /models page) refreshes via the omniagent API and writes models.yml —
   NEVER the plugin (plugin mutation is fragile, lost on plugin version
   updates, esp. remote). refresh_url defined → fetch remote models (reuse
   fetch_enum_values src/plugins_yaml.rs:1782) → UPSERT: entry absent → add
   `plugin: true` + `models: [fetched]` (everything else from the plugin);
   entry present → update ONLY `models`, other fields untouched. Current
   refresh_plugin_models (src/plugins_yaml.rs:1746) mutates in-memory
   config_schema + DYNAMIC_ENUM_CACHE — rework to write models.yml. A provider
   gains new models without a new/changed plugin.
2. **/models page modeled on /channels page** (appearance + functionality:
   list rows, inline add/edit/delete, save), using the models API (GET/PUT
   /api/models) instead of the channels API, updating models.yml instead of
   channels.yml.
3. New refresh-flow gate: models.yml upsert on refresh, ONLY-models update on
   existing entry (byte-identical others), plugin manifest/config_schema
   unchanged, works for plugin-less providers, API-only writes.

## 2026-08-19 (provider/model overrides spec — config/models.yml)

`Todo/ModelOverridesConfigImplementation.md` — task 16 (end of chain, after
compact+prune task 15). User feature: overridable provider definitions +
per-model settings via a pure definition file `config/models.yml` in OMNI_DIR
(NO new plugin, NO custom code). Top-level `providers`, each child = provider
name with `plugin:` flag (use provider plugin vs builtin chat_completions /
anthropic formats), `models` array replacing `default_model.allowed_values` in
dashboard selectors (deepseek example: plugin.json allowed_values
["deepseek-v4-flash","deepseek-v3","deepseek-r1"] is wrong — models.yml
`models: ["deepseek-v4-flash","deepseek-v4-pro"]` fixes the selector without a
new plugin). Provider-level fields (api_mode, default_base_url, refresh_url,
default_model, api_key with $env:/$secret: expansion — resolver already exists
src/platform/external/mod.rs:291, supports_reasoning) OVERRIDE the provider
plugin on name match; plugin-less providers still selectable on threads.
Per-model config: api_mode, supports_reasoning, token_budget_soft/hard,
max_tokens, max_tokens_on_truncation; precedence model > provider >
plugin/core. New dashboard "Models" page (/models) after Providers; API
GET/PUT /api/models. Verified: ProviderMetadata src/llm/mod.rs:57-69,
plugins.yml providers:114-134, refresh-models API src/server/plugins.rs:204,
channel model selector src/lib/channel-config.ts:276-300+.

## 2026-08-19 (cache reqs refined — agent-side windowing, no black-magic truncation)

User refinement folded into `Todo/CompactPrunePluginOwnershipImplementation.md`
(task 15) requirement 3: silent SOURCE truncation of tool results is rejected —
the full content MAY be needed and hidden truncation makes the agent
misunderstand what it read. Replaced with:
1. **Agent-side windowing (preferred)**: skills/templates teach smaller result
   windows + use tool params — `filesystem_read` already has char-based
   offset/limit paging (plugins/tools/filesystem/src/main.rs:173-181, default
   limit 50000); fetch ranges where protocol allows. Cache benefit comes from
   the agent's own explicit smaller reads, never silent truncation.
2. **Safe grep/rg content-search tool** (user-suggested): filesystem_search
   matches NAMES only — add file-content search so the agent finds relevant
   lines instead of whole-file reads. Safety-critical: fixed rg binary /
   in-process matcher, path-restricted to allowed roots, validated args, NO
   shell / NO arbitrary code. Safety gate added.
3. **Drain-time compaction stays** as the safety valve (over hard budget):
   meaning-preserving excerpts (what was read + why) fold INTO the frozen
   summary; surviving tail byte-identical.
4. New requirement 7: skills/templates guidance is the PRIMARY lever; guidance
   gate added (no silently-truncated results).

## 2026-08-19 (cache requirements corrected — user review)

User corrections folded into `Todo/CompactPrunePluginOwnershipImplementation.md`
cache section (task 15):
1. **In-place excerpting of existing messages would INCREASE cache misses**
   (rewriting an old message shifts every byte after it → whole tail cache
   miss). Rewrote req 1 + 3: truncation is cache-safe ONLY (a) at SOURCE (tool
   result capped at creation, before entering context — never touches
   existing messages) and (b) at DRAIN time (drained content folds INTO the
   frozen summary block; never written back to its old position). Surviving
   tail = byte-identical, full, in order. "Keep last N full" = surviving tail;
   "excerpt older" = drained content into the summary.
2. **Threshold-gated cadence clarified**: compact-messages is CALLED every
   iteration but COMPACTS only when over the hard budget (null-contract no-op
   otherwise; no-op path must be byte-identical). The 08-14 "compaction every
   iteration" observation was a misconfiguration symptom (thread 5x over the
   100K char hard budget), not the design.

## 2026-08-19 (cache requirements added to compact+prune task)

`Todo/CompactPrunePluginOwnershipImplementation.md` extended with the user's
LLM-cache directive: context management shapes the prompt prefix (DeepSeek
cache key) — the compact+prune refactor must IMPROVE cache, expected ≥95% hit.
Reference: Hermes 08-02 98.4% (311M hit/5M miss); omniagent 08-18 95.8%
(252M/11M); live omnistable baseline 94.4% (7d) — below target. Baked in:
stable-prefix invariant (no modify/reword/reorder of pre-tail messages),
frozen byte-identical summary block (absorbs the unclaimed
CacheFriendlyCompactionImplementation.md spec — that task never got a kanban
task; its "don't touch core prune" non-goal is superseded), deterministic
in-place truncation, per-iteration miss-token minimization (cap top tool-result
producers after measuring msg_subtype token sums), no mid-context changing
upserts, cache-compatible custom-plugin test. Cache gates: ≥95% measured from
threads table + cached_tokens-grows-with-prompt live check + byte-identical
prefix unit tests + quality guard (no dumber behavior).

## 2026-08-19 (compact+prune+budget → plugin-only spec)

`Todo/CompactPrunePluginOwnershipImplementation.md` — user architecture
decision: context management belongs to the prompt plugin. Core must have NO
budgets and NO tool pruning (`prune_old_tool_results`, main_loop.rs:843 Layer
3) — the dual mechanism is code smell and blocks custom prompt plugins from
owning context management. Budgets live only in the prompt plugin (token
budgets, chars/4 fallback, per task 12); prune moves INTO compact-messages
(ChatMessage carries tool_call_id/name → tool results identifiable; interface
change allowed, e.g. thread_dir for auto-notes). Custom-plugin test required.
Task 15, at the very end of the chain after dead-code removal. Task 12 body
updated to defer core budget changes to this task (no core rename to token).

## 2026-08-19 (Wiki source + skill spec, dead-code removal spec)

Two new Todo specs appended to the chain (after budget unification
task_18cd3920aeeea608; board omnidev):

- `Todo/WikiSourceSkillImplementation.md` — user finding from the 7-day usage
  report: no wiki tool called. Verified: NO dedicated wiki plugin exists —
  wiki is a data source (profile wiki dir + `search_wiki` tool from the search
  plugin, in allowed_tools, but 0 real calls in 7 days) + optional Qdrant
  vectorizer (vectorize_wiki=false). Direction: wiki skill (Karpathy method +
  Obsidian format + filesystem-tool examples) instead of a new plugin.
- `Todo/DeadCodeRemovalImplementation.md` — remove `get_recent_summaries()`
  (src/db/summaries.rs:36, `#[allow(dead_code)]`, uncalled),
  `condense_messages()` (src/agent/helpers.rs:594, test-only legacy condenser
  — live loop uses compact tool + prune_old_tool_results), stale
  `old_message_char_budget` refs (after task 12), plus a general dead-code
  sweep. Deletion-only, no behavior change.

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

2026-08-18 (channel-naming design correction): User corrected the $new
design: "$new accepts an OPTIONAL first argument. When defined, it creates a
channel with THAT name (or updates the existing channel with that name)."
The earlier ChannelNamingMmKanban spec (pass name verbatim, keep
{platform}-{first8} fallback) was wrong — upsert-by-name semantics, NOT a
fresh create. Updated ChannelNamingMmKanbanImplementation.md accordingly;
archived the old task_18cd0a6c7ef43217 (wrong design), re-chained dashboard
task to board-validation, created task_18cd0ab3aef76f8b ($new [name]:
optional first arg creates/updates channel by that name) chained after
RemoveChannelCause (last task).


## 2026-08-18 (wiki-maintenance hook run #1 — threads 1-11)

First trigger of the profile-scoped wiki/templates/skills maintenance hook
(thread_finished, count 10, agentic; event: last_thread=null, current_thread=11).
Window threads 1-11 (all profile omni):

- **Hooks wiki/summaries task COMPLETED** (threads 2 executor, 3 tester PASS,
  4 reviewer APPROVE) — omniagent `56b486b` `feat(hooks): per-scope-key counter
  meta + replace auto-summary with save-summary tool`; omni-stack side:
  tasks.yml defines the 2 agentic thread_finished hooks (count 10, scope
  profile/channel) + skills wiki-maintenance.md + channel-summary.md. Todo
  `HooksWikiSummariesImplementation.md` marked IMPLEMENTED.
- **Kanban board validation task COMPLETED** (threads 5 executor, 7 tester PASS,
  9 reviewer APPROVE, 10 tester caveat, 11 smoke PASS) — omniagent `9a7f8c0`
  `feat(kanban): require board on task create/update when boards.yml present`.
  Live smoke (thread 11) against the new binary via the ISOLATED omnidev-toolbox
  stack: POST without board → 400, unknown board → 400, PATCH board "" → 400,
  valid board → ok + auto-dispatched via in-process dispatcher; artifacts
  cleaned + verified. Caveat confirmed: the deployed stack still runs the
  PRE-CHANGE binary until restarted. Todo
  `KanbanBoardValidationImplementation.md` marked IMPLEMENTED.
- Thread 6 failed: LLM provider rate-limited (HTTP 429, retry after 416342s) →
  thread marked failed — operational noise, no spec impact.
- NEW skill `profiles/omni/skills/live-smoke-toolbox.md`: repeatable procedure
  for live-smoke-testing a new omniagent build (fresh pgvector DB + release
  binary from current HEAD) without touching the deployed stack.
- Thread 1 was a trivial math test (no durable facts). This maintenance run
  updated: Todo/KanbanBoardValidationImplementation.md (implemented),
  Todo/HooksWikiSummariesImplementation.md (implemented), index.md (new skill +
  done markers), log.md (this entry); created skill live-smoke-toolbox.md.
  No template changes (nothing REALLY valuable enough for prompt-space cost).

2026-08-18 (dispatcher archived + provider relative path): Two new planned specs. (1) DispatcherArchivedFilter: dispatch_todo_tasks scan (kanban_dispatch.rs:137-143) has no `archived` filter — archived task_18cd0a6c7ef43217 was promoted and ran despite archived=t (stopped via stop-thread + status:blocked); fix = AND archived=false + regression test. (2) ProviderRelativeEntrypoint: platform loader resolves relative entrypoint args against plugin dir (external/mod.rs:158-180) but provider loader does not (plugins_env.rs:119-181 only string-prefix replaces remote args; provider spawn has no current_dir); noop-full plugin.json hardcodes /opt/omni/plugins/providers/noop-full/client.py → breaks with non-default OMNI_DIR; fix = mirror platform resolution for providers + current_dir + change plugin.json arg to client.py. Both mirrored as omnidev board tasks.

2026-08-18 (plugin omni_dir config): User: fix /opt/omni in tools/memory + tools/actions server.py (and other plugins if needed) — the plugin may define an omni_dir config field defaulting to $env:OMNI_DIR and use that config. Verified: memory/actions get_omni_dir() = os.environ.get("OMNI_DIR", "/opt/omni") (server.py:90/:69) ignoring the existing config_schema omni_dir field; prompt server.py:571 uses ~/.omniagent fallback and has NO config_schema; framework injects config_schema defaults as env (apply_config_schema_defaults mcp/external/config.rs:579-631, $env: resolved by resolve_config_value) and python cfg_env() reads them. Spec: PluginOmniDirConfigImplementation; mirrored as omnidev board task.

2026-08-18 (sub-prompts append): User spec: when a channel has a running user thread (cause=user) and pending user threads (cause=user) with same channel/profile/parent_id (or pending.parent_id == running id), the next LLM call appends the pending prompt into the FULL prompt before compaction; pending marked skipped; messages gains original_thread_id (pointing to the skipped pending thread); sub_cause message type with msg_subtype = original thread id; cumulative char setting (sub_prompt_max_chars) stored/incremented across loop iterations, stops at limit with loop flag; iteration-percent setting (sub_prompt_iteration_percent, default 50%, 0 disables, 100 = check every call). Verified anchors: main_loop.rs:623 loop, condense at :645 (append BEFORE it), types.rs:380/341, messages DDL lib.rs:486, settings.rs sections/whitelist :193/:736, threads.rs:773 pending lookup + :287 skipped choke point. Spec: SubPromptsAppendImplementation; mirrored as omnidev board task.


## 2026-08-19 (wiki-maintenance hook run #2 — threads 23-34)

Second trigger of the profile-scoped wiki/templates/skills maintenance hook
(thread_finished, count 10, agentic; event: last_thread=23, current_thread=34).
Window threads 23-34 (all profile omni; thread 25 = hook-caused, skipped):

- **`$new [name]` optional first arg COMPLETED** (threads 23 executor, 24
  tester PASS, 26 reviewer APPROVE; task_18cd0ab3aef76f8b) — omniagent
  `b9058c8` `feat(commands): support optional channel name in /new and $new
  commands` (parse_new_command optional first arg; NewCommand{name:
  Option<String>}; handle_new_external name verbatim upsert, `{platform}-
  {first8}` fallback for bare `$new`; unit tests) + omni-stack `8f5b8f5`
  (boards.yml omnidev channel + channels.yml key renamed to `mm-kanban`).
  LIVE evidence: threads ≥27 have channel_id `mm-kanban` in the DB.
  Todo `ChannelNamingMmKanbanImplementation.md` marked IMPLEMENTED.
- **Dispatcher archived filter COMPLETED** (threads 27 executor, 28 tester
  PASS, 29 reviewer APPROVE; task_18cd0bea01181c88) — omniagent `070e8f4`
  `fix(kanban): never dispatch archived tasks` — scan SQL `archived = false`
  + Rust backstop `scan_row_eligible` (NULL = not archived) + regression
  test; `create_kanban_step_thread` returns Ok(None) for archived (backstops
  status-change dispatch, /redispatch, startup, auto-dispatch). Todo
  `DispatcherArchivedFilterImplementation.md` marked IMPLEMENTED.
- **Provider relative entrypoint COMPLETED** (threads 30 executor, 31 tester
  PASS, 32 reviewer APPROVE; task_18cd0beb88b366d1) — omniagent `d9f323d`
  `fix(providers): resolve relative entrypoint args against plugin dir + set
  subprocess cwd` (resolve_provider_args mirrors platform loader; provider
  spawn current_dir) + omni-plugins `1659583` (noop-full plugin.json arg →
  `client.py`). Tester ran the live gate (non-default OMNI_DIR + noop-full +
  chat completion). Todo `ProviderRelativeEntrypointImplementation.md`
  marked IMPLEMENTED.
- **Plugin omni_dir config IMPLEMENTED + TESTED** (threads 33 executor, 34
  tester PASS; task_18cd0c7a02d3884f — reviewer thread 35+ OUTSIDE window) —
  omni-plugins `19bb5bc` `fix(plugins): resolve data dir via omni_dir config
  field` (memory/actions/prompt server.py config-first +
  `_fail_omni_dir()` RuntimeError; prompt plugin.json gains omni_dir
  config_schema) + omni-deployer `dedc5e3` NEW GROUP 42 (3 tests, 3/3 PASS
  hermetic in omnidev-toolbox — omnidev stack down, Hermes owns lifecycle).
  Todo `PluginOmniDirConfigImplementation.md` marked IMPLEMENTED (reviewer
  pending in next window).
- Notes: git push in thread 34 used the JWT workaround (broken GitHub App
  key); GROUP 37/38 still need the live stack.
- This maintenance run updated: 4 Todo specs (implemented), index.md
  (implemented markers), log.md (this entry). No template changes (nothing
  REALLY valuable enough for the prompt-space cost).

## 2026-08-19 (wiki-maintenance hook run #2 — threads 34-46)

Second trigger of the profile-scoped wiki/templates/skills maintenance hook
(event: last_thread=34, current_thread=46; all profile omni). Window
threads 34-46 covered 4 completed omnidev workflow tasks (reviewer APPROVE
on all); hook-caused threads 36/38 skipped:

- **Sub-Prompts Append COMPLETED** (threads 37 executor, 39 tester PASS,
  40 reviewer APPROVE) — omniagent `5d17bd3` `feat(sub-prompts): append
  pending user prompts to running thread (parent_id, before condense)`;
  omni-stack `7268d2e` (settings.yml `sub_prompt_max_chars: 4000`,
  `sub_prompt_iteration_percent: 50`); omni-deployer `20a3778` (GROUP 43
  4/4 PASS, fix commits `aa7f577` FK-parent + `9107d40` rollback cleanup).
  `messages.original_thread_id` column; injection BEFORE the condense call;
  Todo/SubPromptsAppendImplementation.md marked IMPLEMENTED with summary.
- **Builtin omniagent-api + fetch allow_unsafe_methods COMPLETED**
  (threads 41 executor, 42 tester PASS, 43 reviewer APPROVE) — omniagent
  `0ecb985`: `omniagent_api_tool` (src/mcp/mod.rs :819/:873) gains 30s
  timeout + non-2xx tool errors; fetch plugin `allow_unsafe_methods` config
  (default false); Dockerfile ships api-reference.md → `/opt/omni/docs/
  api.md`; omni-deployer `a287ffe` GROUP 44 3/3 PASS + fetch unit tests
  5/5 PASS; omni-stack `f85f9bb` skill omniagent-api.md updated. NEW
  Todo/OmniagentApiBuiltinImplementation.md.
- **yml/API Field Naming Parity COMPLETED** (threads 44 executor, 45
  tester PASS, 46 reviewer APPROVE) — API JSON field names unified to yml
  property names: `channel_id`/`channel_name`→`channel`,
  `workflow_id`→`workflow`, `schedule`(cron expr)→`cron`,
  `current_profile/provider/model`→bare (omniagent `9c52028` refactor,
  10 src/server/*.rs files, NO DB migration — 1:1 SQL boundary mapping;
  docs `f147c52`); omni-dashboard `305199d` TS renames + `bc4e622` tsc
  fixes (threads.ts duplicate channel TS2300 + 4 pre-existing type errors);
  omni-deployer `3833c0c` tests.py + `500e1a4` tester fix (3 stale
  schedule→cron spots); omni-stack `f3ebfdf` skill omniagent-api.md kanban
  create uses `channel`. Audit: plan_mode tri-state, /stop/{channel_id}
  path params, schedule_task_id (DB-only), kanban history JSON keys
  KEEP-DOCUMENTED; actions/plugins/remote/settings/boards.yml CONSISTENT.
  NEW Todo/YamlApiFieldParityImplementation.md. SQL/DB references
  (threads.channel_id etc.) remain valid — the rename was API-only.
- Maintenance actions this run: 2 new Todo pages, 1 spec marked
  IMPLEMENTED + summary, index.md updated (2 new entries + sub-prompts
  marker). No template changes (none warranted). omniagent-api skill was
  already updated during the threads (f85f9bb/f3ebfdf) and verified
  current. The omni_dir task (threads 34/35) and plugin consolidation were
  already documented (PluginOmniDirConfigImplementation.md etc.).

## 2026-08-19 (wiki-maintenance hook run #3 — threads 46-58)

Third trigger of the profile-scoped wiki/templates/skills maintenance hook
(event: last_thread=46, current_thread=58; all profile omni). Window threads
46-58 covered: task 12 budget unification (executor 48 → tester 49 → reviewer
51 REJECT → executor rework 52 → tester 53 PASS → reviewer 54 APPROVE), channel
summary hook (50), task 13 wiki data source + wiki skill (executor 55 → tester
56 PASS → reviewer 57 APPROVE), task 14 dead-code removal (executor 58).

Changes:
- NEW `Todo/ContextBudgetUnificationImplementation.md`: task 12 IMPLEMENTED —
  char budgets removed everywhere; budgets are GLOBAL SETTINGS in core
  (`AgentConfig.token_budget_hard/soft` ← `prompt_token_budget_hard/soft`,
  defaults soft 100000 / hard 500000), passed to compact-messages as
  `soft_budget`/`hard_budget` params; chars/4 fallback; commits omniagent
  `bf2af90`, omni-stack `451a461`, omni-deployer `3386e1d`; documents the
  round-1 REJECT lesson (reviewer thread 51 caught the missing core rename
  against SCOPE UPDATE v2 — verify against the CURRENT task body).
- UPDATED `Todo/WikiSourceSkillImplementation.md` → IMPLEMENTED: omni-stack
  `9c86468` (new skill `skills/wiki.md`, Karpathy + Obsidian + filesystem
  worked example; guidance convention #7 "check wiki before asking user") +
  omni-deployer `adb72f3` (GROUP 45 + GROUP 25 pass in omnidev-toolbox).
- UPDATED `Todo/DeadCodeRemovalImplementation.md` → IMPLEMENTED: omniagent
  `614a3dd` (removed `get_recent_summaries`, `condense_messages` + tests,
  `old_message_char_budget` stragglers, general sweep; 393 del / 3 ins,
  deletion-only). Tester/reviewer run lands after this window.
- UPDATED `Reference/Budget-and-Context.md`: compaction section now reflects
  TOKEN budgets (hard 500000 / soft 100000, chars/4 fallback, global settings
  + compact-messages params, model > provider > settings chain) — the old
  page still described char-era defaults (hard 100000 / soft 50000).
- UPDATED `index.md`: new wiki skill entry under Skills; Todo list gains
  ContextBudgetUnification (IMPLEMENTED) and IMPLEMENTED markers on
  WikiSourceSkill + DeadCodeRemoval.

Not changed: no templates touched (nothing in the window justified a template
edit beyond the dev-reviewer template already improved in run #2's window);
no skills created/deleted (wiki.md from thread 55 already ships; omniagent-api
skill was updated by the earlier parity task).

## 2026-08-20 (wiki-maintenance hook run #4 — threads 1732-1744)

Fourth trigger of the profile-scoped wiki/templates/skills maintenance hook
(event: last_thread=1732, current_thread=1744; all profile omni). Window
threads 1732-1744: threads 1732/1733/1735/1736/1738/1739/1740/1741 are
failed/skipped system-caused threads with NO agent activity (no durable facts);
1734 (hooks) and 1737 (hooks, channel-summary run) are hook-caused, skipped.
Substantive work: one omnidev workflow task `task_18cd65247cfc4d9e`
(omni-dashboard 8-item UI/UX fixes, threads 1742 executor / 1743 tester /
1744 reviewer):

- **omni-dashboard 8-item UI/UX pass VERIFIED + regression-tested** — the
  implementation had already landed on omni-dashboard origin/main from prior
  threads: `fb9c680` (DB page 502 → server/routes/db.ts calls `search_database
  {sql}`, was `query_database {operation, sql}`), `d56d046` (workflow option
  text/order/defaults — review_on_fail first, defaults on create),
  `b0e2bc6` (board modal fields → custom selects channel/profile/workflow/
  plan/template/priority with empty options), `73fdf62` (hook trigger count
  `type="tel"` + template custom select resolves from profile),
  `8e85376` (template selects alphabetical all-profiles, red OPAQUE cancel
  `var(--bg-card,#1e1e2e)`, plugin Remove always, explorer git box to bottom),
  `295a669` (umbrella 8-item pass — accidentally included scratch push
  scripts), `731f909` + `877a9e7` (hygiene: gitignore + remove leftover
  .task-push.sh / .tmp_patch_*.py). Custom-select helper:
  `enhanceSelect`/`enhanceSelectElement` in `src/lib/dropdown.ts`, consumed by
  `src/pages/kanban.ts` (`wireBoardControls`), `src/lib/kanban-boards.ts`,
  `src/lib/hooks-detail.ts`.
- Executor 1742 verified the work was already pushed (clean tree), re-ran
  `npm ci && npm run build && npm run lint` + tests in a node:22-alpine
  toolbox (`/opt/workspace/.dash-build-compose.yml`, project `dash-build`);
  only pre-existing `OmniDashboard API` subtest fails without a live server
  (not a regression). Tester 1743 added omni-deployer GROUP 49 — a STATIC
  source-check regression (`7e49bb8` `test(dashboard): GROUP 49 — omni-dashboard
  UI/UX fixes regression tests`, reads TSX from disk, asserts select wiring /
  option ordering / modal opacity) — and ran it PASS.
- Reviewer 1744 verified origin/main @ `877a9e7`, clean trees in BOTH repos,
  recorded GOOD findings for the DB 502 + workflows items, then ended the
  thread FAILED with `workflow_step: running` — task flipped review → running
  for executor rework (outcome threads ≥ 1745 are OUTSIDE this window, not
  tracked here). Hygiene lesson: dashboards tasks keep committing scratch push
  scripts — reviewers should grep `ghp_|x-access-token|PRIVATE KEY|sk-...`
  before approving.
- Maintenance actions this run: NEW Todo/DashboardUiUxFixesImplementation.md
  (8 items, commit table, GROUP 49, workflow history, hygiene lesson);
  index.md updated (new Todo entry); log.md (this entry). No template changes
  (nothing REALLY valuable enough for the prompt-space cost); no skills
  created/deleted.

## 2026-08-21 (wiki-maintenance hook run #5 — threads 1744-1756)

Fifth trigger of the profile-scoped wiki/templates/skills maintenance hook
(event: last_thread=1744, current_thread=1756; all profile omni). Window
threads 1744-1756: hook threads 1747 (prev maintenance run 1732-1744) and
1749 (channel-summary) skipped; 1745 FAILED (bookend of the dashboard reject
cycle). Two substantive workflow tasks completed end-to-end:

1. **omni-dashboard 8-item UI/UX fixes (task_18cd65247cfc4d9e) — APPROVED** —
   the rework cycle that run #4 left open completed: reviewer 1744 REJECTED
   (blocking gap: Item 2 first bullet — the Kanban page board selector
   `#kanban-board-select` in `src/lib/kanban-boards.ts` was STILL a native
   `<select>` with no `enhanceSelectElement` call, only the board modal
   selects were enhanced) → executor 1746 rework commit `1bf1405`
   (`fix(kanban): board selector custom select`) → executor 1748 verified no
   re-implementation needed → testers 1750 + 1751 re-ran GROUP 49 live
   against omnidev: **9 pass / 0 fail** → reviewers 1752 + 1753 **APPROVE**
   (git grep verified `enhanceSelect` wiring in kanban.ts/kanban-boards.ts/
   dropdown.ts and hook select markup in hooks-detail.ts at HEAD).
   `Todo/DashboardUiUxFixesImplementation.md` updated: status
   IMPLEMENTED + TESTED + APPROVED, commit table gains `1bf1405`, workflow
   history extended to the full lifecycle.
2. **Resolve fields with fallback AT DATA-LOAD TIME (task_18cd7ecb9817b677) —
   Phase 2 of the Field-Resolution rule, APPROVED** — omniagent `57e16da`
   (3 files, +221/−15) "loaders return resolved data, never shallow values":
   - `src/resolution.rs` (+152): `ResolvedChannelIdentity` +
     `resolve_channel_identity(data_dir, def)` — canonical channel-tier
     resolver: profile (yml → `default_profile_name()`), provider (yml →
     resolved profile's provider → global `default_provider`), model (yml →
     profile model ONLY when the channel doesn't pin a provider →
     `resolve_default_model(provider)`); mirrors `resolve_thread_identity`'s
     channel tier; 3 new unit tests incl. regression guard `83f461b`
     (wf-test → noop/test-tool-caller).
   - `src/db/channels.rs` (+15): `def_to_channel` resolves profile/provider/
     model on EVERY load (channels.yml re-read fresh per call, NO boot-time
     cache) — a provider edit takes effect next load/thread, no restart;
     fixes the root-cause bug (mm-kanban → opencode-go edit ignored, threads
     kept `deepseek`).
   - `src/server/kanban.rs` (+69): `task_row_to_entry(data_dir, r)` runs
     `resolve_task_defaults` after fetch — kanban API list/get return
     RESOLVED values, never shallow board-based rows; invalid board → warn +
     raw row (display only).
   - Tester 1755: fmt fix `45bc5c2` (pre-existing rustfmt violation in
     `plugins/tools/prompt/src/compact.rs:674`, file NOT touched by 57e16da);
     ALL_GATES_DONE (check/fmt/clippy/test exit 0; 541-test + 44-test bins);
     **GROUP 47 live G47_EXIT=0** (7 fns 47-A..G: rework, retest, block,
     status-change dispatch, redispatch, explicit-fields-win,
     unknown-board-fail-loud); rebuilt missing dev bins (mcp-server-prompt,
     mattermost-platform); omni-deployer clean @ `7e49bb8`. Reviewer 1756
     APPROVE; repo hygiene PASS (no scratch/secrets at HEAD).
   - NEW `Todo/FieldResolutionDataLoadTimeImplementation.md`; `Reference/
     Field-Resolution.md` updated (kanban API now returns resolved values —
     display-API note revised; resolve_channel_identity + def_to_channel
     load-time section; task_row_to_entry consumer; implementation status
     block).

Also fixed a catalog gap: `Reference/Field-Resolution.md` was missing from
index.md's Reference list — added. No templates touched (nothing in the
window justified a prompt-space cost); no skills created/deleted (no new
reusable procedure beyond the documented resolvers; git push again used the
JWT workaround where needed per known issue).

## 2026-08-21 (docs task pass 2 — remaining implemented Todo pages marked IMPLEMENTED)

Docs task (task_18cd5aff66039e6f) continued: marked PlanNormalization,
DefaultChannels, SkippedTerminal, DispatchChannelGate, CleanupAndCoreDispatcher,
StopThreadSurgical Todo pages IMPLEMENTED with their implementing omniagent
commits (0c772e9, 8e13237, 44799c4, 4086d06, 26e2ae1, d096e30); index.md synced.

## 2026-08-21 (docs task — RemoveChannelCause marked IMPLEMENTED)

`RemoveChannelCauseImplementation.md` marked **IMPLEMENTED 2026-08-19** (omniagent `4640777`,
kanban task_18cd0a9e3b7a7e1a DONE): `cause` removed from the channel model (channels.yml + API).

## 2026-08-21 (docs task: wiki Todo statuses round 4)

Marked IMPLEMENTED with verified omniagent commits: Plugin Restart Endpoint
(`0245407`, 2026-08-13), Fail-Thread Routing review_on_fail (`4f8b1f9`,
2026-08-17), Cache-Friendly Compaction (`e8239a0`+`f29e9a4`, folded into
compact+prune), Actions Plugin → omni-plugins Python (`89c08f3`/`1285b50`,
2026-08-17; deploy-env registration under verification), SSH Plugin
(`bccfd2a`), Subtasks Improvement (`14e832f`+`d601dd5`). index.md catalog
synced.


## 2026-08-22 (wiki-maintenance hook run #6 — threads 34-46)

Sixth trigger of the profile-scoped wiki/templates/skills maintenance hook
(event: last_thread=34, current_thread=46; all profile omni). Window threads
34-46 were an **automated smoke-test burst** of the `noop` test provider
(model `test-tool-caller`) — 13 threads created within ~31 seconds, each a
single trivial tool call:

- Thread 34: `prompt_compact-messages` (1 msg, soft 50k / hard 100k) →
  `messages: null, was_compacted: false` — re-verified the null-contract
  (compaction only fires over the hard budget; matches
  Reference/Budget-and-Context.md).
- Threads 37/40/43/46: `search_messages` / `search_wiki` /
  `subtasks_list-subtasks` / `actions_relevance-indexer` → **"Unknown tool:
  X"** (tool NOT registered in that thread's toolset).
- Threads 38/39, 41/42, 44/45: the SAME tools (`search_messages`,
  `search_wiki`, `subtasks_list-subtasks`) → real results (tool registered).
- Threads 35/36: hook-caused (channel-summary run for 22-34; previous
  wiki-maintenance run 22-34) — skipped per skill.

Key insight: the same tool alternating between "Unknown tool" and success
across consecutive threads is a **tool-registration smoke test**, not a bug
and not a regression. No durable implementation facts in this window.

Maintenance actions this run:
- NEW `Reference/Smoke-Test-Threads.md`: how to recognize noop-provider
  smoke-test bursts (rapid single-tool threads, "Unknown tool: X" = toolset
  not registered, skip in maintenance) + the compact null-contract
  re-verification.
- index.md updated (Reference list entry).
- No template changes (nothing REALLY valuable enough for prompt-space cost);
  no skills created/deleted/merged (no new repeatable procedure beyond the
  existing live-smoke-toolbox skill, which already covers the toolbox
  pattern).


## 2026-08-22 (wiki-maintenance pass, threads 46-58)

Window 46-58 (profile omni) contained ONLY hook-caused + automated smoke-test
threads: relevance-indexer hooks (46, 49, 50 — "78 files indexed"), the
channel-summary hook (47), the previous wiki-maintenance trigger (48, which
created Reference/Smoke-Test-Threads.md), and noop/test-tool-caller smoke
bursts (51-58). No user conversations, no new durable facts.

- Extended `Reference/Smoke-Test-Threads.md` with the 51-58 confirmation of
  the tool-registration alternation: `plugin-manager_plugin-manager` unknown
  in 51 but works in 52/53; `search_database` unknown in 54 but works in
  55/56; `search_thread-messages` unknown in 57 but works in 58. Pattern =
  toolset not registered in that env, NOT a bug.
- No wiki page / skill / template additions, deletions, or merges (nothing in
  the window justified them).
## 2026-08-22 (wiki-maintenance pass, threads 58-70)

Window 58-70 (profile omni) contained ONLY hook-caused + automated smoke-test
threads: smoke bursts (58, 61-70 — noop/test-tool-caller single-tool runs;
`search_channel-prompts`/`search_channels`/`skills_list-skills` alternation
with "Unknown tool" = toolset not registered), the channel-summary hook (59),
and the previous wiki-maintenance pass (60, threads 46-58 — commits 5be82bf +
7ff2556, already pushed). No user conversations, no new durable facts.

- Extended `Reference/Smoke-Test-Threads.md` with the 61-70 confirmation of
  the tool-registration alternation (new tools in the burst:
  `search_channel-prompts`, `search_channels`, `skills_list-skills`).
- No wiki page / skill / template additions, deletions, or merges (nothing in
  the window justified them).

## 2026-08-22 (omniagent chain ops, hermes session)

- Created dev-executor kanban task on the omnidev board (omnistable-postgres-1,
  workflow `dev-executor`, auto_approve) to run the 4-step omnidev chain:
  `python3 omnidev.py setup` → `test` → `agent` → `prepare` in
  /opt/workspace/omni-deployer, run-to-green fixing issues mid-run.
- New spec: `Todo/OmnidevChainRunImplementation.md` (mirrors task body; verified
  inventory: omnidev.py subcommands 82-107, shared.setup 666-745, shared.agent
  841-938, shared.prepare 943+, STOP_TARGETS shared.py:398-402 — omnidev stops
  only omnideploy, never omnistable).
- Probed the running binary's create-field name: `workflow` populates
  workflow_id (task_18cdff915c641ab1), `workflow_id` leaves it NULL
  (task_18cdff916075076a) — use `workflow` on this binary. Status `todo` is
  honored at create. Probes deleted; board back to 0 tasks (fresh board, no
  dependency chain to join).

## 2026-08-22 (wiki-maintenance hook — threads 1-10)

- Window 1..10 = ALL automated smoke-test threads (noop provider /
  test-tool-caller), same pattern as Reference/Smoke-Test-Threads.md
  (threads 34-70): thread 1's cause is a cron step ({"name": "step1",
  "tool": "cron_list-cron-jobs"} — cron-triggered smoke thread); later smoke
  threads probe it via `search_thread-messages {thread_id: 1}` with the
  expected real-result / "Unknown tool" alternation. No durable facts -> no
  wiki/skill/template content changes from the window.
- Extended Reference/Smoke-Test-Threads.md with the earliest-burst
  observation (threads 1-10).
- Committed the pending 2026-08-22 chain-ops wiki edits found uncommitted in
  the working tree: Todo/OmnidevChainRunImplementation.md (new spec) +
  index.md entry + log.md entry + regenerated relevant-index.md.
  (config/*.yml + profiles/omni/config.json runtime changes NOT committed —
  live-stack managed.)

## 2026-08-22 (omnidev chain task — completed, hermes session)

- Task `task_18cdffbbda75676c` (dev-executor workflow, auto_approve) COMPLETED:
  all 4 omnidev chain steps exit 0 — setup 554s (images built, stack up,
  channel patched deepseek), test 302s (149 passed / 0 failed), agent
  (thread 76, answer 597), prepare 14s (mm-kanban registered, opencode-go +
  12 builtin tool MCPs enabled). omnistable untouched (7 containers before
  == after). No code fixes needed; omni-deployer clean.
- Provider failover (mid-task): first executor thread 79 died at iteration 2
  with `rate limited (HTTP 429); retry after 144622s` — mm-kanban channel was
  on opencode-go (Zen gateway monthly quota exhausted). Failover per
  provider-rate-limit-failover.md: edited live config/channels.yml (root-owned,
  via docker exec sed) mm-kanban provider → deepseek, PATCHed /channels
  (response showed deepseek), PATCHed task todo, auto-dispatched thread 80
  with provider=deepseek → ran to green. Repo HEAD already had deepseek
  (942512a); live file had been flipped back to opencode-go (runtime/prepare
  PATCH) — now aligned again.
- CORRECTION (2026-08-22, user): the restart of omnistable-omniagent-1 during
  the failover was NOT necessary — the running image is the CI-built GHCR
  latest (created 2026-08-21T23:31Z, from stable 58dbfcf), which contains
  omniagent `100c9d2` (2026-08-20: channel identity resolved AT LOAD TIME,
  no boot-time cache). File edit + PATCH alone takes effect on the next
  dispatch. The "restart required" note applied only to pre-100c9d2 binaries
  (verified 2026-08-20, thread 1741). Docs updated accordingly.

## 2026-08-22 (follow-up: OmnidevChainRun DONE)

- The chain-ops executor thread flipped Todo/OmnidevChainRunImplementation.md
  to **DONE** (task_18cdffbbda75676c, 2026-08-22 — all 4 steps exit 0) after the
  first maintenance commit; the status flip + index.md entry update were
  committed in the same maintenance session so the wiki stays consistent.

## 2026-08-22 (deploy.py hybrid stop-safety fix, hermes session)

- Fixed `deploy.py hybrid` stopping BOTH omnidev AND omnistable (omni-deployer
  `a62dc71`, main): `DEV_STOP_EXCLUDE` (dev-only) → mode-aware
  `MODE_STOP_EXCLUDE` = {dev: {omnistable}, hybrid: {omnidev, omnistable}}.
  dev unchanged (stops only omnidev); hybrid now stops NEITHER launcher
  (manages only its own omnideploy containers); ci unchanged (clean slate on
  fresh runner — publish.yml uses `deploy.py ci`).
- Verified: unit check of target selection per mode (hybrid → []) + live check
  in the omnistable container (repo bind-mounted: `hybrid stops: []`) +
  py_compile. Base compose binds no host ports, so hybrid running
  side-by-side with the launcher stacks is conflict-free.
- stable NOT touched (CI builds via `deploy.py ci`, unaffected; no release
  loop fired). Fix is live in the container via the bind mount.


## 2026-08-22 (wiki-maintenance pass, threads 10-22)

Window 11-22 (profile omni) contained ONLY hook-caused + automated
smoke-test threads: the channel-summary hook (11 — summarized threads 1-10
into the `summaries` table, next_thread_id=10), the previous
wiki-maintenance trigger (12, threads 1-10 — commits c547e24 + 400461e,
already pushed), and a noop/test-tool-caller smoke burst (13-22, 10 threads
created within ~30s, each a single trivial tool call: `filesystem_read`
README (13/14), `git_status` (15-17), `git_run-command log --oneline -3`
(18-20), `kanban_list-kanban-tasks` (21/22)). No user conversations, no new
durable implementation facts.

- Extended `Reference/Smoke-Test-Threads.md` with the 13-22 burst: new
  tools in the registration alternation (`filesystem_read`, `git_status`,
  `git_run-command`, `kanban_list-kanban-tasks`) and a NEW error variant —
  thread 15's `git_status` returned `External MCP server 'ssh' tool
  'status' failed: Missing required parameter: host` (name-collision:
  git_status not registered → resolved to the ssh `status` handler) instead
  of "Unknown tool". Still a test artifact, not a regression.
- `skills/git-workflow.md`: one-line pitfall — omniagent's `/mcp-server-*`
  + `plugins/tools/*/mcp-server-*` are Dockerfile-built binaries, gitignored
  and never versioned (7 ELF binaries removed from tracking, a923360);
  observed in the 19/20 smoke-test git log output.
- No wiki page/skill additions, deletions, or merges; no template changes
  (nothing in the window justified prompt-space cost).
## 2026-08-22 (wiki-maintenance hook — re-trigger, threads 34-46)

Re-trigger of the 34-46 window (hook counter reset after the test-DB
rebuild; previous trigger covered up to thread 34 with no changes).
Window = ONLY the already-documented automated smoke burst: thread 34
(compact-messages null-contract), threads 35/36 (channel-summary +
previous wiki-maintenance hook threads, channel `hooks`), threads 37-46
(noop/test-tool-caller single-tool runs with the expected "Unknown tool"
alternation for search_messages / search_wiki / subtasks_list /
actions_relevance-indexer). No user conversations, no new durable facts —
content matches the burst documented by run #6 (`5be82bf`,
Reference/Smoke-Test-Threads.md) byte for byte.
- No wiki page / skill / template additions, deletions, or merges (nothing
  in the window justified them; the window was already fully processed).
## 2026-08-22 (wiki-maintenance hook — re-trigger, threads 46-58)

Re-trigger of the 46-58 window (hook counter reset after the test-DB rebuild;
the window was already processed by the previous pass — commits 5be82bf +
7ff2556, log entry "wiki-maintenance pass, threads 46-58" +
Reference/Smoke-Test-Threads.md extension covering the 51-58
tool-registration alternation). Window = ONLY the already-documented
hook-caused + noop/test-tool-caller smoke threads: relevance-indexer hooks
(46, 49, 50), the channel-summary hook (47), the previous wiki-maintenance
trigger (48), and smoke bursts 51-58 (plugin-manager_plugin-manager unknown
in 51 but working in 52/53; search_database unknown in 54 but working in
55/56; search_thread-messages unknown in 57 but working in 58). No user
conversations, no new durable facts — the window was already fully processed.

- No wiki page / skill / template additions, deletions, or merges (nothing in
  the window justified them; content matches the previous 46-58 pass entry).

## 2026-08-22 (wiki-maintenance hook — re-trigger, threads 58-70)

Re-trigger of the 58-70 window (hook counter reset after the test-DB rebuild; the window was already processed by the previous pass — commit 039ed3f, log entry "wiki-maintenance pass, threads 58-70" + Reference/Smoke-Test-Threads.md extension covering the 61-70 tool-registration alternation). Window = ONLY the already-documented hook-caused + noop/test-tool-caller smoke threads: the channel-summary hook (59), the previous wiki-maintenance trigger (60), smoke burst 58 (`search_thread-messages` probe) and bursts 61-70 (`search_channel-prompts` unknown in 62 but working in 63/64; `search_channels` unknown in 65 but working in 66/67; `skills_list-skills` unknown in 68 but working in 69/70). No user conversations, no new durable facts — the window was already fully processed.

- No wiki page / skill / template additions, deletions, or merges (nothing in the window justified them; content matches the previous 58-70 pass entry).

## 2026-08-22 (deploy hybrid token-budget task, hermes session)

- Created dev-executor kanban task on the omnidev board to run `deploy.py
  hybrid` to green with HARD token caps: cache hit (cached_tokens) ≤ 2M AND
  cache miss (input−cached) ≤ 200K on the task's executor thread(s).
- New spec: `Todo/DeployHybridTokenBudgetImplementation.md` — mirrors task
  body; verified facts: hybrid stops neither omnistable nor omnidev
  (a62dc71 MODE_STOP_EXCLUDE), token recording live on threads
  (input/cached/output) + messages.token_usage, baseline thread 80 =
  721K cached / 128K miss (within caps).
- Hermes enforcement loop: monitor per-thread sums via SQL; if caps breached
  mid-run → stop-thread, fix (agent prompts/skills/wiki/prompt-generate/
  compact-messages/tools/templates), re-run deploy.py dev, re-measure, repeat.

## 2026-08-22 (wiki-maintenance pass, threads 70-82)

Window = smoke bursts + hook threads + a provider-429 failure cluster +
one fully-green omnidev chain re-run. No template changes (nothing REALLY
valuable enough for the prompt-space cost).

- **Smoke / non-durable threads (skipped for facts)**: 70 (skills_list-skills
  noop, closes the documented 61-70 burst), 71 (channel-summary hook →
  saved summary id=5, mattermost-stable-channel threads 58-70), 72
  (previous wiki-maintenance hook, pass 58-70 — commit 039ed3f), 73-75
  (memory_list-memories registration alternation: unknown in 73, works
  74/75), 76/77 (math-tester threads: real agent answers
  `What is 15 * 37 + 42?` → 597 — same probe shared.agent() posts in the
  omnidev `agent` step).
- **Provider rate-limit (HTTP 429) failure mode** (threads 78/79/81):
  3 consecutive LLM provider errors → thread marked failed, retry-after
  ~141-145k s (~39-40h), NO work done. Re-run succeeds (thread 80 = re-run
  of thread 79's omnidev chain task, fully green). Documented in
  Reference/Omni-Deployer.md + Smoke-Test-Threads.md identification note.
- **Omnidev chain re-run GREEN (thread 80)**: setup 554s → test 302s
  (149 passed / 0 failed) → agent (deepseek / deepseek-v4-flash / omni,
  omnidev-DB thread 76, 2652ms, 597) → prepare 14s (mm-kanban MM channel
  kus3t3196tdy3gzirjktmg8efw, members bot/testuser/admin, `$new mm-kanban`
  registered → omniagent channel id=mm-kanban, patched
  opencode-go/deepseek-v4-flash/profile omni, verified via GET /channels).
  omnistable untouched (count 7 before/after); omni-deployer tree clean; no
  code changes. The Todo status + timings were already recorded (400461e);
  this pass added the execution pattern + gotchas to
  Reference/Omni-Deployer.md.
- **docker_compose gotchas (from thread 80)**: `-p <project> ps` is NOT a
  valid command ("Unrecognized compose command '-p'. Allowed: up, down, ps,
  logs, build, restart, stop, exec, run, pull") — select the compose project
  via the `env_file` param (omnistable.env / omnidev.env). Long exec steps
  return processing + task_id → block on `builtin_wait-task(timeout_secs=900,
  tail=2000)`; never pass a timeout on docker_compose. Added to
  skills/workspace-development.md + Reference/Omni-Deployer.md.
- **DeployHybridTokenBudget**: first execution attempt (thread 81) failed
  pre-work on 429 — execution-history note appended to
  Todo/DeployHybridTokenBudgetImplementation.md.
- **Files changed**: Reference/Smoke-Test-Threads.md, Reference/Omni-Deployer.md,
  skills/workspace-development.md, Todo/DeployHybridTokenBudgetImplementation.md,
  index.md, log.md.


### ops | omni profile MEMORY.md: generalized TOKEN EFFICIENCY section (2026-08-22)

- Generalized the token-budget lessons from the deploy.py hybrid dev-executor task (thread 88 229K miss breach -> thread 89 88K miss PASS) into profiles/omni/memories/MEMORY.md.
- Principle: avoid UNNECESSARY token usage, not minimize total. Complex tasks legitimately burn tokens. Never self-monitor what a supervisor monitors (no token_usage queries), long commands = one background run + single generous wait-task, read output once (grep+tail combined), bound exploration (<=10 calls).
- Notes/subtasks/plans are NOT waste — they are the anti-hallucination machinery (compaction truncates tool results; notes prevent re-derivation; subtasks keep multi-step state; plans avoid wrong-approach costs).

### ops | omni-root synced to omni-stack (2026-08-22)

- Generalized token-efficiency lessons from the deploy.py hybrid dev-executor task into profiles/omni/memories/MEMORY.md (NEW TOKEN EFFICIENCY section): avoid UNNECESSARY token usage (not minimize total — complex tasks legitimately burn tokens); never self-monitor supervisor-tracked budgets; one background run + single generous wait-task; read output once; bounded exploration; notes/subtasks/plans are anti-hallucination machinery worth spending on.
- Committed omni-stack 05056f6, pushed to origin/main.
- Cloned nexuslbs/omni-root (private mirror) into /opt/workspace/omni-root, force-synced main to omni-stack HEAD (48d379b...05056f6), tags up-to-date, file lists identical, working tree clean. Removed local omni-stack remote + stripped token from origin URL after push.


### ops | deploy.py dev task GREEN + HOST_OMNI_DIR mapping verified (2026-08-22)

- Kanban task task_18ce1f61ab5890ec (dev-executor) ran `python3 deploy.py dev` to green: exit 0, ALL TESTS PASSED (incl. shared tool tests), ~52 min, log test-output/deploy_dev_20260822_1216.log. Thread 78 completed; tokens cached 907,136 <= 2M, miss 78,795 <= 200K.
- Thread 77 hit opencode-go HTTP 429 quota first -> failover: PATCH mm-kanban channel to deepseek/deepseek-v4-flash, committed live channels.yml pin (omni-root 55fa1b2 + omni-stack a60d394), re-dispatched -> thread 78 ran on deepseek.
- **Mapping verified live**: omnideploy container binds /opt/workspace/omni-stack -> /opt/omni (HOST_OMNI_DIR=omni-stack in omni.env); omnistable binds /opt/workspace/omni-root -> /opt/omni, count 7 unchanged. omni-deployer ships NO compose files (removed; compose lives in omni-stack+omni-root equal mirrors via HOST_OMNI_DIR default /opt/omni).
- Earlier: both omnidev + omnistable chains ran GREEN from fresh omni-root (149/0, agent 597, prepare complete) — remote plugins seeded automatically in shared.setup via install-git API (no manual intervention).
- Commits: omni-deployer 09404e3, omni-stack 74814ab + a60d394, omni-root 5dba993 + 55fa1b2.
