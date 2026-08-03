# General Development Workflow

## Context Budget (MANDATORY — read first)
- This thread has a HARD limit of ~120 tool calls. Spending the budget on exploration
  kills the task: threads that burn 100+ calls reading files die mid-implementation with
  ZERO commits (observed repeatedly).
- Spend AT MOST 10 calls on exploration (list/read/search). By call ~20 you must be
  writing or committing.
- READ FILES ONCE: read a file a single time and extract everything you need from it in
  that one call. Do NOT re-read the same file or the same line ranges. Compaction destroys
  earlier tool results, so after a compaction you will NOT remember file contents — that
  is not a reason to re-read; write the facts you need into your working notes or a
  scratch file (outside the repo) as you read.
- LARGE FILES: `filesystem_read` truncates at 50,000 chars and has NO offset/limit
  parameter, so it can only ever show the head of a big file. `filesystem_search` only
  matches FILE NAMES (glob) — it does NOT search file contents. There is no content-grep
  tool. For a large file, read the section you need with `filesystem_read` (accept the
  head truncation) or use `docker_compose exec` with `sed -n 'START,ENDp' path` / `grep -n`
  inside the project's own container to extract exact lines. Never re-read the same file:
  extract the facts you need the first time and write them into your working notes.
- COMMIT PARTIAL WORK: commit after each logical unit (a file written, a test passing).
  A thread can die at any moment; only committed work survives. Do not hold changes for
  a single final commit.
- If you cannot finish in this thread: commit what exists, push it, and report exactly
  what remains. NEVER let the thread die with uncommitted work on disk.

## Before Starting
- Pull the latest code: use the `git_status` tool to check the current state, then `git_clone-repo` (if not cloned yet) or ensure the working tree matches the remote. The repo to work on is usually under `/opt/workspace/<project>`.
- Read the project's `README.md` and `AGENTS.md` files first — they describe the build, run, and test conventions for that repo.
- Check for `.cursorrules`, `CLAUDE.md`, or similar guidance files at the repo root.
- List the existing files with `filesystem_list` to understand the project layout before editing.
- If the project has no local clone yet, clone it with `git_clone-repo` specifying the target directory.

## Understanding the Task
- Read the task body carefully and identify the deliverables.
- Explore the existing codebase structure (`filesystem_list`, `filesystem_read`) to match existing patterns and conventions.
- Use `search_wiki` / `search_messages` if you need prior context about this project or related work.
- Consider edge cases: empty inputs, error conditions, and what happens when services are unavailable.

## Implementation
- Make focused, incremental changes. Do not rewrite unrelated parts of the codebase.
- Follow the repo's existing code style, naming conventions, and directory layout.
- For multi-service projects, use `docker_compose` to build/run services. Services defined in the project's `docker-compose.yml` (e.g. a database, backend, frontend) should be started with `docker compose up -d` and verified with `docker compose ps`.
- Use `filesystem_write` to create/modify files and `filesystem_read` to verify results.
- Commit work frequently with `git_commit-and-push` using a descriptive message.
- Keep secrets out of code: use environment variables / `.env` files for credentials and never hardcode API keys.

### Scratch tooling rules (MANDATORY)
- NEVER commit scratch helper files into the project repo. If you create temporary
  tooling (helper compose files, patch scripts, busybox containers, `toolbox/`
  directories), it is scaffolding — NOT part of the deliverable. Delete it before
  committing, or keep it OUTSIDE the project directory (e.g. `/tmp/`).
- When using `git_commit-and-push`, pass the explicit `files:` parameter listing
  exactly the files that belong in the commit. NEVER do a blanket stage of
  everything (`git add -A` equivalent) — that is how scratch files leak into the repo.
- Before finishing, remove any helper containers you created for the task
  (`docker compose down` for the project's own stack is fine; scratch containers
  like `*-toolbox`, `*-patch` must be `docker rm -f`'d).
- After `git_commit-and-push`, VERIFY the push actually succeeded (the tool's
  response should confirm the remote ref was updated). If the push failed, the
  task is NOT complete — report the failure and do not mark the deliverable done.

## Testing
- Run the project's test suite (whatever the README/AGENTS.md specifies): `docker compose exec <service> <test-command>` or the equivalent.
- Verify each service starts cleanly: check `docker compose ps` for healthy state and inspect logs via `docker compose logs <service>`.
- Test the happy path and at least one error path (e.g. invalid input, missing config, service down).
- For web apps, verify the frontend loads and can reach the backend API.

## Never restart the stack you run inside (MANDATORY)
- You run INSIDE the omniagent container. NEVER issue `docker_compose restart`, `down`, `stop`, `rm`, `kill`, or `up` against the
  omni-stack project (`project_dir` containing `omni-stack`). Restarting your own container kills your thread mid-task.
- The executor blocks such calls automatically; if you see a "Blocked: docker_compose ... targets the omni-stack" error, that is
  working as intended — do NOT try to work around it. Report that a stack restart is needed instead; Hermes performs it.
- You MAY build Rust binaries inside the container (`docker_compose exec` with `cargo build`) and restart OTHER projects.

## Completing the Task
- Commit all changes with a descriptive message (what changed and why), and push to the remote.
- Verify the push landed on the remote (not just a local commit) before reporting success.
- Clean up: remove scratch helper containers/files created during the task.
- Report back with:
  - What was implemented and how it works
  - Service layout (db / backend / frontend) and how to run it
  - How to access/verify the result (URLs, API endpoints, seeded data)
  - Any deviations from the request and why
  - Follow-up items if any
