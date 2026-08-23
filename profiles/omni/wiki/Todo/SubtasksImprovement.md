# Subtasks Improvement (Research + Implementation Spec)

**Status:** IMPLEMENTED (omniagent `14e832f` — real manage_subtasks tool + markdown-plan auto-create + token-safe enforcement; `d601dd5` numeric-string ids)
**Date:** 2026-08-16
**Scope:** omniagent (subtasks plugin + core wiring), omni-stack (config/prompt/templates), omni-deployer (tests: noop test-tool-caller + manual)

## Goal

Decide what to do about thread subtasks. They exist as a builtin plugin
(`plugins/tools/subtasks/`, `mcp-server-subtasks`) but in practice the agent
never uses them, and when it did the result was broken. This spec documents
the root causes (verified in code + live DB), compares against opencode CLI
subtasks and Hermes' todo tool, and prescribes the fix.

## Verified root causes (evidence)

> Line refs verified against origin/main 2026-08-16 (post SSH plugin). Note:
> the prompt plugin lives at `plugins/tools/prompt/` — `prompt_builder.rs` is
> at `plugins/tools/prompt/src/prompt_builder.rs`, NOT `src/agent/prompt_builder.rs`.

1. **`manage_subtasks` tool does not exist.** The core enforcement
   (src/agent/main_loop.rs:912, 1615, 1631), README (README.md:119-121), and
   templates/knowledge-pipeline.md all instruct the agent to call
   `manage_subtasks(action="update", ...)`. The plugin only exposes
   `add_subtask`, `list_subtasks`, `update_subtask`, `delete_subtask`,
   `get_subtask_counts` (plugins/tools/subtasks/src/main.rs:419 etc.). Any
   agent following the instructions gets a tool-not-found error.
2. **Write tools disabled in allowed_tools.** Profile config.json allows only
   `subtasks_list-subtasks` (38 allowed tools total, verified
   profiles/omni/config.json in omni-stack). The agent physically
   cannot add/update/delete subtasks. A read-only list is useless alone.
3. **Auto-create is dead code.** main_loop.rs:282 parses the plan with
   `serde_json::from_str` expecting `{"steps": [...]}`, but the plan prompt
   says "Wrap your plan in a <plan> block" and every real plan in the DB is
   markdown (`<plan>1. …</plan>`). JSON parse always fails → no subtasks ever
   created. Live DB has **0 rows** in `thread_subtasks` (verified omnistable).
   Note: `enable_subtasks = should_plan` (main_loop.rs:65) — subtasks only
   run in plan mode.
4. **Prompt never references subtasks.** The tool-categorizer
   (plugins/tools/prompt/src/prompt_builder.rs:45) checks
   `tool_names.starts_with("manage_subtask")` but real names are `subtasks_*`
   → `has_subtasks` always false → subtasks never appear in tool lists,
   capability descriptions, or TOOL_GUIDANCE.
5. **Enforcement is a landmine.** If subtasks DO exist (manual DB insert), the
   end-of-thread gate orders the agent to call the phantom tool (main_loop.rs
   :902-933 retry loop, `max_unfinished_subtask_retries` default 3 —
   config.rs:230,329,412), then **force-fails the thread**;
   response_handler.rs:323 force-fails completed threads with unfinished
   subtasks too (exception: iteration limit reached keeps `interrupted`).
   A completed task with stale subtask rows would be marked failed.
6. **Cache-hostile injections.** "[Subtask Required]" (main_loop.rs:911, loop
   exit) and "[Progress Check]" (main_loop.rs:1630, every 3 rounds) system
   messages mutate the context prefix mid-run, breaking DeepSeek prefix
   caching — the exact failure class fixed in Reference/DeepSeek-Prefix-Cache.md.

## Comparison (research)

- **opencode CLI**: two mechanisms — (a) **subagents**: separate child
  sessions with own context, invoked via `@mention` or auto for parallel work
  (general/explore/scout; `todo` disabled in subagents); (b) **todowrite /
  todoread**: "Creates and updates task lists to track progress during complex
  operations" — lightweight in-session checklist maintained by the LLM.
- **Hermes**: `todo` tool — in-conversation checklist {id, content, status},
  one in_progress at a time, merge semantics. No DB/table overhead; the list
  is re-injected each turn. Works because it's trivial and always visible.
- **omniagent notes** (`notes_note-*`): the mechanism that ACTUALLY works —
  durable working memory in `data/threads/<id>/notes.md`, survives compaction
  and thread death, taught in templates (threads 76/77/78 all have notes.md).
  Notes = "what I learned"; subtasks = "what remains" (plan progress).

## Verdict

**Subtasks give real value IF fixed coherently.** The concept is sound
(plan-progress layer, complementary to notes), the infrastructure exists (DB
table, `## Subtasks` context block at prompt main.rs:1373, get_current_subtask,
enforcement hooks), and opencode/Hermes both validate LLM-maintained checklists.
The failure is 6 layers of name/format/enablement drift since the 0a194fa
refactor (planning_mode → plan bool) rewrote the prompt plugin and dropped the
caller of format_subtask_section.

**Path A-lite (recommended) — fix/align, don't rebuild:**

1. **Add a real `manage_subtasks` tool** to the subtasks plugin — a single
   tool with `action` param (add/list/update/delete/get_counts) matching the
   README, enforcement strings, and knowledge-pipeline template. (Alternative:
   rename all guidance to the real tool names — more churn, templates already
   say manage_subtasks.) The unified tool returns counts + affected row, NOT
   the full list on every call (token efficiency).
