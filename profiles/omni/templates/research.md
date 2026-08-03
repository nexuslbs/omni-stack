# Research Workflow

## Context Budget (research flavor)
- This thread still has a HARD limit of ~120 tool calls, but research is exploration-
  heavy BY DESIGN: reading sources and gathering data IS the deliverable. Budget for
  it: spend the exploration calls on batching and note-taking, not on re-discovery.
- READ FILES / SOURCES ONCE and take notes as you go (working notes or a scratch file
  under /tmp/ or /opt/workspace/.research-notes/). Compaction keeps only a short excerpt
  of tool results, so after a compaction you will NOT remember what you read — your
  notes survive. Re-reading the same source teaches you nothing new.
- Fetch ALL external data in ONE batch. Do NOT fetch one URL at a time.
- COMPLETE in 2-4 tool-calling rounds max. More than 6 means you failed to batch.
- If you cannot finish in this thread: write what you have to the output file, and
  report exactly what remains. NEVER die with the findings still in your head.

## Process
1. If the prompt already contains the question, use it directly: no separate file needed.
2. ALWAYS `search_messages` first for past context; `search_wiki` for existing knowledge.
   Past research, decisions, and conventions may already cover the topic.
3. Gather internal context (search_messages / search_wiki / query_database) BEFORE
   fetching external data — you need to know what's already known.
4. Fetch ALL external data in ONE batch. Batch = one tool call that pulls several
   sources, or at minimum group your fetches so you never round-trip one URL at a time.
5. Take notes per source as you fetch. Structure them by question/subtopic so the
   final write-up is assembly, not re-research.
6. Verify by re-reading your own output: citations resolve, numbers match sources,
   tables render, no invented facts.

## Output Quality
- Clear headers, comparison tables where the data lends itself, cited sources (URLs).
- Answer the question asked; do not pad with tangents.
- If the evidence is conflicting or incomplete, SAY SO explicitly rather than smoothing
  it over. Honesty about uncertainty beats confident hallucination.

## Output Path
- Write the report to `/opt/workspace/data/research/<category>/` (the ONLY writable
  location — filesystem_write is sandboxed to /opt/workspace; `/opt/omni` is
  read-only for the agent).
- Category reflects topic domain (e.g. 'agents', 'deployment', 'security').
- If the prompt specifies a filename, use it. Otherwise, the agent defines one.

## Where to find deeper guidance
- Tool execution details: skill `workspace-development`, `memory-context-recovery`.
- Environment facts (mounts, port checking, compaction behavior): wiki `Reference/*` pages + MEMORY.
