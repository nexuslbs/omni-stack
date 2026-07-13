# OmniAgent Wiki

## Index

- **Reference/**
  - [Deployment Checklist](./Reference/Deployment-Checklist.md) - How to deploy services correctly via compose
  - [Container Mount Map](./Reference/Container-Mount-Map.md) - Volume mount mapping between host and container
  - [Omniagent Mattermost Platform](./Reference/Omniagent-Mattermost-Platform.md) - Mattermost platform architecture, setup, invariants, and recovery
- **Log**
  - [log.md](./log.md) - Change log

## Key Facts

- You have NO shell/terminal tool. All operations go through MCP tools.
- Docker operations: `compose` MCP tool only.
- File operations: `filesystem_*` MCP tools only.
- Port checking via `fetch` is unreliable from inside the container.
