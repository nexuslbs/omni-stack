# Channel Summary (channel-scoped)

Triggered by the channel-scoped `thread_finished` hook every 10 threads. You
create a structured summary of the threads of ONE channel between
`last_thread` and `current_thread` (Event JSON) and persist it in the
`summaries` table.

## Scope rules (MANDATORY)

- Work ONLY on the channel named in the Event JSON (`channel` field). Never
  include threads from other channels.
- Base the summary on threads between `last_thread` and `current_thread`
  (both inclusive). IGNORE all threads after `current_thread`.
- You MAY read threads before `last_thread` for context (especially the
  previous summary via `search_database` on the `summaries` table), but the
  summary must focus on the threads between the two ids.

## How to gather the material

1. `search_database`:
   `SELECT id, channel_id, profile, created_at, cause FROM threads WHERE id
   BETWEEN <last_thread> AND <current_thread> ORDER BY id` — keep only rows
   whose channel matches the Event JSON channel.
2. For each thread, read the messages with `search_thread-messages`. Skip
   tool-result/tool spam; keep user prompts, decisions, commands, file paths,
   config keys, numbers, and outcomes.
3. Optionally fetch the previous summary
   (`SELECT content FROM summaries WHERE channel_id = '<channel>' ORDER BY id
   DESC LIMIT 1`) to connect new material to it.

## Summary format (structured markdown)

Write the summary with these sections:

- **Topics**: bullet list of main topics with specifics (paths, commands).
- **Key Decisions**: what was decided, why, affected files.
- **Action Items**: status (done/pending/failed), task, details.
- **Entities Referenced**: systems/files/config referenced.
- **Thread Count**: total threads covered, first id, last id.

Be specific and grounded — every claim must come from a thread you read.

## Saving the summary

Call `memory_save-summary` with exactly:

- `channel_id`: the channel NAME from the Event JSON (`channel`).
- `next_thread_id`: `current_thread` from the Event JSON (the highest thread id
  covered).
- `content`: the full markdown summary text.

The tool INSERTs a row into the `summaries` table (channel_id,
next_thread_id, content). It returns the new summary id — confirm the save
succeeded before finishing.

## Fallback (observed 2026-08-22, hook run for threads 1-10)

In some hook environments the MCP tools `search_database` /
`search_thread-messages` / `memory_save-summary` are NOT exposed. Fall back
to direct postgres access:

- Read threads/messages via
  `docker_compose exec <postgres-service> psql -U <user> -d <db> -c "SELECT
  ..."` (the omni-stack postgres, e.g. in /opt/workspace/omni-deployer).
- Save the summary with a direct
  `INSERT INTO summaries (channel_id, next_thread_id, content) VALUES
  ('<channel>', <current_thread>, '<escaped markdown>')` and verify with a
  SELECT.
