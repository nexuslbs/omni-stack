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
compose(project_dir="/opt/workspace/omni-stack", command="exec", service="toolbox",
        args="grep -n '^GROUP' /opt/workspace/omni-deployer/scripts/tests.py")
compose(project_dir="/opt/workspace/omni-stack", command="exec", service="toolbox",
        args="sed -n '3338,3510p' /opt/workspace/omni-deployer/scripts/tests.py")
```
Prefer the project's own service if it has the tools; `toolbox` is the generic fallback.

## Sandbox

- **Filesystem sandbox**: `filesystem_*` tools only operate inside the workspace dir (`/opt/workspace`) and its subdirectories — reads, writes, lists, searches, and metadata calls outside it are rejected. All project files go under `/opt/workspace/<project>/`.
- **Git sandbox**: git tools (`status`, `commit-and-push`, `run-command`, `clone`) only operate inside `/opt/workspace` and subdirectories.

## Tools Available

- **`filesystem_write` / `filesystem_read` / `filesystem_info` / `filesystem_search`**: create and edit project files
- **`compose`**: `build`, `up -d`, `exec`, `down`, `logs -n 50`, `ps`: all Docker operations
- **`commit_and_push`**: git commit + push
- **`query_database`**: run SQL on the shared PostgreSQL to retrieve agent memories, past messages, threads, kanban tasks and config info (for context, not for building)
- **`clone_repo` / `create_github_repo`**: manage git repos

## Workspace Layout

```
/opt/workspace/<project>/
├ docker-compose.yml  # ALWAYS at project root, not in repo/
├ .env                # gitignored, env overrides
└ repo/               # gitignored, source code lives here
```

**Rules**: Only 1 project runs at a time. No docker.sock, no privileged. Names must not start with `omni`.

## compose Tool Usage

The `compose` tool accepts these parameters:
- `project_dir`: directory with docker-compose.yml
- `command`: compose verb + flags (e.g. `up -d`, `build`, `logs --tail=50`)
- `service`: container name (required for exec/run)
- `args`: command to run inside the container (for exec/run only)

### Examples

```
# Build images
compose(project_dir="/opt/workspace/blog", command="build")

# Start services
compose(project_dir="/opt/workspace/blog", command="up", args="-d")

# Run commands INSIDE a container: NO character restrictions
# Everything in `args` runs inside the container via Docker exec, not a shell
compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="cargo build")
compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="npm test")
compose(project_dir="/opt/workspace/blog", command="exec", service="db", args="mysql --help")
compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="sh -c 'cargo build && cargo test'")
compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="ls -la /app/data")

# View logs
compose(project_dir="/opt/workspace/blog", command="logs", args="-n 50")

# Check running services
compose(project_dir="/opt/workspace/blog", command="ps")

# Stop everything
compose(project_dir="/opt/workspace/blog", command="down")
```

### Important: Character Safety

`exec` and `run` commands pass `args` directly to Docker, which passes them to the container's process via `execve`. **No shell** interprets the arguments on the host, so ANY characters are safe: including `$`, `>`, `<`, `&`, `|`, `;`, `*`, `~`, backticks, and brackets. They are all passed verbatim to the command running inside the container.

To run multiple commands inside the container, use a shell:
```
compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="sh -c 'cd /app && cargo build && cargo test'")
```

This runs a shell *inside* the container, and the `&&` chaining executes safely there: never on the host.

### Common pitfalls

- The `repo/` subdir is gitignored at workspace level
- Containers/networks/volumes should be named with the project prefix
- Docker compose project name should match directory name
- When `service` is provided without `command="exec"`, it's ignored