2. **Auto-create from real markdown plans**: extract the `<plan>` block,
   parse numbered/bulleted lines (max 6, priority preserved) instead of
   requiring JSON — or ask the plan phase to emit `{"steps":[...]}`. Real
   plans are markdown; fix the parser, not the prompt.
3. **Enable `subtasks_*` (or `manage_subtasks`) in allowed_tools** (config.json
   — omnidev + omnistable profiles); fix the tool-categorizer prefix check
   (`starts_with("subtasks_")` or `== "manage_subtasks"`).
4. **Prompt guidance**: add TOOL_GUIDANCE — "after planning a multi-step task,
   create one subtask per plan step; mark completed as each finishes; before
   the final answer complete or cancel all subtasks." Keep the `## Subtasks`
   context block (protocol-correct, cache-stable — it's part of context
   assembly, not a mid-run injection).
5. **Token-safety rules**:
   - `max_unfinished_subtask_retries` = 1 (not 3) — one enforcement nudge max.
   - Never force-fail when iteration limit reached (already the case).
   - Inject enforcement as **user-role appended at end** (preserves prefix
     cache) — never a mid-run system-role upsert.
   - Drop the every-3-rounds "[Progress Check]" nudge, or gate it on
     `pending > 0` AND no subtask tool call in the last 10 rounds.
6. **Tests**: plugin unit test for `manage_subtasks` actions; one integration
   test proving a complex thread creates + completes subtasks and reaches
   `completed` (not failed).
7. **Docs**: README already documents manage_subtasks (becomes true);
   knowledge-pipeline template becomes valid; dev-development.md adds a
   subtask-usage rule alongside the notes rules.

**Rejected alternatives:**
- *Kill subtasks entirely*: notes already cover durable tracking, but plan
  progress (pending/completed/cancelled, current subtask, counts) is a
  distinct useful signal — and the infra is already built. Net-negative churn
  to remove.
- *Full rebuild (DB → notes-embedded todo)*: opencode/Hermes show a
  context-only todo works, but omniagent's threads are long-lived and survive
  compaction; DB persistence is a feature (resume after retry), not a bug.

## Execution plan (kanban task)

- Scope: omniagent repo (subtasks plugin + main_loop + prompt plugin),
  omni-stack (config.json allowed_tools, templates, AGENTS.md), omni-deployer
  (tests if feasible).
- Omnistable frozen: changes reach omnistable only via next CI build from main.

## Testing requirements (user spec, 2026-08-16)

The tester MUST verify subtasks both ways — automated fake-agent tests AND
real end-to-end manual tests:

### 1. Automated tests with the noop provider `test-tool-caller` (fake agent)

- The `noop` provider with model `test-tool-caller` (implemented in
  omni-plugins/providers/noop) is a FAKE agent: it parses a JSON script
  `[{"name": "step1", "tool": "...", "arguments": {...}}]` posted as a channel
  message, executes each step as a tool call through the real agent loop, and
  posts the results back. It exercises tools "as an agent" with no real LLM.
- Tests must be written in omni-deployer `scripts/tests.py` following the
  GROUP 12/13/14 pattern (dedicated `mattermost-test-channel` pinned to
  noop/test-tool-caller, NEVER patch the kanban channel — 2026-08-09 incident).
- Script steps should drive the subtasks tools end-to-end through the agent:
  create a plan-mode thread, post a script calling `manage_subtasks(action=
  "add", ...)` / `list` / `update` / `get_counts`, then verify the thread
  reaches `completed` (NOT failed) with subtask rows created and finished.
- Also unit tests: plugin unit test for `manage_subtasks` actions (add/list/
  update/delete/get_counts), and the auto-create-from-markdown-plan parser.

### 2. Real manual tests (subtasks actually working end-to-end)

- Create a REAL task in omnidev (dev workflow, kanban) that asks the omnidev
  agent to run a task using subtasks — e.g. a multi-step task with plan mode
  enabled — and verify it runs successfully: subtasks get created from the
  plan, get updated as steps complete, and the thread ends `completed` (never
  force-failed by the enforcement gate).
- Both executor AND tester should do such manual runs (executor proves it
  works; tester independently re-verifies).
- Keep manual tasks SHORT to avoid wasting tokens: 3-6 steps, small scope
  (e.g. create files in a throwaway test project, run a couple of commands,
  no long builds). Do NOT change local state — except a dedicated test
  project (e.g. a scratch dir/repo that the task may create and clean up).
- The manual test must NOT touch omnistable: run it in omnidev only
  (omnistable stays frozen).

### 3. Acceptance gates (both modes)

- A plan-mode thread that uses subtasks reaches `completed` with
  `thread_subtasks` rows created → updated → completed (query
  `thread_subtasks` for the thread).
- A thread that ends WITHOUT finishing its subtasks must NOT be force-failed
  when the iteration limit was reached (keep `interrupted`), and the
  enforcement nudge must fire at most once (`max_unfinished_subtask_retries`
  = 1).
- `cargo check --workspace --all-targets`, `cargo clippy -- -D warnings`,
  `cargo test` (full suite incl. new unit tests) all green in omnidev;
  deploy runs fully green (exit 0, no errors/skips); never weaken/remove
  existing tests.
