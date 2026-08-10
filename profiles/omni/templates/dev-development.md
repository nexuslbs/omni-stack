# General Development Workflow

## Context Budget (MANDATORY — read first)
- This thread has a HARD limit of ~120 tool calls. Spending the budget on exploration
  kills the task: threads that burn 100+ calls reading files die mid-implementation with
  ZERO commits (observed repeatedly).
- Spend AT MOST 10 calls on exploration (list/read/search). By call ~20 you must be
  writing or committing.
- READ FILES ONCE: read a file a single time and extract everything you need from it in
  that one call. Do NOT re-read the same file or the same line ranges. Compaction keeps
  only a short excerpt of tool results, so after a compaction you will NOT remember full
  file contents — that is not a reason to re-read; write the facts you need into your
  working notes or a scratch file (outside the repo) as you read.
- LARGE FILES: use `filesystem_read` with offset/limit paging (read ONCE, page forward
  through the file, extract what you need into your working notes as you go). Do NOT read
  a big file "whole" — you can only ever see a slice, and re-reading the same slice
  teaches you nothing. Do NOT use `docker_compose exec ... sed -n 'A,Bp'` / `grep -n`
  to read file contents: `filesystem_read` is the ONLY file-reading tool and costs ONE
  call per page. `docker_compose` is for RUNNING commands/builds, never for reading
  files. If you find yourself re-reading overlapping line ranges of the same file, STOP —
  that is the #1 budget killer (threads have died at 120/120 after 100+ sed windows with
  zero commits). Write the facts into your working notes (`prompt_note-write`) after the
  FIRST read; consult notes, never the disk again.
  See skill `workspace-development` for the exact patterns.
- COMMIT PARTIAL WORK: commit after each logical unit (a file written, a test passing).
  A thread can die at any moment; only committed work survives. Do not hold changes for
  a single final commit.
- If you cannot finish in this thread: commit what exists, push it, and report exactly
  what remains. NEVER let the thread die with uncommitted work on disk.

## Trust the Task Body — PRE-VERIFIED FACTS are authoritative (MANDATORY — read first)
- Task bodies are written by an orchestrator that has ALREADY done the exploration. When a
  body embeds facts — file paths, line numbers, code snippets, exact commands, root causes —
  those facts are PRE-VERIFIED ground truth. Your job is to USE them, not re-derive them.
- **Do not re-read a file (or a line range) whose relevant content is already quoted in the
  task body.** Opening a file to "confirm" what the body already states costs a tool call
  and teaches you nothing. Trust the body; verify only what the body tells you to verify.
- **If the body gives you the change and the location, EDIT FIRST.** Open the target file
  once, make the edit, then read back ONLY the edited region (a few lines) to confirm it
  applied. Do not page through the whole file first.
- **Your plan should be: edit → test → commit.** A plan that lists "read files to confirm
  line content" is a plan to waste the budget. The first N tool calls should be EDITS.
- When the body says a build/test/verification "already passed" or "is not needed here",
  trust it — do not rerun it "to be sure". The orchestrator recorded the state so you can
  finish in a handful of calls instead of re-earning it.

## Long-Running Commands & Waiting (MANDATORY — read before running any build/test)

- **A long-running command (build, test suite, server start, git push) costs ONE tool call if
  you wait properly — or 20+ if you poll.** Poll-spinning (repeatedly calling
  `filesystem_info`/`filesystem_search`/`docker_compose ps` to check "is it done yet?") burns
  your entire iteration budget on a single command and the thread dies with zero commits
  (observed repeatedly: threads died at the iteration limit mid-`cargo build` after 100+ poll
  calls).
- **When a tool call returns `status: processing` with a `task_id`, ALWAYS block on
  `builtin_wait-task` immediately** — do NOT poll with other tools. Use a GENEROUS timeout
  matching the operation: `builtin_wait-task(task_id=<id>, timeout_secs=900, tail=2000)` for a
  dev-stack setup (5-15 min), `timeout_secs=900` for a Rust build. There is NO hard cap —
  the wait returns as soon as the task finishes (it polls internally every 500ms). If it
  returns `status: timeout`, call it AGAIN — each wait is still just ONE call.
- **Never guess a small timeout** (e.g. 5-15s) for a build — a Rust `cargo build --release`
  takes 1-10+ minutes, a full `omnidev.py setup` takes 10-15 min. Use 900-1800s from the
  start. Waiting 15 min costs 1 iteration; checking every 15s for 15 min costs 60.
