# Workspace Development with Docker

Use this skill when asked to build, run, or test code projects in the workspace. All code execution happens inside Docker containers.

## Rule: Don't Waste Iterations

- This thread has a HARD limit of ~120 tool calls. Budget it like money: ≤10 calls of
  exploration, start writing by call ~20, commit partial work as you go (a dead thread
  loses everything uncommitted).
- If a tool fails 3+ times in a row, **stop calling it** and move on to the next step
- If `list_kanban_tasks` fails, you don't need it to build code: skip kanban
- Searching past messages is rarely needed for building a new project
- When you have a clear instruction, **execute it directly** rather than exploring
- READ FILES ONCE and only what you need. Take notes as you read: compaction keeps only
  a short excerpt of tool results, so re-reading after a compaction teaches you nothing.
- Never read the same file (or the same line range) twice in one thread. If you need a
  fact from a file, extract it the first time and write it to a scratch note outside the
  repo.

## Reading large files (concrete patterns)

`filesystem_read` returns char-based slices, NOT whole files:

- No args → first 50,000 chars + a truncation note when the file is bigger.
- `offset` (default 0) + `limit` (default 50000) → page deterministically:
  ```
  filesystem_read(path="/opt/workspace/omni-deployer/scripts/tests.py", offset=0,     limit=50000)
  filesystem_read(path="/opt/workspace/omni-deployer/scripts/tests.py", offset=50000, limit=50000)
  filesystem_read(path="/opt/workspace/omni-deployer/scripts/tests.py", offset=100000, limit=50000)
  ```
  The response reports the slice, e.g. `[showing chars 50000-100000 of 250000 total chars]`.
  Keep paging until the note no longer says "truncated".

`filesystem_search` matches FILE NAMES only (glob) — it does NOT search file contents.

For exact lines / content grep in a big file, exec inside the project's own container
(no shell on the agent host):
```
docker_compose(project_dir="/opt/workspace/omni-stack", command="exec", service="toolbox",
        args="grep -n '^GROUP' /opt/workspace/omni-deployer/scripts/tests.py")
docker_compose(project_dir="/opt/workspace/omni-stack", command="exec", service="toolbox",
        args="sed -n '3338,3510p' /opt/workspace/omni-deployer/scripts/tests.py")
```
Prefer the project's own service if it has the tools; `toolbox` is the generic fallback.

## Sandbox

- **Filesystem sandbox**: `filesystem_write` (and other WRITE ops) only operate inside the workspace dir (`/opt/workspace`) and its subdirectories — writes outside it are rejected. READS, lists, searches, and metadata lookups are UNRESTRICTED (any path, e.g. `/opt/omni/...` wiki/memories configs can be read). All project files go under `/opt/workspace/<project>/`.
- **Git sandbox**: git tools (`status`, `commit-and-push`, `run-command`, `clone`) only operate inside `/opt/workspace` and subdirectories.

## Tools Available

- **`filesystem_write` / `filesystem_read` / `filesystem_info` / `filesystem_search`**: create and edit project files
- **`docker_compose`**: `build`, `up -d`, `exec`, `down`, `logs -n 50`, `ps`: all Docker operations. The compose MCP tool is registered as `docker_compose` — the bare name `compose` does NOT exist; always call it as `docker_compose(...)`.
- **`commit_and_push`**: git commit + push (registered as `git_commit-and-push`)
- **`query_database`**: run SQL on the shared PostgreSQL to retrieve agent memories, past messages, threads, kanban tasks and config info (for context, not for building)
- **`clone_repo` / `create_github_repo`**: manage git repos (registered as `git_clone-repo` / `git_create-github-repo`)

## Workspace Layout

```
/opt/workspace/<project>/
├ docker-compose.yml  # ALWAYS at project root, not in repo/
├ .env                # gitignored, env overrides
└ repo/               # gitignored, source code lives here
```

**Rules**: Only 1 project runs at a time. No docker.sock, no privileged. Names must not start with `omni`.

## docker_compose Tool Usage

The `docker_compose` tool accepts these parameters:
- `project_dir`: directory with docker-compose.yml
- `command`: compose verb + flags (e.g. `up -d`, `build`, `logs --tail=50`)
- `service`: container name (required for exec/run)
- `args`: command to run inside the container (for exec/run only)

### Examples

```
# Build images
docker_compose(project_dir="/opt/workspace/blog", command="build")

# Start services
docker_compose(project_dir="/opt/workspace/blog", command="up", args="-d")

# Run commands INSIDE a container: NO character restrictions
# Everything in `args` runs inside the container via Docker exec, not a shell
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="cargo build")
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="npm test")
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="db", args="mysql --help")
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="sh -c 'cargo build && cargo test'")
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="ls -la /app/data")

# View logs
docker_compose(project_dir="/opt/workspace/blog", command="logs", args="-n 50")

# Check running services
docker_compose(project_dir="/opt/workspace/blog", command="ps")

# Stop everything
docker_compose(project_dir="/opt/workspace/blog", command="down")
```

### Important: Character Safety

`exec` and `run` commands pass `args` directly to Docker, which passes them to the container's process via `execve`. **No shell** interprets the arguments on the host, so ANY characters are safe: including `$`, `>`, `<`, `&`, `|`, `;`, `*`, `~`, backticks, and brackets. They are all passed verbatim to the command running inside the container.

To run multiple commands inside the container, use a shell:
```
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="sh -c 'cd /app && cargo build && cargo test'")
```

This runs a shell *inside* the container, and the `&&` chaining executes safely there: never on the host.

## Verifying a plugin/tool deliverable (MANDATORY for plugin tasks)

A plugin/tool is NOT done when it compiles — it is done when its actual tools/endpoints
produce the expected output through the real runtime. Minimum bar:

1. **Exact tool names**: the executor calls tools by exact name (e.g. `prompt_generate`,
   `promote_to_memory`). A renamed/mismatched tool silently breaks the feature even when
   "everything compiles". List the tools your plugin registers and check each against the
   name the caller expects.
2. **Functional call**: after install+enable, CALL each tool with real arguments and
   assert the response. For omniagent MCP tools, `POST /mcp/execute` with
   `{"name": "<tool>", "arguments": {...}, "meta": {"profile_name": "omni"}}` runs a tool
   statelessly — use it for verification.
3. **Reference equivalence**: a Python rewrite must produce the SAME output as the Rust
   original on the same input (same sections, same chars order, same fallbacks). Diff the
   outputs, don't eyeball them.
4. **Env refs**: mcp-config.json env values MUST use `$env:VAR` / `$secret:NAME`.
   `"${VAR}"` is NEVER interpolated — it reaches the subprocess as the literal string
   `${VAR}` (framework passes it through verbatim; only `$env:`/`$secret:` are resolved).
   A wrong ref manifests as empty sections (e.g. missing MEMORY/skills in a prompt), not
   as an error — check the generated output, not just process startup.

## Common pitfalls

- The `repo/` subdir is gitignored at workspace level
- Containers/networks/volumes should be named with the project prefix
- Docker compose project name should match directory name
- When `service` is provided without `command="exec"`, it's ignored
