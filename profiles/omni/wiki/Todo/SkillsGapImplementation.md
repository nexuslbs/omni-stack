# Skills Gap: Display Bug + Hermes-Compatible Layout + Prompt Nudge

**Status:** Planned (mirrors kanban task — see board)
**Date:** 2026-08-17
**Scope:** omniagent (skills plugin + prompt plugin) — NO omni-plugins changes (no python skills port exists; skills stays Rust built-in)

## Goal

Close the skills lifecycle loop in omniagent. Verified (2026-08-17, omnistable DB):
the agent **never creates or reads skills** — `skills_create-skill` 0 calls,
`skills_view-skill` 0 calls, `skills_list-skills` 3 calls (old threads 61-63,
before prompt injection existed). Yet 7 hand-written skills exist on disk and
their *descriptions* are injected into every system prompt, and the executor
threads demonstrably follow them (workspace-development.md matches the heavy
docker_compose/git/filesystem usage). The failure is threefold:

1. **Display bug**: `create_skill` writes YAML frontmatter (first line `---`),
   but the prompt plugin's `get_skills()` renders the FIRST LINE as the
   description (strips only a leading `#`). A tool-created skill would appear
   in the agent's prompt as `- <name>: ---` — broken.
2. **Layout drift**: omniagent `create_skill` writes flat `<cat>/<name>.md`
   with thin frontmatter; Hermes conventions (see `hermes-agent-skill-authoring`)
   use `skills/<cat>/<name>/SKILL.md` with rich frontmatter. The prompt
   plugin's reader only handles flat `.md`, so even the Hermes-style layout
   wouldn't be listed.
3. **Prompt nudge insufficient**: the injected line "Available skills (read
   one with view_skill before acting when it matches the task)" never results
   in a view_skill call. The system prompt guidance (added 2026-06-16) tells
   the agent skills exist but gives no concrete trigger for creating one.

## Verified facts (do not re-derive — greps from 2026-08-17)

- Repo: `/opt/workspace/omniagent` (branch main). Skills plugin:
  `plugins/tools/skills/src/main.rs` (765 lines) — tools `create_skill`,
  `list_skills`, `view_skill`, direct filesystem (NOT an HTTP wrapper).
- `create_skill` (main.rs:19-115): validates name (≤64 chars,
  lowercase/digits/-/_), writes `---\nname: <n>\ndescription: "<d>"\nversion:
  0.1.0\nauthor: omniagent\n---\n\n<content>` to
  `<data_dir>/profiles/<profile>/skills/<category>/<name>.md` (profile root =
  what the prompt lists), rejects if exists. No update/patch tool.
- `get_skills` (prompt plugin `plugins/tools/prompt/src/main.rs:1188-1215`):
  reads `{data_dir}/profiles/{profile}/skills/`, for each `.md` file uses
  `file_stem` as name and FIRST LINE as description (strips only `#`). **Bug:
  a frontmatter first line renders as `---`.**
- Existing skills on disk (`/opt/omni/profiles/omni/skills/*.md`): 7 files,
  all hand-written, start with `# Title` (no frontmatter) — why the bug never
  bit. Skills plugin `list_skills`/`view_skill` already handle ALL 3 layouts
  (SKILL.md dir, flat `<cat>/<name>.md`, root-flat `<name>.md`); only the
  PROMPT plugin's reader is limited to flat root `.md`.
- Hermes skill conventions (authoritative): `skills/<cat>/<name>/SKILL.md`;
  frontmatter name/description/version/author/license +
  `metadata.hermes.{tags, related_skills}`; description ≤1024 chars, "Use
  when <trigger>..."; validator enforces name ≤64, desc ≤1024, content
  ≤100k, byte-0 `---`; 8-15k char body target; patch/edit supported.
- Prompt injection point: `main.rs:1342` — "Available skills (read one with
  view_skill before acting when it matches the task):\n{}" (skills joined
  `- name: first_line`). Only shown when `create_skill`/`list_skills` tool
  names present in the tool list (`main.rs:48-50, 77-78`).

