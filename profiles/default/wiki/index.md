# OmniAgent Wiki

## Index

- **Reference/**
  - [Deployment Checklist](./Reference/Deployment-Checklist.md) — How to deploy services correctly via compose
  - [Container Mount Map](./Reference/Container-Mount-Map.md) — Volume mount mapping between host and container
- **Log**
  - [log.md](./log.md) — Change log

## Key Facts

- You have NO shell/terminal tool. All operations go through MCP tools.
- Docker operations: `compose` MCP tool only.
- File operations: `filesystem_*` MCP tools only.
- Port checking via `fetch` is unreliable from inside the container.
