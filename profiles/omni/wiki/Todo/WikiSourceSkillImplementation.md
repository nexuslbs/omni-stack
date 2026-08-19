# Wiki Data Source + Wiki Skill — Implementation

**Status:** IMPLEMENTED 2026-08-19 (task 13, task_18cd39ea0c185171) —
omni-stack `9c86468` (wiki skill + guidance update) + omni-deployer `adb72f3`
(GROUP 45 integration tests). Verified: executor thread 55, tester thread 56
(PASS, GROUP 45 + GROUP 25 green against fresh HEAD binary in omnidev-toolbox),
reviewer thread 57 (APPROVE).
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

## Delivered (what actually shipped)

1. **New skill `profiles/omni/skills/wiki.md`** (5,691 B, 103 lines, YAML
   frontmatter `name`/`description` so the prompt plugin renders it) —
   Karpathy method (index.md catalog FIRST, log.md append-only log, pages
   under Memory/ Reference/ Todo/), Obsidian format (frontmatter, [[wikilinks]],
   file-per-topic, link-don't-copy), when-to-use table (`search_wiki` text vs
   `filesystem_search` names vs `filesystem_read` of index.md catalog vs
   `search_messages` history vs `search_database` SQL), complete worked
   example "record a new decision" (list tree → read index → dedupe via
   search → filesystem_write → link from index → append log.md → verify via
   search_wiki), documents `vectorize_wiki` OFF (keyword path only), and
   references `wiki-maintenance.md` (loop) / `knowledge-pipeline.md` as
   complementary.
2. **`Reference/Agent-Guidance-Architecture.md` updated** — added convention
   #7: "Check the wiki before asking the user" (search_wiki + read index.md
   first; wiki is a data source, no wiki tool).

## Verification gates (all passed)

- Skill exists with frontmatter + ≥1 complete filesystem-tool worked example.
- Live smoke: filesystem_search (names), search_wiki (text, found
  Container-Mount-Map), filesystem_write append=true to log.md + restored via
  git checkout (wiki content untouched); skills_list-skills shows "wiki"
  enabled:true (bind-mount live immediately); search_wiki still in
  allowed_tools.
- omni-deployer `adb72f3` GROUP 45 (skill artifact + live smoke coverage) +
  pre-existing GROUP 25 — both PASS (RC=0) against a fresh HEAD binary in the
  isolated omnidev-toolbox.
- Push via JWT workaround (git_commit-and-push blocked by broken app-key →
  manual JWT push from omnidev-omniagent container, 451a461..9c86468);
  origin/main == 9c86468 == local HEAD.