## Requirements

1. **Fix the display bug** (`get_skills` in prompt plugin):
   - Parse YAML frontmatter `description:` field when the file starts with
     `---` (reuse the frontmatter extraction pattern from the skills plugin,
     `extract_frontmatter_field` main.rs:284-307); fall back to the first
     `#`-stripped line for hand-written skills. Result: both layouts render a
     real description.
   - Handle the `SKILL.md` dir layout in the reader too: scan
     `<skills_dir>/<category>/<name>/SKILL.md` entries (category dirs), in
     addition to flat root `.md`, so Hermes-style skills are listed.
2. **Align `create_skill` with Hermes layout** (skills plugin):
   - Write to `skills/<category>/<name>/SKILL.md` (dir layout) instead of
     flat `<category>/<name>.md` — or write BOTH if backward compat matters
     (verify: does anything else read the flat path? `get_skills` is the only
     reader; `list_skills`/`view_skill` already support both).
   - Enrich frontmatter: keep name/description/version/author; add `license:
     MIT` and `metadata.hermes: {tags: [...], related_skills: [...]}` (tags
     from an optional `tags` arg, comma-separated). Enforce description ≤1024
     chars with a "Use when ..." convention (warn/error if missing "Use when"
     or too long — mirror Hermes validator constraints; do NOT enforce the
     100k content cap unless trivial).
   - Keep name validation as-is (already matches Hermes ≤64 rule).
3. **Prompt nudge** (prompt plugin `main.rs` ~1342 block + any system prompt
   template text): make skill creation/viewing actionable:
   - Change the available-skills block to include the trigger: "...read with
     view_skill when it matches the task. After solving a non-trivial,
     repeatable task (3+ tool calls, reusable procedure), create a skill with
     create_skill so future threads reuse it."
   - Verify the nudge lands in the actual system prompt for kanban
     executor/tester/reviewer threads (the workflow prompt template — check
     `src/workflows.rs` / template file referenced by workflow_id
     omniagent-dev; the skills block comes from prompt_generate_full).
4. **Verify the loop end-to-end** (omnidev, isolated): create a skill via
   `create_skill`, confirm it appears with a real description in the next
   thread's prompt "Available skills" block, `list_skills` shows it, `view_skill`
   reads it, and (agentic test) an agent actually calls view_skill when the
   skill matches its task.

## Non-goals / DO NOT CHANGE

- Do NOT port skills to python / omni-plugins (no python port exists; skills
  stays Rust built-in for now — revisit only if the user asks).
- Do NOT change the notes plugin (it's healthy and heavily used — 63 calls
  across threads 71-90 as durable working memory).
- Do NOT add skill update/delete tools (create/list/view only, as today).
- Do NOT touch the on-disk hand-written skills (they render fine; only the
  reader/creator change).
- No db-migrations change; no API route changes in core (kanban/schedule
  untouched — this is purely the skills + prompt plugins).

## Verification gates

- `cargo check --workspace --all-targets` clean, `cargo clippy --workspace
  --all-targets -- -D warnings` clean, `cargo test --workspace --release`
  (baseline ~433+ / 0 failed), `cargo fmt --check` clean.
- Unit tests for the new frontmatter-aware description extraction: frontmatter
  file → description from `description:`; `# Title` file → stripped title;
  `SKILL.md` dir layout → listed with name=dir name.
- Grep audit: `get_skills` no longer uses first-line-only; create_skill writes
  SKILL.md layout; no other code reads the old flat path.
- Live check (omnidev): create → prompt lists real description → view_skill
  reads → (agentic) view_skill invoked on match. Screenshot/evidence the
  prompt block.

## Deliverable

Commit + push to origin/main (omniagent only). Report commit SHA, the diff
summary (prompt get_skills frontmatter parsing + SKILL.md dir support,
create_skill layout/frontmatter enrichment, prompt nudge), unit test results,
and live-check evidence (created skill name, its rendered prompt block,
view_skill output). Do NOT claim done until all gates pass.
