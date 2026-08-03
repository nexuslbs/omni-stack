# Code Improvement Workflow

This is a legacy flavor template for code-refactor / bug-fix tasks. It is a lighter
variant of `dev-development.md` — prefer that template for new tasks unless the task
is specifically a focused code improvement.

## Context Budget (MANDATORY — read first)
- This thread has a HARD limit of ~120 tool calls. Read files ONCE and take notes;
  compaction keeps only a short excerpt of tool results. Commit partial work as you go;
  never let the thread die with uncommitted work on disk. For large files use
  `filesystem_read` offset/limit paging or `compose exec` + `sed -n` / `grep -n`.
- Deeper guidance: skill `workspace-development` (patterns) and template
  `dev-development.md` (full dev workflow).

## Before Starting
- Pull latest code from the repository
- Read the project's README.md and AGENTS.md files for context
- Review the existing codebase to understand patterns and conventions
- Check if there's a .cursorrules or CLAUDE.md for coding guidelines

## Understanding the Task
- Research what is being asked thoroughly
- Identify the best approach by analyzing the existing code structure
- Consider edge cases and potential regressions before making changes

## Implementation
- Make minimal, focused changes that address the specific requirement
- Follow the project's existing code style and patterns
- Add clear comments for complex logic
- Ensure the changes compile without errors
- Stage changes locally with `git add` for the modified files (explicit files only)

## Testing
- Run the full test suite: `cargo test` or equivalent
- If implementing a new feature, add tests that cover:
  - Happy path (normal operation)
  - Edge cases (empty input, boundary values)
  - Error conditions
- If fixing a bug, add a test that:
  - Reproduces the bug with the old code (shows it failing)
  - Passes with the fix applied

## Completing the Task
- Commit changes with a descriptive message explaining what and why
- Push changes to the remote; VERIFY the push landed (local == origin/main)
- Summarize what was done, including:
  - What was changed and why
  - Any design decisions made
  - Test results
  - Follow-up items if any
