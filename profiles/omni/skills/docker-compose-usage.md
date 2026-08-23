# Docker Compose Usage

Use this skill when building, running, or inspecting multi-service projects. All Docker operations go through the `docker_compose` tool — there is no direct shell access to the Docker daemon.

## The docker_compose Tool

`docker_compose` takes two main parameters:

- **project_dir** — the directory containing the `docker-compose.yml` file (e.g. `/opt/workspace/<project>`).
- **command** — the compose verb and flags. The tool runs `docker compose <command>` in that directory.

Common commands:

| Command | Purpose |
|---------|---------|
| `build` | Build images for all services |
| `up -d` | Start all services in detached mode |
| `ps` | List running services and their health/status |
| `logs <service>` | Show logs for one service (`logs -n 100 <service>` for recent lines) |
| `down` | Stop and remove containers/networks |
| `exec <service> <cmd>` | Run a command inside a running container |
| `run --rm <service> <cmd>` | Run a one-off command in a new container |

## Workflow

1. **Read the project docs first** — check `README.md` / `AGENTS.md` / `docker-compose.yml` for the service layout (db, backend, frontend) and expected commands.
2. **Build + start** — `docker_compose(project_dir="...", command="build")` then `docker_compose(project_dir="...", command="up -d")`.
3. **Verify health** — `docker_compose(project_dir="...", command="ps")`; confirm each service is `Up` and healthy. If a service exited, inspect `docker_compose(project_dir="...", command="logs <service>")`.
4. **Run commands inside containers** — use `exec` with the service name, e.g. `docker_compose(project_dir="...", command="exec db psql -U <user> -d <db> -c 'SELECT 1'")`. Everything after the service name runs inside the container.
5. **Check logs for errors** — when something fails, `logs` is the fastest diagnostic.

## Service Access Patterns

- **Database service** — connect from inside the container: `exec db psql -U <user> -d <db>`. Credentials come from the project's `.env` or compose `environment:` block.
- **Backend API** — verify it responds: `exec backend curl -s http://localhost:<port>/health` (if curl is in the image) or `logs backend`.
- **Frontend** — usually served on a host port; verify the container is healthy and check the build output in logs.

## Pitfalls

- `docker compose` commands must run from the project directory that owns the `docker-compose.yml` — always pass the correct `project_dir`.
- After editing `docker-compose.yml` or Dockerfiles, rebuild with `build` before `up -d` so the new image is used.
- A service in `Exit` state means the container crashed at startup — read its logs, don't just restart it blindly.
- Ports are only reachable from inside the Docker network in this environment; use `exec` into a container to reach service endpoints (e.g. `http://backend:8080`), not `localhost` from the host.
- Never hardcode credentials in compose files; reference environment variables.
