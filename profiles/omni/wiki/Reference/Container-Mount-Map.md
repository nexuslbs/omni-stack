# Container Mount Map

The omniagent container mounts several host directories, creating path namespace discrepancies between MCP tools. Understanding these is critical for correct file operations and docker deployments.

## Current Mount Map

| Host Path | Container Path | Purpose | compose accessible? |
|---|---|---|---|
| `/opt/workspace/omni-workspace/` | `/opt/workspace/` | Project development files | ✅ Yes - under `/opt/workspace/omni-workspace/` |
| `/opt/workspace/omni-stack/` | `/opt/data/` | AGENTS.md, wiki, skills, memories, templates | ✅ Yes - under `/opt/workspace/omni-stack/` |
| `/opt/workspace/omniagent/` | `/app/` | Source code, compiled binaries | ✅ Yes - under `/opt/workspace/omniagent/` |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker socket for compose tool | N/A |

## Path Discrepancy Bug

This is the most common deployment failure. The `filesystem` MCP tool writes through the container's filesystem. The `compose` MCP tool validates paths on the HOST.

**Example:**
```
filesystem_write(path="/opt/workspace/playground/build/wiki-llm/docker-compose.yml", ...)
```
- Container writes to: `/opt/workspace/playground/build/wiki-llm/`
- Bytes land at HOST path: `/opt/workspace/omni-workspace/playground/build/wiki-llm/`
- `compose(project_dir="/opt/workspace/playground/build/wiki-llm/")` → looks at HOST `/opt/workspace/playground/build/wiki-llm/` which DOES NOT EXIST
- `compose(project_dir="/opt/workspace/omni-workspace/playground/build/wiki-llm/")` → looks at HOST `/opt/workspace/omni-workspace/playground/build/wiki-llm/` which DOES EXIST

## Verification

Always verify the mount map before writing files for docker deployment:
```
docker inspect omni-stack-omniagent-1 \
  --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

## Rule of Thumb

When `filesystem_write` writes to a path starting with `/opt/workspace/`, the files will be at `/opt/workspace/omni-workspace/` on the host (NOT at `/opt/workspace/` directly).
