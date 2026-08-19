# Wiki Data Source + Wiki Skill — Implementation

**Status:** Todo (task 13 in the serial chain, after budget unification)
**Date:** 2026-08-19
**Scope:** omniagent repo (assess/decide) + omni-stack profile skills (implement)

## Goal

Resolve the "wiki" finding from the 7-day usage report (no wiki tool used) —
decide what the wiki IS in omniagent, whether the current surface is relevant,
and ship the user-requested fix: a **wiki skill** (Karpathy method + Obsidian
format + general wiki conventions) with **concrete filesystem-tool examples**,
so agents actually use and maintain the wiki.

## Verified facts (do not re-derive — greps from 2026-08-19)

- **There is NO dedicated "wiki" builtin plugin.** `plugins/tools/` = cron,
  docker, fetch, filesystem, git, kanban, memory, notes, plugin-manager,
  prompt, search, skills, ssh, subtasks, util.
- "wiki" in omniagent = a **data source**: `{OMNI_DIR}/profiles/<profile>/wiki`
  (markdown). Two read paths:
  1. `search_wiki` MCP tool from the **search** plugin
     (`plugins/tools/search/src/main.rs:146` handler, `:1248` registration) —
     keyword scan of the active profile's wiki dir. It IS in the live
     `allowed_tools` (profiles/omni/config.json).
  2. Optional Qdrant vectorization: settings `vectorize_wiki`
     (config/settings.yml:50 = **false**), `wiki_vectorization_api_key/model/url`
     all empty, method local, protocol openai; worker
     `src/vectorizer/mod.rs:433` (scans wiki .md, embeds into Qdrant
     `wiki` collection).
- **Usage: 0 real `search_wiki` calls in 7 days** on omnistable (messages
  `msg_type='tool'` with `"name":"search_wiki"` = 0; the 1445 prompt hits are
  tool-list echoes in system prompts). Matches the usage-report finding.
- The wiki content IS populated and live-maintained: profiles/omni/wiki/
  `index.md` (14 KB catalog), `log.md` (47 KB action log), `relevant-index.md`,
  `Memory/`, `Reference/`, `Todo/` (30+ Implementation specs).
- A **wiki-maintenance skill already exists** in the omni profile:
  `profiles/omni/skills/wiki-maintenance.md` (shipped by the
  HooksWikiSummaries task; a `thread_finished` hook maintains wiki/templates/
  skills). It teaches the maintenance *loop*; it does not teach the *method*
  (Karpathy) or *format* (Obsidian) or give filesystem-tool walkthroughs.
- Guidance architecture documented at
  `profiles/omni/wiki/Reference/Agent-Guidance-Architecture.md` (memory →
  templates → skills → wiki layers).
- omniagent agents have **no shell**: all file ops go through `filesystem_*`
  MCP tools — the skill examples MUST use those tools.

## Requirements

1. **Decision (make it explicit in the spec/PR):** wiki stays a data source +
   skill; do NOT build a new wiki plugin. Rationale: the read path exists
   (`search_wiki`) and the content is maintained by hooks; the gap is agent
   education + usage, which a skill fills at zero runtime cost.
2. **Write/extend the wiki skill** in profiles/omni/skills/ (recommended: new
   `wiki.md` that references + complements `wiki-maintenance.md`, or extend the
   existing file — executor's choice, keep both discoverable):
   - **Karpathy method**: durable knowledge layer — `index.md` = catalog of
     everything, `log.md` = append-only action log, pages under `Memory/`
     (facts), `Reference/` (how-to/architecture), `Todo/` (implementation
     specs). Every entry linked from the index; every action logged.
   - **Obsidian format**: YAML frontmatter, `[[wikilinks]]`, markdown headings,
     file-per-topic, link-don't-copy.
   - **Filesystem-tool examples** (the actual omniagent toolset): how to read
     `index.md` first (`filesystem_read`), find pages (`filesystem_search`
     file names + `search_wiki` text), create/update a page
     (`filesystem_write`), list the wiki tree (`filesystem_list`), append to
     `log.md`. Include a short worked example (e.g. "record a new decision").
   - **When to use what**: `search_wiki` (text) vs `filesystem_search`
     (names) vs reading `index.md` (catalog) vs `search_messages` (conversation
     history — NOT wiki).
3. **Surface the wiki in agent guidance**: check `index.md` before asking the
   user something the wiki may already answer (align with
   Agent-Guidance-Architecture).
4. **vectorize_wiki stays off** unless real `search_wiki` usage emerges (no
   Qdrant/API cost for an unused feature). Document this in the spec.
5. Update `Reference/Agent-Guidance-Architecture.md` if the skill changes the
   guidance model wording.

## Non-goals / DO NOT CHANGE

- Do NOT create a new builtin wiki plugin or new MCP tools (user direction:
  skill over plugin).
- Do NOT enable wiki vectorization (Qdrant) in this task.
- Do NOT move/restructure the wiki content itself (index.md/log.md layout is
  load-bearing for the maintenance hooks).
- Do NOT touch `wiki-maintenance.md` hook behavior — only skills/education.

## Verification gates

- `profiles/omni/skills/wiki.md` (or extended wiki-maintenance.md) exists,
  has frontmatter, and contains ≥1 complete filesystem-tool worked example.
- Live check: a kanban/agent thread can follow the skill end-to-end to read
  index.md → find a page → append a log entry (smoke via omnidev).
- `search_wiki` remains registered in allowed_tools (no regression).
- Wiki content untouched: `git diff` shows only skills/ + docs changes.

## Deliverable

- omni-stack commit(s): skill file + Agent-Guidance-Architecture update (if
  needed). Commit SHAs + evidence in the task thread.
- Honest "not live until image/stack refresh" note if the skill lives in the
  omni profile (bind-mounted → live immediately for omni profiles; verify).