- **`docker_compose` LONG COMMANDS: NEVER pass the `timeout` parameter.** `docker_compose`
  automatically switches to background after a few seconds and returns
  `{"status":"processing","task_id":...}`. It has NO default timeout — the command runs until
  it finishes, errors, or you cancel it. If you pass `timeout: 300`, the command is KILLED at
  300s (observed: a setup killed at 300s left the stack half-up; a cargo build killed at 300s
  forced a full re-run). To wait: `builtin_wait-task(task_id=<id>, timeout_secs=300, tail=2000)`
  and repeat if it times out. Do NOT combine `timeout` with wait-task — `timeout` on the tool
  call kills the command; wait-task just waits.
- **While a build runs, do NOT do other work in parallel by polling** — the per-channel
  executor is serial; your thread is the only one running. Just wait.
- **If a command genuinely hangs past 2-3 wait cycles (10-15 min), THEN investigate** (logs,
  process list) — not before. A Rust release build legitimately takes that long.

## Before Starting — ORIENT FIRST (MANDATORY, 2-4 calls max)

**This task may be a CONTINUATION of previous threads that died mid-work (interrupted /
iteration-limit). The kanban task stays the same across attempts; each new thread starts with
fresh context. DO NOT assume you are starting from zero — and DO NOT redo work a previous thread
already did. Establish state cheaply, then act:**

1. **Check the tracking file FIRST if this task references one** (e.g. the task body says
   `/opt/omni/data/tasks/<name>.md`): `filesystem_read` it. It is the resume ledger — previous
   threads write what they did, what worked, errors, and what remains. If it exists, your job is
   usually "finish the listed remaining steps", not re-implement.
2. **Check git state of every repo the task touches** (`git_status` / `git diff --stat` /
   `git log --oneline -5`): uncommitted changes on disk = a previous thread's work that survived;
   recent commits with the task's topic = previous thread's committed work. Map what's already
   done BEFORE writing any code.
3. **Check prior threads of THIS task** (if you have a threads API/tool): read the last thread's
   summary/status. A thread that reached `completed`/`review` means the work was done — your job
   is verification/commit, not re-implementation. A thread that was `interrupted`/`skipped` means
   it died mid-way — resume from its last recorded state.
4. **Check prior threads of OTHER tasks on THIS CHANNEL that touched the same repos/files**
   (the channel is serial — earlier tasks on the same channel often solved the exact problem you
   are about to investigate). Query the channel's recent thread messages (`query_database` on
   `threads`/`messages`, or search_messages) and read the FINAL messages / status reports of the
   last 1-3 relevant threads. Harvest their verified facts: canonical build commands, error
   signatures, root causes, workarounds. **If a prior thread already documented an investigation
   result (e.g. "build fails with 17 sqlx no-cached-data errors; fix = regenerate .sqlx via
   prepare.py"), TRUST it and continue from there — do NOT re-run that investigation.** Re-deriving
   what a previous thread already established is the #1 budget killer (observed: threads 88-90 each
   burned ~117 tool calls re-investigating the same sqlx cache problem).
5. **Then decide:**
   - Uncommitted work exists + looks coherent → review the diff, fix if broken, COMMIT + PUSH it
     (this is the #1 most common missing step — previous threads die right before committing).
   - Work is committed but task not marked done → verify the commit matches the task, then report.
   - Nothing exists → implement fresh.

**Never redo verified work.** If the tracking file or a prior thread says a build/test passed,
do not rebuild from scratch "to be sure" — trust the recorded verification, or at most re-run the
cheapest check. The whole point of the tracking file is that a successor thread can finish in a
handful of calls instead of re-earning the state.

## Before Starting
- Pull the latest code: use the `git_status` tool to check the current state, then `git_clone-repo` (if not cloned yet) or ensure the working tree matches the remote. The repo to work on is usually under `/opt/workspace/<project>`.
- Read the project's `README.md` and `AGENTS.md` files first — they describe the build, run, and test conventions for that repo.
- Check for `.cursorrules`, `CLAUDE.md`, or similar guidance files at the repo root.
- List the existing files with `filesystem_list` to understand the project layout before editing (ONCE).
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
  response should confirm the remote ref was updated; local == origin/main). If the
  push failed, the task is NOT complete — report the failure and do not mark the
  deliverable done.

## Testing (MANDATORY — before you commit)
- Run the project's test suite (whatever the README/AGENTS.md specifies): `docker compose exec <service> <test-command>` or the equivalent.
- Verify each service starts cleanly: check `docker compose ps` for healthy state and inspect logs via `docker compose logs <service>`.
- Test the happy path and at least one error path (e.g. invalid input, missing config, service down).
- For web apps, verify the frontend loads and can reach the backend API.
- If the deliverable is a plugin/tool/service (MCP server, HTTP API, library), FUNCTIONALLY
  verify it end-to-end: install/start it, CALL its actual tools/endpoints with real
  arguments, and assert the output matches the expected behavior — do not rely on
  "it compiles" or "the test suite passed" as proof the deliverable works. Compare
  against the reference implementation it replaces (e.g. a Python rewrite must produce
  the same output as the Rust original on the same input).
