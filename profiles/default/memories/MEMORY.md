FILESYSTEM ACCESS:
- Read/write/search/list are allowed under TWO directories:
  * data_dir — agent config, profiles, wiki, memories
  * /opt/workspace/ — project development
- For project files, write to paths under /opt/workspace/.
- Do NOT try to access paths under /app/.
- For wiki writes, use paths under data_dir/profiles/<profile>/wiki/.
- For research reports, use wiki/Research/<category>/.

§

RESEARCH WORKFLOW (skip if the task is not research):
1. If the prompt already contains the question, use it directly — no separate file needed.
2. ALWAYS search_messages first for past context; search_wiki for existing knowledge.
3. Fetch ALL external data in ONE batch. Do NOT fetch one URL at a time.
4. COMPLETE in 2-4 tool-calling rounds max. More than 6 means you failed.
5. OUTPUT QUALITY: Clear headers, comparison tables, cited sources. Verify by re-reading.
6. Skip Critical-Instructions.md and Anti-Patterns.md — not needed for research.
7. OUTPUT PATH: Write to <data_dir>/profiles/<profile>/wiki/Research/<category>/.
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

CONTAINER VOLUME MOUNT MAP:
/opt/workspace/omni-workspace (host) → /opt/workspace (container) ← filesystem writes go here
/opt/workspace/omni-stack (host) → /opt/data (container) ← wiki, skills, AGENTS.md live here
/opt/workspace/omniagent (host) → /app (container) ← source code, target/release binaries

CRITICAL: filesystem_write to /opt/workspace/playground/ lands at /opt/workspace/omni-workspace/playground/ on the HOST.
But `compose(project_dir="/opt/workspace/playground/...")` uses actual host path.
When deploying via `compose`, verify paths against the mount map first.

§

PORT CHECKING LIMITATION:
fetch("http://localhost:PORT/") only checks ports inside THIS container's network.
A container can have 0.0.0.0:PORT->container_port on the HOST but be unreachable from here.
ALWAYS use `compose(ps)` on the compose project to check port mappings instead.

§

CONTEXT RETRIEVAL:
Before executing a task, ALWAYS use search_messages to check past conversation history and session context — previous prompts, research, decisions may already cover the topic. Do not assume you have all context just from the current message. Existing session data can save re-doing work.