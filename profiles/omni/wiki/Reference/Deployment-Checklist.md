# Deployment Checklist

Deploying a new service via docker compose requires ALL of these steps. Do NOT skip any.

## Step 1: Verify Mount Map

Before writing any files, verify the container's volume mounts:
```
docker inspect omni-stack-omniagent-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

This tells you where your files will actually land. **Critical:** `filesystem_write` uses the container path (`Destination`), but `compose` validates the host path (`Source`).

## Step 2: Check Port Availability

**Do NOT** use: `fetch("http://localhost:PORT/")`: this only checks ports inside this container's network namespace. A container on the host can occupy the port but be invisible from here.

**DO use:**
```
compose(project_dir="<verify-project-dir>", command="ps")
```
Or check if a compose project is already using the port.

If a container from another compose project is using the target port, stop it via:
```
compose(project_dir="<that-project-dir>", command="stop", service="<service>")
```

## Step 3: Write Files to Paths Reachable by compose

**The container volume mount mapping creates a path discrepancy:**

| Container path (filesystem tool) | Host path (compose tool) | Accessible? |
|---|---|---|
| `/opt/workspace/...` | `/opt/workspace/omni-workspace/...` | ✅ compose sees `/opt/workspace/omni-workspace/` |
| `/opt/data/...` | `/opt/workspace/omni-stack/...` | ✅ compose sees `/opt/workspace/omni-stack/` |
| `/app/...` | `/opt/workspace/omniagent/...` | ✅ compose sees `/opt/workspace/omniagent/` |

Write files to a container path whose corresponding host path is under `/opt/workspace/` for compose to find them.

## Step 4: Create docker-compose.yml (if needed)

Write a compose file that:
- Uses a valid Docker image (pull from registry or build from Dockerfile)
- Maps container port to the target host port
- Mounts volumes correctly (use absolute or verified relative paths)

## Step 5: Deploy

**Writing the compose file does NOT deploy it.** Always call:
```
compose(project_dir="<host-abs-path>", command="up", args="-d")
```

Parameters:
- `project_dir`: The HOST path where the docker-compose.yml resides
- `command`: The compose verb (`up`, `down`, `ps`, `logs`, etc.)
- `args`: Extra arguments (e.g., `"-d"` for detached)
- `service`: Only needed for `exec`, `stop`, `restart` (NOT for `up` or `down`)
- `timeout`: Optional timeout in seconds

## Step 6: Verify

Check the service is running:
```
compose(project_dir="<host-abs-path>", command="ps")
```

Verify the service responds. If curl is available inside the composed container, use:
```
compose(project_dir="<host-abs-path>", command="exec", service="<service>", args="curl -sI http://localhost:PORT/")
```

## Anti-Patterns

- ❌ **Scope creep during deployment**: Do NOT upgrade infrastructure (e.g., changing from Python HTTP to nginx) while deploying. Infrastructure improvements are separate tasks.
- ❌ **Not verifying after compose**: `up -d` can succeed while the port binding fails silently (port already taken). Always verify with `ps` and a health check.
- ❌ **Writing compose file without deploying**: The compose file is inert until you call `up`.
- ❌ **Using `fetch` to check host port availability**: `fetch` only sees this container's network.
