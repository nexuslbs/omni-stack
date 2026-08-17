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