- If the codebase has a test harness, ADD tests for the new behavior (happy path + at
  least one edge/error case). If it has no harness, capture verification evidence
  (tool-call transcripts, API responses) in your final report instead.
- Write the verification results into your report: WHAT you called, WHAT you passed in,
  WHAT came back, and how it compares to expected/reference output.

## omniagent is a SEPARATE PROJECT — NEVER touch the live stack (MANDATORY)

- **You develop omniagent (and omni-dashboard, omni-stack) like ANY OTHER external project.**
  The live omnistable stack is a DEPLOYED product running image-fixed binaries. Your code changes
  do NOT exist there and you MUST NOT make them exist there. They go live ONLY when a new CI image
  is built and published from `main` — never before.

## Building omniagent code from an omnistable-dispatched task (MANDATORY)

If THIS task is running under the omnistable stack (you are inside the
`omnistable-omniagent-1` container / stable-channel) and the task asks you to
implement omniagent (or omni-dashboard / omni-stack) code, you build and
verify it via the DEV stack — the omnistable container has NO source mount
and NO build toolchain:

1. **Bring up omnidev FIRST if it is not running** — you (inside
   `omnistable-omniagent-1`) have `docker.sock`, `python3`, `git`, and
   `/opt/workspace` mounted, so you CAN start the dev stack yourself. Check
   first (pass the env file so the compose project resolves to `omnidev`):
   `docker_compose(project_dir="/opt/workspace/omni-stack", env_file="/opt/workspace/omni-deployer/omnidev.env", command="ps")`
   — if no containers are listed, bring omnidev up by running the dev setup
   INSIDE your own container (this is safe — it creates the OMNIDEV project;
   it does NOT touch omnistable). CRITICAL: pass `omnistable.env` here so the
   exec targets YOUR project (omnistable), NOT the default `omni` project:
   `docker_compose(project_dir="/opt/workspace/omni-stack", env_file="/opt/workspace/omni-deployer/omnistable.env", command="exec", service="omniagent", args="python3 /opt/workspace/omni-deployer/omnidev.py setup")`
   - NOTE: do NOT try `command="up -d"` directly against the omni-stack dir —
     the executor blocks `up`/`restart`/`down`/`stop`/`rm`/`kill` on any
     project_dir containing `omni-stack` (self-restart guard: you run inside
     that stack). `exec` is NOT blocked, so the omnidev.py path above is the
     supported way. If you see a "Blocked: docker_compose ... targets the
     omni-stack" error, that is working as intended — use the exec path.
   - omnidev and omnistable run side-by-side — starting omnidev does NOT stop
     omnistable, and vice versa. The docker plugin accepts compose/env files
     anywhere inside `/opt/workspace`, not only inside `project_dir`.
2. **Implement the code in the omniagent repo in the workspace**:
   `/opt/workspace/omniagent` (mounted at `/app` inside the omnidev omniagent
   container).
3. **Build it in the omnidev omniagent container** (`omnidev-omniagent-1`).
   Use `docker_compose` exec with the OMNIDEV env file so the project
   resolves to `omnidev`:
   `docker_compose(project_dir="/opt/workspace/omni-stack", env_file="/opt/workspace/omni-deployer/omnidev.env", command="exec", service="omniagent", args="bash -c 'cd /app && cargo build --release -p omniagent'")`
   (add `&& cargo clippy -p omniagent -- -D warnings && cargo test -p omniagent --lib` to run the full gate).
   This is a LONG command (a Rust release build takes 1-10+ min) — the tool
   call will return `{"status":"processing","task_id":...}` after a few
   seconds; ALWAYS follow with `builtin_wait-task(task_id=<id>,
   timeout_secs=900, tail=2000)` and repeat only if it returns `status:
   timeout`. Do NOT poll with other tools.
   The omnidev dev overlay already sets `SQLX_OFFLINE: "false"`, so
   `sql_forge!` macros are verified against the LIVE dev database at compile
   time — do not set `SQLX_OFFLINE=true` to bypass.
4. NEVER run the migrator or builds against the live omnistable DB/stack.
   Your changes reach omnistable only via the next CI build from `main`.

- **NEVER run `db-migrations` against the live database** (omnistable-postgres-1, db `omniagent`)
  — or ANY database that is not a throwaway local/test DB you created yourself for this task.
  Applying schema to the live stack is a PRODUCTION CHANGE, not a dev step. The error that caused
  this rule: an agent ran the migrator against the live omnistable DB and polluted the prod schema
  with unreleased columns. The migrator crate exists so CI/deploy applies migrations at release
  time — the AGENT never applies them to live.
