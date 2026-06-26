# Workspace Development with Docker

Use this skill when asked to build, run, or test code projects in the workspace. All code execution happens inside Docker containers.

## Rule: Don't Waste Iterations

- If a tool fails 3+ times in a row, **stop calling it** and move on to the next step
- If `list_kanban_tasks` fails, you don't need it to build code — skip kanban
- Searching past messages is rarely needed for building a new project
- When you have a clear instruction, **execute it directly** rather than exploring

## Tools Available

- **`filesystem_write` / `filesystem_read` / `filesystem_info` / `filesystem_search`** — create and edit project files
- **`docker_compose`** — `build`, `up -d`, `exec`, `down`, `logs -n 50`, `ps` — all Docker operations
- **`commit_and_push`** — git commit + push
- **`query_database`** — run SQL on the shared PostgreSQL to retrieve agent memories, past messages, threads, kanban tasks and config info (for context, not for building)
- **`clone_repo` / `create_github_repo`** — manage git repos

## Workspace Layout

```
/opt/workspace/<project>/
├── docker-compose.yml  # ALWAYS at project root, not in repo/
├── .env                # gitignored, env overrides
└── repo/               # gitignored, source code lives here
```

**Rules**: Only 1 project runs at a time. No docker.sock, no privileged. Names must not start with `omni`.

## compose Tool Usage

The `docker_compose` tool accepts these parameters:
- `project_dir` — directory with docker-compose.yml
- `command` — compose verb + flags (e.g. `up -d`, `build`, `logs --tail=50`)
- `service` — container name (required for exec/run)
- `args` — command to run inside the container (for exec/run only)

### Examples

```
# Build images
docker_compose(project_dir="/opt/workspace/blog", command="build")

# Start services
docker_compose(project_dir="/opt/workspace/blog", command="up", args="-d")

# Run commands INSIDE a container — NO character restrictions
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

`exec` and `run` commands pass `args` directly to Docker, which passes them to the container's process via `execve`. **No shell** interprets the arguments on the host, so ANY characters are safe — including `$`, `>`, `<`, `&`, `|`, `;`, `*`, `~`, backticks, and brackets. They are all passed verbatim to the command running inside the container.

To run multiple commands inside the container, use a shell:
```
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="sh -c 'cd /app && cargo build && cargo test'")
```

This runs a shell *inside* the container, and the `&&` chaining executes safely there — never on the host.

### Common pitfalls

- The `repo/` subdir is gitignored at workspace level
- Containers/networks/volumes should be named with the project prefix
- Docker compose project name should match directory name
- When `service` is provided without `command="exec"`, it's ignored
