# Log

## 2026-08-12

- Added `Todo/HooksImplementation.md` (NEW): the versioned implementation plan for the
  event-driven Hooks system (thread_started / thread_finished / new_message) — hook
  definition fields, counter semantics (default 1, JSON per-scope counters, trigger+reset),
  scope resolution (global / channel by name or all / profile by name or all), both execution
  modes (agentic thread spawn + actions.yml action), infinite-loop protection (hook-caused
  threads/messages never re-trigger), and error isolation (hook failures never affect the
  main agent loop). Mirrors kanban task `task_18cb1c10324f7240` (omniagent-dev workflow,
  thread 74). Updated index.md.

## 2026-08-04

- Added `Todo/WorkflowImplementation.md` (NEW): the versioned implementation plan for the
  role-based kanban workflow (executor/tester/reviewer) — distills the full v6 research
  (`data/research/workflow-role-based-kanban.md`, working-tree only) into schema, status
  machine, fail-task matrix, retry semantics, prompt-plugin concerns, phases 0–7, and the
  integration test matrix. Updated index.md + relevant-index.md.
- Added mandatory verification + review-before-commit requirements after the Python
  prompt plugin shipped without MEMORY/skills (agent never functionally verified):
  - templates/dev-development.md: Testing section now MANDATORY before commit —
    functional end-to-end verification (call actual tools/endpoints, assert output,
    compare against reference/Rust original), add tests or capture evidence. New
    "Review before commit (MANDATORY)" section — re-read diff as reviewer, check exact
    tool names, `$env:VAR` vs `${VAR}`, scratch files.
  - templates/code-improvement.md: same upgrades.
  - skills/workspace-development.md: new "Verifying a plugin/tool deliverable" section
    (exact tool names, /mcp/execute functional calls, reference equivalence, env-ref
    resolution) + `${VAR}`-is-literal pitfall.
  - wiki Reference/Verification-and-Review.md (NEW): the requirements + why + report
    shape. index.md updated.

## 2026-08-03

- Established the 4-layer Agent Guidance Architecture (memory → templates → skills →
  wiki) and documented it in:
  - wiki Reference/Agent-Guidance-Architecture.md (the model, conventions, why it matters)
  - AGENTS.md (Agent Guidance Architecture section)
- Reworked guidance content to match the model:
  - MEMORY.md: now always-know only (filesystem access, tool capabilities, mount map,
    universal discipline). Removed task-shaped budget numbers and the research workflow
    (they moved to the dev/research templates). Fixed stale claim: filesystem_read now
    HAS offset/limit paging.
  - templates/dev-development.md: dev-flavor budget rules + large-file paging guidance.
  - templates/research.md (NEW): research-flavor workflow (batch fetches, notes-first,
    output quality + path) — research exploration is by-design heavy, so its budget
    rules differ from dev.
  - skills/workspace-development.md: concrete paging/grep examples, fixed stale
    filesystem_read claim.
- Corrected wiki Reference/Container-Mount-Map.md: the mount map is omni-stack →
  /opt/omni and /opt/workspace → /opt/workspace (old docs said /opt/data / omni-workspace).
- Added wiki Reference/Budget-and-Context.md: thread budget, compaction mechanics
  (tool-result excerpts), prompt context blocks, filesystem_read paging.
- Updated index.md and relevant-index.md.

## 2026-06-27

- Created wiki pages documenting:
  - Deployment Checklist: correct procedure for deploying compose services
  - Container Mount Map: volume mount mappings and their implications
- Updated AGENTS.md with:
  - Tool capability reference table
  - Docker & Deployment Pitfalls section (5 pitfalls)
- Updated MEMORY.md with:
  - No shell tool warning
  - Container volume mount map
  - Port checking limitation

