# Agent Guidance Architecture

How the agent gets its instructions. There are FOUR layers with distinct roles.
Content should live in the layer that matches its role — putting it in the wrong
layer makes prompts bloated and guidance rot.

## The four layers

| Layer | Path | Injected when | Role | Size budget |
|---|---|---|---|---|
| MEMORY | `profiles/<p>/memories/MEMORY.md` | EVERY prompt | Always-know facts: environment, tool capabilities, universal discipline | Keep small (~4-5k chars) |
| Templates | `profiles/<p>/templates/<name>.md` | Only tasks that name the template (kanban task, cron job) | Task-flavor guidance: what a whole class of tasks must do (development, research, maintenance) | Medium, one template per task flavor |
| Skills | `profiles/<p>/skills/<name>.md` | On demand (agent reads the matching skill) | Execution detail: concrete patterns, examples, commands for a specific area | Can be longer, example-heavy |
| Wiki | `profiles/<p>/wiki/**` | On demand (search_wiki) | Long-term knowledge: architecture, invariants, history, detailed references | Can be large; stays focused on important stuff |

## Conventions

1. **Memory = always-know only.** If a fact is only relevant to one task flavor
   (e.g. research output paths, dev commit rules), it does NOT belong in memory —
   it belongs in the task's template. Memory is injected into every prompt, so
   bloating it taxes every task.
2. **Templates are generic, task-flavor-focused — never project-specific.**
   A template covers a FLAVOR of task (development, research, knowledge-pipeline),
   not one project. If a task needs project specifics, they go in the task body or
   a wiki page — not a dedicated template. (Legacy project-specific templates
   `blog-markdown.md`/`build-blog.md` were removed for violating this rule.)
3. **Templates keep the overview; skills carry the how-to.** A template says "use
   paged reads for large files, see the workspace-development skill" — the skill has
   the actual offset/limit examples and compose exec patterns.
4. **Wiki holds the durable detail** that would bloat memory/templates: mount maps,
   platform architecture, compaction mechanics, deployment checklists.
5. **Tool capabilities live in the tool description** (input_schema + description in
   the plugin source), NOT duplicated in guidance files. Guidance files should
   reference capabilities, not restate them — tool descriptions stay in sync with
   code by construction; docs rot.
6. **Keep every layer small enough to be read.** The agent reads memory every turn
   and templates at task start; long files get skimmed and key rules get missed.

## Why this matters (observed failure)

A thread with a hard ~120 tool-call limit was dispatched without budget guidance.
It spent ~600 calls re-reading the same files (compaction had destroyed the earlier
tool results), produced zero commits, and died. The fix was threefold:
- budget discipline in the dev template + memory,
- compaction preserving tool-result excerpts (prompt plugin fix),
- `filesystem_read` gaining offset/limit paging so large files are readable.

All three are documented in their correct layers above.
