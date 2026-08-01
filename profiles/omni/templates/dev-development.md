# General Development Workflow

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