- **NEVER write to the live stack's state** — no API PATCH/POST against the running omniagent's
  kanban/threads/plugins endpoints to "test" your change (the running binary is OLD code; your
  change is not there, so such tests prove nothing and mutate prod state). No edits to
  `/opt/omni/**` runtime data that is not a git repo. No container restarts, no `docker compose`
  against the omni-stack project, no killing processes.
- **The dev loop is: edit source → add/run INTERNAL RUST TESTS (unit tests in the crate) → build →
  clippy → fmt → commit → push to origin/main.** Internal Rust tests are the verification vehicle —
  write tests that exercise the new behavior in-process (mock DB/state where needed). Do NOT
  "functionally verify" against the live stack.
- If you genuinely need a database to test against, create a THROWAWAY local postgres (e.g. a
  scratch compose service or `docker run` on a non-live port) and run `db-migrations` against
  THAT — never the live one.
- **Databases: NEVER use the live omnistable DB — spin your OWN temporary local
  postgres.** The live omnistable stack (image, binary, DB) is FROZEN — no
  migrations, no schema changes, no builds against it, no pointing tests at it.
  Only bundled and remote *plugins* can change live. Your code goes live ONLY via
  the next CI build. So: create a THROWAWAY local postgres (scratch compose
  service or `docker run` on a non-live port — e.g. the `phase5-db` pattern),
  run `db-migrations` against THAT, and point `DATABASE_URL` at it.
- **Development uses a LIVE database — NOT `SQLX_OFFLINE`.** `SQLX_OFFLINE=true`
  is for CI and hybrid builds (the Dockerfile sets it); the dev overlay
  (`docker-compose.dev.yml`) already sets `SQLX_OFFLINE: "false"` so `cargo build`
  validates queries against your live temp DB at compile time. When you change a
  query, build/test against your temp DB — sqlx will validate it live and you do
  NOT need to regenerate the `.sqlx` cache yourself during development. CI
  regenerates the cache (`cargo sqlx prepare --workspace` against a scratch DB)
  as part of its own build; if you must regenerate it (e.g. to prove CI will
  pass), run `prepare.py` under /opt/workspace/rustbuild with DATABASE_URL
  pointing at YOUR throwaway DB — never the live one.
- **If a query fails at compile time with a missing table/column, your temp DB
  schema is stale — re-run `db-migrations` against it, or the query is wrong.**
  Do NOT reach for `SQLX_OFFLINE=true` to bypass the error; that hides real
  problems and is not how dev is configured.
- If the live DB lacks columns your code references, that is EXPECTED and CORRECT — the columns
  arrive with the release that carries your code. Do not "fix" the live schema. Do not edit around
  the missing columns in a way that diverges from the spec — write the code per spec and let the
  release pipeline apply the schema.

## Never restart the stack you run inside (MANDATORY)
- You run INSIDE the omniagent container. NEVER issue `docker_compose restart`, `down`, `stop`, `rm`, `kill`, or `up` against the
  omni-stack project (`project_dir` containing `omni-stack`). Restarting your own container kills your thread mid-task.
- The executor blocks such calls automatically; if you see a "Blocked: docker_compose ... targets the omni-stack" error, that is
  working as intended — do NOT try to work around it. Report that a stack restart is needed instead; Hermes performs it.
- You MAY build Rust binaries inside the container (`docker_compose exec` with `cargo build`) and restart OTHER projects.

## Review before commit (MANDATORY)
- Before `git_commit-and-push`, RE-READ your own diff as a reviewer, not as the author:
  `git_status` / `git diff` (or `docker_compose exec` + `git diff --stat` + `git diff`).
  Check for: missing files, renamed tool names (the executor calls exact names like
  `prompt_generate` — a mismatch silently breaks the feature), wrong env refs
  (`${VAR}` is a literal; use `$env:VAR`), scratch files leaking in, dead code.
- Verify the exact deliverables the task named: every file it asked for exists, every
  tool/endpoint it asked to implement is present with the EXACT expected name/schema.
- If you cannot verify (no runtime available, sandbox blocks the call), say so in the
  final report and flag the task for review — do NOT mark it done silently.

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

## LEARN (MANDATORY — the loop only works if you write back)
- Before finishing (success OR interruption), promote at least ONE durable lesson/fact you learned this thread via `memory_promote-to-memory` (e.g. build commands, file anchors, root causes, what NOT to do). This is how future threads avoid repeating your work — 6 threads already died re-deriving the same harness knowledge because no one wrote it down.
- If you have nothing durable, still write one line: what you attempted and the blocker.
- Promoted memories are injected into EVERY future prompt under '=== Learned Knowledge ===' — the loop is closed only when you write back.

## Where to find deeper guidance
- Tool execution details: skill `workspace-development`, `docker-compose-usage`, `git-workflow`.
- Environment facts (mounts, port checking, compaction behavior): wiki `Reference/*` pages + MEMORY.
- Repo-specific conventions: the repo's own README/AGENTS.md.
