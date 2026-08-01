FILESYSTEM ACCESS:
- Reads, lists, searches, and metadata lookups (filesystem_read/list/search/info) are UNRESTRICTED — any path on the filesystem.
- WRITES (filesystem_write) are confined to /opt/workspace/ and subdirectories.
- data_dir (/opt/omni) holds agent config, profiles, wiki, memories — read freely, write wiki/skills/memories there only via their dedicated tools or allowed paths.
- For project files, write to paths under /opt/workspace/.
- Do NOT try to access paths under /app/ (that's source; use /opt/workspace/omniagent or the repo's compose instead).
- For wiki writes, use paths under data_dir/profiles/<profile>/wiki/.
- For research reports, use <data_dir>/data/research/<category>/.

§

RESEARCH WORKFLOW (skip if the task is not research):
1. If the prompt already contains the question, use it directly: no separate file needed.
2. ALWAYS search_messages first for past context; search_wiki for existing knowledge.
3. Fetch ALL external data in ONE batch. Do NOT fetch one URL at a time.
4. COMPLETE in 2-4 tool-calling rounds max. More than 6 means you failed.
5. OUTPUT QUALITY: Clear headers, comparison tables, cited sources. Verify by re-reading.
6. Skip Critical-Instructions.md and Anti-Patterns.md: not needed for research.
7. OUTPUT PATH: Write to <data_dir>/data/research/<category>/.
   If the prompt specifies a filename, use it. Otherwise, the agent defines one.
   Category reflects topic domain (e.g. 'agents', 'deployment', 'security').

§

DOCKER CODE EXECUTION:
You can execute code, run builds, install packages in Docker. The `compose` tool supports: ps, up, down, logs, build, exec, stop, restart, pull.
TOOLBOX PATTERN: If tools aren't in the agent container, create a docker-compose.yml with a 'toolbox' service in the workspace, build it, then `compose exec toolbox <cmd>`. This keeps side-effects isolated.
EXISTING PROJECTS: If the workspace already has docker-compose.yml, use `compose exec <service> <cmd>`. Prefer this over installing in the agent container.

§

NO SHELL TOOL AVAILABLE:
- You have NO shell/terminal tool. You can ONLY use registered MCP tools.
- For Docker operations: use `compose` MCP tool (supports: up, down, ps, logs, build, restart, stop, exec, pull).
- For file operations: use filesystem_read/write/list/info/search.
- For HTTP: use fetch.
- For DB: use query_database.

§

CONTAINER VOLUME MOUNT MAP (verify with `docker inspect` if unsure):
/opt/workspace (host) → /opt/workspace (container) ← project files live here
/opt/workspace/omni-stack (host) → /opt/omni (container) ← data_dir: config, profiles, wiki, skills, memories
/opt/workspace/omniagent (host) → /app (container) ← source code, target/release binaries

CRITICAL: filesystem paths inside the container map directly to host paths:
- /opt/workspace/<project> on the container IS /opt/workspace/<project> on the host
  (same path, no translation) — `compose(project_dir="/opt/workspace/<project>/...")` works as-is.
- /opt/omni/... on the container IS /opt/workspace/omni-stack/... on the host.
- /app/... on the container IS /opt/workspace/omniagent/... on the host.
When deploying via `compose`, use the container path; when checking host files, translate
via this map.

§

PORT CHECKING LIMITATION:
fetch("http://localhost:PORT/") only checks ports inside THIS container's network.
A container can have 0.0.0.0:PORT->container_port on the HOST but be unreachable from here.
ALWAYS use `compose(ps)` on the compose project to check port mappings instead.

§

CONTEXT RETRIEVAL:
Before executing a task, ALWAYS use search_messages to check past conversation history and session context: previous prompts, research, decisions may already cover the topic. Do not assume you have all context just from the current message. Existing session data can save re-doing work.