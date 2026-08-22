# Smoke-Test Threads (noop provider)

How to recognize automated smoke-test threads and skip them in maintenance.
Observed live 2026-08-22 in the rebuilt test DB (threads 1-10, 13-22 and
34-70, profile omni).

## Pattern

- Threads are created in **rapid bursts** (seconds apart, e.g. 13 threads in
  ~31s), all in the same channel, all profile `omni`.
- Each thread makes exactly **one tool call** with trivial arguments
  (e.g. `search_messages {query: "test", limit: 1}`,
  `search_wiki {query: "omniagent", limit: 1}`,
  `subtasks_list-subtasks {thread_id: 1}`, `actions_relevance-indexer {}`,
  `prompt_compact-messages {1-msg input}`).
- The replies come from the **`noop` test provider / `test-tool-caller`
  model** — "This is a reply to your message from the **test provider**
  `noop` using the model **test-tool-caller**".
- Tool results alternate between a real result and
  `Error executing tool '<name>': Unknown tool: <name>` for the SAME tool
  (e.g. search_messages works in threads 38/39 but is "Unknown tool" in 37;
  search_wiki works in 41/42 but not 40; subtasks_list works in 44/45 but not
  43). This is a **tool-registration smoke test** — each thread runs with a
  different toolset on purpose. Confirmed again in threads 51-58:
  `plugin-manager_plugin-manager` unknown in 51 but works in 52/53;
  `search_database` unknown in 54 but works in 55/56;
  `search_thread-messages` unknown in 57 but works in 58. Confirmed again in
  threads 61-70: `search_channel-prompts` unknown in 62 but works in 63/64;
  `search_channels` unknown in 65 but works in 66/67;
  `skills_list-skills` unknown in 68 but works in 69/70.
- The EARLIEST burst (threads 1-10, 2026-08-22T02:47Z) already showed it:
  thread 1's cause is a cron step (`{"name": "step1", "tool":
  "cron_list-cron-jobs"}` — a cron-triggered smoke thread), and later smoke
  threads probe it with `search_thread-messages {thread_id: 1}` — the reply
  alternates a real 5-message listing vs "Unknown tool:
  search_thread-messages", the same registration test.
- Confirmed again in threads 13-22 (2026-08-22T02:48Z, right after the 1-10
  burst) with git/kanban/filesystem tools:
  `filesystem_read` README.md works (13/14); `git_status` works (16/17) but
  thread 15 shows a **name-collision variant**: the call returned
  `External MCP server 'ssh' tool 'status' failed: Missing required
  parameter: host` — the executor resolved `git_status` to the ssh server's
  `status` tool instead of erroring "Unknown tool"; `git_run-command`
  (log --oneline -3) unknown in 18 but works in 19/20 (real output shows
  HEAD a923360, the MCP-server-artifact-removal chore); `kanban_list-kanban-
  tasks` unknown in 21 but works in 22 (`_No kanban tasks found._`).

## Consequences (durable facts)

1. **"Unknown tool: X" in these threads is EXPECTED** for toolsets that don't
   register that tool — it is a test artifact, NOT a bug and NOT a regression.
   Do not chase it.
2. **No durable facts live in smoke-test threads** — skip them in
   wiki-maintenance (they are trivial single-tool noop runs).
3. Hook-caused threads (channel `hooks`) are also skippable unless they carry
   durable facts (e.g. the previous wiki-maintenance run's relevant-index
   refresh). Threads in channel `hooks` = hook-caused by definition.
4. The `prompt_compact-messages` null-contract is verified by these tests:
   under the hard budget → `messages: null, was_compacted: false`
   (matches Reference/Budget-and-Context.md — compaction only fires over the
   hard budget).
5. A tool call can fail with a WRONG-HANDLER error instead of "Unknown tool"
   (thread 15: `git_status` → ssh `status` missing `host`) — still a
   registration-test artifact, not a regression; don't chase it.

## How to identify before reading

- Query threads table: `SELECT id, channel_id, profile, created_at FROM
  threads WHERE id BETWEEN <last> AND <current> ORDER BY id` — a run of
  consecutive ids with `created_at` within seconds of each other + all in
  `mattermost-stable-channel` (or the test channel) = smoke burst.
- Spot-check one thread: if the reply names the `noop` provider /
  `test-tool-caller` model, the whole burst is smoke tests.
