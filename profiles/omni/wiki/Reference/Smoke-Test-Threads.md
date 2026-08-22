# Smoke-Test Threads (noop provider)

How to recognize automated smoke-test threads and skip them in maintenance.
Observed live 2026-08-22 in the rebuilt test DB (threads 34-58, profile omni).

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
  `search_thread-messages` unknown in 57 but works in 58.

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

## How to identify before reading

- Query threads table: `SELECT id, channel_id, profile, created_at FROM
  threads WHERE id BETWEEN <last> AND <current> ORDER BY id` — a run of
  consecutive ids with `created_at` within seconds of each other + all in
  `mattermost-stable-channel` (or the test channel) = smoke burst.
- Spot-check one thread: if the reply names the `noop` provider /
  `test-tool-caller` model, the whole burst is smoke tests.
