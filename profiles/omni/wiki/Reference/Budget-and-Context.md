# Budget & Context Mechanics

How the agent's thread budget and context compaction actually work — so guidance can
be written (and tasks dispatched) against reality.

## Thread budget

- Threads on this deployment have a hard ~120 tool-call budget. There is no UI count;
  the practical signal is: exploration-heavy threads die mid-task with zero commits.
- Budget discipline belongs in the task template (dev vs research shapes differ).
  Memory carries only the universal rules (commit partial work, verify pushes).

## Context management is PLUGIN-OWNED (architecture rule, 2026-08-19)

The core engine has NO compaction/pruning logic. Every iteration it passes the
conversation to the configured prompt plugin's `compact-messages` tool and applies
whatever comes back (`"messages": null` = no-op, prefix untouched). A user may write
a CUSTOM prompt plugin that compacts/prunes in a completely different way — the core
depends only on the tool interface (messages + budgets in, messages array or null
out). The bundled Rust prompt plugin (`plugins/tools/prompt`, `compact.rs`) is one
implementation; the python `prompt` plugin in omni-plugins is another, and both
answer through the same interface.

## Compaction + pruning (prompt plugin `compact.rs`)

- Budgets are TOKEN-ONLY (char budgets removed 2026-08-19, task 12). Compaction
  triggers when conversation size exceeds the HARD token budget (default
  `prompt_token_budget_hard` = **500000**), reducing it TO the soft budget
  (`prompt_token_budget_soft` = **100000**); without a tokenizer the **chars/4
  proxy** applies, so a 200K-char context counts as 50K tokens.
- Budgets are GLOBAL SETTINGS in omniagent (`src/agent/config.rs`
  `token_budget_hard/soft`, defaults soft 100000 / hard 500000 at both load
  sites) and are passed to the compact-messages tool as
  `soft_budget`/`hard_budget` REQUIRED PARAMS — the prompt plugin has NO budget
  config. Effective per-thread values resolve the chain **model (models.yml) >
  provider (models.yml) > global settings**; see
  `Todo/ContextBudgetUnificationImplementation.md` and log 2026-08-19.
- The tool is CALLED every iteration but COMPACTS only when the hard budget is
  exceeded; under budget it returns `"messages": null` and nothing changes
  (null-contract — byte-identical prefix, DeepSeek prefix cache preserved).
- What compaction does (cache-friendly): old assistant tool-call turns are drained
  and their content excerpt folds into ONE frozen `=== Compaction Summary ===`
  block at a fixed index right after the system prompt (append-only on later
  compactions). Surviving messages are NEVER rewritten — the tail stays
  byte-identical, in order (any in-place rewrite shifts every following byte and
  kills the prefix cache).
- **Pruning lives INSIDE compact-messages** (task 15, omniagent `e8239a0`; core
  `prune_old_tool_results`/`PruneConfig` deleted): when over the hard budget the
  tool drains old tool-result turns; the most recent read-type results
  (filesystem_read/list/search/info, search_*, skills_view, git_status...) are kept
  in full, older ones are excerpted (`prompt_read_excerpt_chars` = 2000) AND
  auto-noted into the thread's durable `auto-notes.md` (`[engine:auto-note ...]`
  entries; thread_dir arg) so the agent never loses what it read (thread-700
  re-read death-spiral fix).

## Consequences for the agent

- After compaction you keep a short excerpt of what you read, not the full content.
- If a file's key facts are beyond the excerpt, you must have written them to notes
  BEFORE compaction. Re-reading after compaction teaches you nothing new.
- Long conversations get compacted repeatedly; notes are the only durable memory.

## prompt_generate context blocks

The prompt plugin assembles context from the DB:
- Recent thread messages (last 10, truncated to 500 chars each).
- Latest channel summary (up to 4000 chars) + recent completed threads.
- Available skills (names + one-line descriptions).
- Subtasks for the thread.

So a new thread does NOT automatically see the full text of prior tool calls —
it sees the summary/excerpt layer. This is why the agent must carry notes forward.

## filesystem_read paging

- `filesystem_read(path, offset=0, limit=50000)` returns char-based slices.
- Response reports the slice: `[showing chars 50000-100000 of 250000 total chars]`.
- No-args = legacy behavior (first 50k chars + truncation note).
- `filesystem_search` matches FILE NAMES only (glob), NOT contents.
- Cache guidance: prefer SMALLER result windows and page only when needed — the
  full content may be needed later, and silent truncation is never applied to a
  read result (any truncation the agent sees is explicit in the tool response).

## Dispatch implications (for Hermes / task authors)

- Pre-verify facts before dispatching; embed file paths WITH line numbers so the
  agent doesn't burn budget confirming them.
- Lead with a context-budget warning when the task needs exploration.
- Expect the agent to commit partial work; verify pushes after completion
  (local == origin/main), don't trust self-reports.
