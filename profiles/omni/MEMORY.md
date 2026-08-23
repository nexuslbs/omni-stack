ALWAYS-KNOW RULES (apply to every task, no matter the type):
- READ FILES ONCE: extract what you need in a single read and write the facts into your
  working notes. Compaction preserves only a short excerpt of tool results (~800 chars
  per tool, capped), so beyond that you must rely on your own notes — never on re-reads.
- COMMIT PARTIAL WORK: a thread can die at any moment (this deployment has a hard
  ~120 tool-call budget). Only committed/pushed work survives. Commit after each logical
  unit; never let a thread die with uncommitted work on disk.
- VERIFY: after `git_commit-and-push`, confirm the remote ref updated (local ==
  origin/main). After any change, run the tests. Self-reports are not verification.
- If you cannot finish: commit what exists, push it, and report exactly what remains.

§

TOKEN EFFICIENCY (spend tokens on thinking and doing, not on re-doing):
The goal is to avoid UNNECESSARY token usage — NOT to minimize total usage. Complex
tasks legitimately burn many tokens (long builds, many files, many iterations); that
is normal and expected. What is never justified is spending tokens on work that
duplicates what you (or a supervisor) already have. Guiding principle: every token
should move the task forward, once.

- NEVER self-monitor what a supervisor already monitors. If an external controller
  (e.g. Hermes) tracks your token budget / thread progress, DO NOT query token_usage,
  threads token columns, or equivalent yourself — each such query is pure waste and
  duplicates the supervisor's job. Spend those calls on the task. (Observed 2026-08-22:
  an executor burned ~16K miss on repeated token_usage queries and still breached the
  cap; the fix was to forbid them entirely.)
- LONG COMMANDS: run them as ONE background command writing to a log file, then wait
  with a single generous `builtin_wait-task(timeout_secs=900-1800)`. NEVER poll with
  short sleeps, NEVER pass a tight timeout on docker_compose. Each poll round-trip
  re-sends the whole context.
- READ OUTPUT ONCE: after a long command finishes, read its log exactly once — combine
  the checks you need into one call (`grep -c <marker>` + `tail -60` in the same
  command). NEVER re-read or re-grep the same output repeatedly. (Observed: repeated
  docker_compose output reads cost ~97K miss and were the main cap-breach driver.)
- READ FILES ONCE (see above): page deterministically, extract facts into notes, never
  re-read the same file/range in one thread.
- BATCH independent checks: combine several small queries/commands into a single call
  instead of issuing one call per micro-step.
- BOUND EXPLORATION: before committing to an approach, do a bounded discovery pass
  (≤10 exploration calls); then execute. Re-exploring the same question is waste.

NOTES, SUBTASKS, PLANS ARE NOT WASTE — they are the anti-hallucination machinery:
- Working notes (notes tool / auto-notes) exist precisely because compaction truncates
  tool results. Writing facts once is far cheaper than re-reading to recover them, and
  notes are what prevent you from repeating or contradicting yourself. Use them.
- Subtasks / task breakdown are for FOCUS and STATE, not token theater: they keep a
  long task's remaining steps visible (so you don't re-derive or lose track after a
  wait-task), and they structure complex work into verifiable units. Use them when the
  task is multi-step; skip them only when they'd add calls without adding structure.
- Planning modes (plan) help you pick the best approach before spending execution
  tokens — a wrong approach costs far more than the plan that avoids it.

IN SUMMARY: token budget is about eliminating WASTE (duplicate reads, self-monitoring,
polling, unbounded exploration), while freely spending on necessary complexity,
notes, subtasks, and planning — those are what keep a long task correct and focused.

§

FILESYSTEM ACCESS:
- Reads, lists, searches, and metadata lookups (filesystem_read/list/search/info) are
  UNRESTRICTED — any path on the filesystem.
- WRITES (filesystem_write) are confined to /opt/workspace/ and subdirectories.
- data_dir (/opt/omni) holds agent config, profiles, wiki, memories — read freely; write
  wiki/skills/memories there only via their dedicated tools or allowed paths.
- For project files, write to paths under /opt/workspace/.
- Do NOT try to access paths under /app/ (that's source; use /opt/workspace/omniagent or
  the repo's compose instead).
- For wiki writes, use paths under data_dir/profiles/<profile>/wiki/.
- For research reports, write to /opt/workspace/data/research/<category>/ — the ONLY
  writable location (filesystem_write is sandboxed to /opt/workspace; /opt/omni is
  read-only for the agent).

§

LARGE FILE CAPABILITIES (what you CAN do):
- filesystem_read supports char-based paging: `offset` (default 0) + `limit` (default
  50000). The response reports total size and which slice was returned, e.g.
  "[showing chars 50000-80000 of 80000 total chars]". Page deterministically:
  offset=50000, then offset=100000, ... until the note no longer says "truncated".
- filesystem_search matches FILE NAMES only (glob) — it does NOT search file contents.
- For exact lines / content grep in a big file, use `docker_compose exec <service>` with
  `sed -n 'A,Bp'` or `grep -n` inside the project's own container.
- Never re-read the same file or the same line range twice in one thread.

§

DOCKER CODE EXECUTION:
- The `docker_compose` tool (the compose MCP tool is registered as `docker_compose`
  — the bare name `compose` does NOT exist) supports: ps, up, down, logs, build,
  exec, stop, restart, pull.
- TOOLBOX PATTERN: if tools aren't in the agent container, create a docker-compose.yml
  with a 'toolbox' service in the workspace, build it, then `docker_compose exec toolbox <cmd>`.
- EXISTING PROJECTS: if the workspace already has docker-compose.yml, use
  `docker_compose exec <service> <cmd>`. Prefer this over installing in the agent container.

§

NO SHELL TOOL AVAILABLE:
- You have NO shell/terminal tool. You can ONLY use registered MCP tools.
- Docker operations: `docker_compose` MCP tool. File operations: filesystem_* tools.
- HTTP: `fetch_fetch`. DB: `search_database`.

§

CONTAINER VOLUME MOUNT MAP (verify with `docker inspect` if unsure):
/opt/workspace (host) → /opt/workspace (container) ← project files live here
/opt/workspace/omni-stack (host) → /opt/omni (container) ← data_dir: config, profiles, wiki, skills, memories, templates
/opt/workspace/omniagent (host) → /app (container) ← source code, target/release binaries

CRITICAL: filesystem paths inside the container map directly to host paths:
- /opt/workspace/<project> on the container IS /opt/workspace/<project> on the host
  (same path, no translation) — `docker_compose(project_dir="/opt/workspace/<project>/...")` works as-is.
- /opt/omni/... on the container IS /opt/workspace/omni-stack/... on the host.
- /app/... on the container IS /opt/workspace/omniagent/... on the host.
When deploying via `docker_compose`, use the container path; when checking host files, translate
via this map.

§

PORT CHECKING LIMITATION:
- fetch_fetch("http://localhost:PORT/") only checks ports inside THIS container's network.
  A container can have 0.0.0.0:PORT->container_port on the HOST but be unreachable here.
- ALWAYS use `docker_compose(ps)` on the compose project to check port mappings instead.

§

CONTEXT RETRIEVAL:
- Before executing, use search_messages / search_wiki when past context likely exists
  (prior research, decisions, conventions). Do not assume you have all context just from
  the current message. Existing session data can save re-doing work.
