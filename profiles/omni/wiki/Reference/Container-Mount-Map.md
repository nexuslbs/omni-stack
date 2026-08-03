# Container Mount Map

The omniagent container mounts several host directories. These paths are the SAME
inside and outside the container for `/opt/workspace` — no translation. `data_dir`
(`/opt/omni`) is the exception: it maps to the omni-stack repo on the host.

## Current Mount Map (verified against a live omnidev container)

| Host Path | Container Path | Purpose | Notes |
|---|---|---|---|
| `/opt/workspace` | `/opt/workspace` | Project files | Same path, no translation |
| `/opt/workspace/omni-stack` | `/opt/omni` | data_dir: config, profiles, wiki, skills, memories, templates | **Translates**: `/opt/omni/...` == `/opt/workspace/omni-stack/...` |
| `/opt/workspace/omniagent` | `/app` | Source code, compiled binaries | **Translates**: `/app/...` == `/opt/workspace/omniagent/...` |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker socket for docker_compose tool | Same path |

## Path Translation Rules

- `/opt/workspace/<project>` on the container IS `/opt/workspace/<project>` on the host
  (same path, no translation) — `docker_compose(project_dir="/opt/workspace/<project>/...")` works as-is.
- `/opt/omni/...` on the container IS `/opt/workspace/omni-stack/...` on the host.
- `/app/...` on the container IS `/opt/workspace/omniagent/...` on the host.
- When deploying via `docker_compose`, use the container path; when checking host files,
  translate via this map.

## Historical Note (do NOT trust old docs)

Older documentation (and this page before it was corrected) claimed `omni-stack →
/opt/data` and `omni-workspace → /opt/workspace`. That was an earlier layout and is
WRONG for the current stack. Verify with `docker inspect` whenever in doubt:

```
docker inspect <omniagent-container> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

## Path Discrepancy: filesystem_* vs compose

The `filesystem_*` MCP tools operate on the CONTAINER's filesystem; the `docker_compose` MCP
tool validates paths on the HOST. Because `/opt/workspace` maps 1:1, this usually does
not bite — but for `data_dir` content, the paths differ:

- Container path `/opt/omni/profiles/omni/...` == host path `/opt/workspace/omni-stack/profiles/omni/...`
- Never pass `/opt/omni/...` to `docker_compose(project_dir=...)` — docker_compose needs the HOST path
  (`/opt/workspace/omni-stack/...`).
