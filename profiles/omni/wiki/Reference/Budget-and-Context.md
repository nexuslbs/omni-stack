# Budget & Context Mechanics

How the agent's thread budget and context compaction actually work — so guidance can
be written (and tasks dispatched) against reality.

## Thread budget

- Threads on this deployment have a hard ~120 tool-call budget. There is no UI count;
  the practical signal is: exploration-heavy threads die mid-task with zero commits.
- Budget discipline belongs in the task template (dev vs research shapes differ).
  Memory carries only the universal rules (commit partial work, verify pushes).

## Compaction (prompt plugin `compact.rs`)

- Compaction triggers when conversation size exceeds the HARD budget (default
  char_budget_hard = 500000), reducing it TO the soft budget (350000).
- What compaction does: old assistant tool-call messages are replaced with a
  `[compact: tool_a(), ...]` marker, and the tool-role messages are drained —
  BUT the marker now embeds a content excerpt of each drained tool result
  (first ~800 chars per tool, capped at ~4000 chars total).
- Consequences for the agent:
  - After compaction you keep a SHORT excerpt of what you read, not the full content.
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

## Dispatch implications (for Hermes / task authors)

- Pre-verify facts before dispatching; embed file paths WITH line numbers so the
  agent doesn't burn budget confirming them.
- Lead with a context-budget warning when the task needs exploration.
- Expect the agent to commit partial work; verify pushes after completion
  (local == origin/main), don't trust self-reports.
