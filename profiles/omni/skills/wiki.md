---
name: wiki
description: "Use when you need to look up or record durable knowledge in the profile wiki (index.md catalog, log.md action log, Memory/ facts, Reference/ how-to, Todo/ specs). Teaches the Karpathy method, Obsidian format, and the real filesystem-tool walkthrough (read index first, search pages, write pages, append log). Complements wiki-maintenance.md (the periodic maintenance loop)."
license: MIT
---

# Wiki Data Source (Karpathy method, Obsidian format, filesystem tools)

The wiki is a **data source, not a tool**: there is no wiki MCP tool. You read and
write it with `filesystem_*` tools and search its text with `search_wiki`. The
wiki is where durable knowledge lives — check it BEFORE asking the user something
it may already answer.

## Layout (Karpathy method)

The wiki lives at `profiles/<profile>/wiki/` (this profile:
`/opt/workspace/omni-stack/profiles/omni/wiki/`). It is a durable knowledge layer:

| Path | Role |
|---|---|
| `index.md` | **Catalog of everything.** Read this FIRST: it links every entry under sections (Skills, Memory/, Reference/, Todo/). |
| `log.md` | **Append-only action log.** Entries are `## YYYY-MM-DD (short title)` + bullet lines. Every action you take on the wiki gets logged here; never rewrite history. |
| `Memory/` | Facts (validated, durable). `Memory/Promoted/` holds promoted memories. |
| `Reference/` | How-to / architecture (Agent-Guidance-Architecture, Container-Mount-Map, Budget-and-Context, ...). |
| `Todo/` | Implementation specs (30+). |

Rules: every entry linked from `index.md`; every action logged in `log.md`;
file-per-topic; facts in Memory/, how-to in Reference/, specs in Todo/.

## Obsidian format

- **YAML frontmatter** at the top of each page (`---` delimited): `name`,
  `description` (and optionally `date`, `tags`). The prompt plugin reads the
  `name`/`description` fields and strips the frontmatter from the body.
- **`[[wikilinks]]`** between pages (also plain `[links](./path.md)` work).
- Markdown headings, **file-per-topic** (one topic = one file, don't stuff
  everything into index.md), and **link-don't-copy** (reference an existing page
  instead of duplicating its content).

## When to use what

| Need | Tool |
|---|---|
| Text search across wiki pages (don't know the page name) | `search_wiki` (keyword scan of the ACTIVE profile's wiki) |
| Find pages by FILE NAME (know roughly what it's called) | `filesystem_search` glob, e.g. `**/*.md` under the wiki dir |
| Browse everything that exists / find the canonical entry | `filesystem_read` of `index.md` (the catalog) |
| See the wiki tree (dirs + files) | `filesystem_list` on the wiki dir |
| Create / update a page | `filesystem_write` (overwrites; for big pages use `append=false` first chunk, then `append=true`) |
| Append to `log.md` (or add a line to any big file) | `filesystem_write` with `append=true` — do NOT rewrite the whole file |
| Conversation history, past threads, what was discussed | `search_messages` — **NOT** wiki; `search_messages` never searches wiki pages |
| Counts / aggregations over threads and messages | `search_database` (SQL) — not for wiki content |

## Worked example: record a new decision

Scenario: you made a decision (e.g. "deploy smoke tests run against omnidev, not
omnistable") and must record it in the wiki.

1. **List the wiki tree** to see what exists:
   `filesystem_list` on `profiles/omni/wiki/` → `index.md`, `log.md`,
   `Memory/`, `Reference/`, `Todo/`.
2. **Read the catalog first**: `filesystem_read` on
   `profiles/omni/wiki/index.md` → find the right section (e.g. `Memory/`) and
   existing pages to link to.
3. **Check nothing already covers the topic** (link-don't-copy):
   - `filesystem_search` pattern `*.md` path `profiles/omni/wiki/` → no existing
     file named like the topic;
   - `search_wiki` with the topic keywords → no existing page matches.
4. **Create the page**: `filesystem_write` to
   `profiles/omni/wiki/Memory/Deploy-Smoke-Targets.md` with frontmatter + body:
   ```markdown
   ---
   name: deploy-smoke-targets
   description: "Smoke tests run against omnidev; never against omnistable (production)"
   ---
   # Deploy Smoke Targets
   Smoke tests (deploy.py, kanban groups) run against the omnidev stack.
   Never run them against omnistable — that is the production stack.
   See [[Deployment-Checklist]].
   ```
5. **Link it from the catalog**: `filesystem_write` `append=true` on
   `index.md` (or `filesystem_read` + full rewrite for small edits) — add
   `- [Deploy Smoke Targets](./Memory/Deploy-Smoke-Targets.md): smoke tests run against omnidev, never omnistable` under the `Memory/` section.
6. **Log the action**: `filesystem_write` `append=true` on `log.md`:
   ```markdown
   ## 2026-08-19 (recorded decision: deploy smoke targets)
   - Added Memory/Deploy-Smoke-Targets.md (smoke tests → omnidev only).
   - Linked from index.md.
   ```
7. **Verify**: `search_wiki` with the topic → the new page is findable;
   `filesystem_read` `index.md` shows the new link.

That is the whole loop: **read index → find → write page → link from index →
append to log → verify with search_wiki.**

## Relationship to other skills

- **wiki-maintenance.md** — the periodic maintenance LOOP (thread_finished hook
  every 10 threads): summarizing threads into wiki/templates/skills. This skill
  is the day-to-day METHOD for reading and writing wiki pages.
- **knowledge-pipeline.md** — periodic channel summarization + wiki/skills
  update pipeline.
- Vectorization: `vectorize_wiki` stays OFF (settings.yml) — `search_wiki`
  keyword search is the read path; no Qdrant/API cost for an unused feature.
