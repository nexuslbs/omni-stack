# Verification & Review Requirements

Why this page exists: a dispatched dev agent shipped a Python prompt plugin whose
generated prompt was MISSING the MEMORY section and skills list (empty `memory`/`soul`
returned by the plugin). The agent never noticed because nothing forced it to
functionally verify the deliverable — the code compiled, the process started, and the
task body said "Hermes will verify". The fix was threefold: task bodies must require
self-verification, templates mandate functional testing + review-before-commit, and
this page documents the concrete checks.

## When this applies

ANY task whose deliverable is code that runs: plugins (MCP servers), tools, services,
APIs, agents. "It compiles" / "tests pass" / "process started" are NOT sufficient.

## Mandatory checks before commit

1. **Exact names.** The caller invokes tools by EXACT name (e.g. executor calls
   `prompt_generate`, `promote_to_memory`, `generate_summary`). A renamed or mismatched
   tool silently breaks the feature. List registered tools, compare against the names
   the executor/API expects.
2. **Functional call.** Install/start the deliverable, then CALL each tool/endpoint with
   real arguments and assert the output. For omniagent MCP tools:
   `POST /api/mcp/execute` with `{"name": "<tool>", "arguments": {...}, "meta": {"profile_name": "omni"}}`
   (stateless execution — see src/server/mod.rs `execute_mcp_tool_handler`).
3. **Reference equivalence.** A rewrite (e.g. Python replacing Rust) must produce the
   SAME output on the same input. Diff outputs; check sections, ordering, fallbacks,
   byte-level where feasible.
4. **Env resolution.** mcp-config.json env values MUST use `$env:VAR` / `$secret:NAME`.
   `${VAR}` is NEVER interpolated by the framework — the subprocess receives the literal
   string `${VAR}`. Symptom of a wrong ref: empty sections in output (missing
   MEMORY/skills), NOT a startup error. Check `cat /proc/<pid>/environ` of the spawned
   process to confirm resolved values.
5. **Self-review the diff.** Before `git_commit-and-push`, re-read `git diff` as a
   reviewer: missing files, renamed identifiers, scratch files, dead code, secrets.

## What the agent must report

- WHAT it called (tool/endpoint), WHAT arguments, WHAT came back
- How the output compares to expected / reference implementation
- Test results, or explicit statement that no runtime verification was possible
  (in which case the task must be flagged for human/Hermes review — not marked done)

## References

- templates/dev-development.md — Testing (MANDATORY) + Review before commit (MANDATORY)
- templates/code-improvement.md — same
- skills/workspace-development.md — "Verifying a plugin/tool deliverable"
- Wiki: Container-Mount-Map.md, Budget-and-Context.md
