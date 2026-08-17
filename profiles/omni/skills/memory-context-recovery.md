# Memory & Context Recovery

Use this skill when you need to recall prior work, understand project history, or find information that is not in the current conversation context. There are three layers of memory available to you.

## 1. Wiki / Long-Term Memory

The wiki is the durable knowledge base for this profile. It lives under `profiles/omni/wiki/` and is organized into pages plus a `Reference/` directory.

- **`search_wiki`** — search wiki pages by keyword. Use this FIRST for project conventions, architecture notes, and known pitfalls that were captured from previous sessions.
- Wiki pages are maintained over time — if you learn something durable, consider promoting it so future sessions benefit.

## 2. Messages / Threads Database

All past agent conversations (threads and messages) are stored in the omniagent PostgreSQL database. The consolidated `search` plugin provides all retrieval tools (the former query_*/metrics_* tools were merged into it).

- **`search_messages`** — search past messages/threads by keyword (ILIKE). Use this to recall what was done in previous sessions, what decisions were made, and how problems were solved.
- **`search_thread_messages`** — read all messages in a conversation thread. Defaults to the current thread; pass `thread_id` for another.
- **`search_channel_prompts`** — list the first message (prompt) of every thread in a channel. Defaults to the current channel.
- **`search_channels`** — list channels (id, name, platform, cause) to find the `channel_id` for channel-scoped queries.
- **`search_database`** — run read-only SQL against the omniagent database when you need structured queries:
  - Threads: `SELECT id, channel_id, status, cause, provider, model, created_at FROM threads ORDER BY id DESC LIMIT 20;`
  - Messages: `SELECT id, thread_id, role, thread_sequence, substr(content,1,200) FROM messages WHERE thread_id = <id> ORDER BY thread_sequence;`
  - Channels: `SELECT id, name, platform, resource_identifier, current_provider, current_model FROM channels;`
  - Kanban: `SELECT id, title, status, priority, channel_id, profile FROM kanban_tasks ORDER BY id DESC LIMIT 20;`
- **`search_metrics`** — agent metrics (token usage, latency, message counts, groundedness) aggregated from the messages table.

## 3. Agent Memories

The memory tool maintains an explicit memory store for the agent.

- **`memory_list-memories`** — list all stored memories with their metadata.
- **`memory_manage-memory`** — add, update, or remove memory entries.
- **`memory_promote-to-memory`** — promote validated facts from conversations into durable memory.
- **`memory_review-memories`** — review memory health (expired/stale entries).
- **`memory_generate-summary`** — generate a summary of a conversation or channel for later recall.

## When to Use Which

| Need | Tool |
|------|------|
| Project conventions / known pitfalls | `search_wiki` |
| What was done in a previous session | `search_messages` |
| Full contents of a past thread | `search_thread_messages` |
| Find channel ids for scoped queries | `search_channels` |
| Structured lookups (threads, tasks, channels) | `search_database` |
| Agent performance / usage stats | `search_metrics` |
| Facts you want the agent to retain | `memory_manage-memory` / `memory_promote-to-memory` |

## Pitfalls

- Prefer `search_wiki` and `search_messages` over raw SQL for free-text recall — they handle relevance ranking for you.
- Use `search_database` only for read-only queries; never modify the database directly.
- Do not store transient task state in memory — memory is for durable facts that matter across sessions.
- If a prior session's work is relevant to the current task, search for it BEFORE asking the user to repeat themselves.
