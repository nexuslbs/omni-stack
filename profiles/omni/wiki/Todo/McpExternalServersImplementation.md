# External / Agnostic MCP Servers (Implementation)

**Status:** IMPLEMENTED 2026-08-16 (omniagent `92c8b40` — Python/NodeJS dependency install for non-Rust remote plugins; the 7 modelcontextprotocol reference servers wired in omni-stack `config/remote.yml`)
**Date:** 2026-08-16
**Scope:** omniagent (plugin install API + remote MCP support), omni-stack (config), omni-deployer (integration tests)

## Goal

Make omniagent work with **external, agnostic MCP servers** — standard MCP
servers that are NOT omniagent-focused. Verify against the Reference Servers
from https://github.com/modelcontextprotocol/servers:

- **Everything** — reference/test server with prompts, resources, and tools
- **Fetch** — web content fetching and conversion for efficient LLM usage
- **Filesystem** — secure file operations with configurable access controls
- **Git** — tools to read, search, and manipulate Git repositories
- **Memory** — knowledge graph-based persistent memory system
- **Sequential Thinking** — dynamic and reflective problem-solving through
  thought sequences
- **Time** — time and timezone conversion capabilities

The executor adds each server manually as a **remote MCP** via the plugin API
endpoints (install-git etc.) and makes **at least 1 tool call in each** against
the live omnidev stack, verifying they actually work. The tester adds
integration tests covering at least 1 tool of each server with correct-return
assertions. Implementation and live verification happen in **omnidev**.

## Why (verified)

- Plugin install API today: `install_plugin_handler`
  (`src/server/plugins_install.rs:22`), `install_git_handler` (`:345`); the
  install flow **compiles with cargo** (`:199` "Compile (force rebuild: remove
  stale binary so cargo actually recompiles)"). So today only compilable
  languages (Rust) can be installed via the API.
- Routes: `POST /api/plugins/install-git`, `POST /api/plugins/install-url`,
  `POST /api/plugins/{type}/{source}/{name}/install`
  (`src/server/plugins.rs:62-83`).
- Remote plugins (git-installed, `remote` field in YAML) are cloned into
  `plugins/<type>/.remote/` (src/server/plugins.rs:21-25).
- The Reference Servers are Python (everything, fetch, memory,
  sequentialthinking, time) and NodeJS (filesystem, git) based — the git clone
  alone does NOT provide their dependencies, so Python (`requirements.txt`)
  and NodeJS (`package.json`) packages must be installed as part of install.
  The current cargo-only install API does not do this.

## Design (executor picks cleanest implementation)

### 1. Add the 7 reference servers as remote MCPs (omnidev, live)

- Add each repo as a **remote tool plugin** via the plugin API endpoints
  (install-git or equivalent). Do it manually — this is the real exercise.
- For each server, **make at least 1 tool call** through omniagent and verify
  it works: the call succeeds AND the returned content is correct (not just
  "a call happened"). Record the verified calls (server, tool, input, return
  shape) for the tester to reuse.

### 2. Extend the install API for Python / NodeJS (only if needed)

- The git directory may not have its dependencies installed; install must
  handle that for non-compiled languages:
  - **Python**: install deps from `requirements.txt`
    (pip install -r requirements.txt) — no compilation.
  - **NodeJS**: `npm install` from `package.json`.
- Keep the Rust compile behavior unchanged.
- Verify best practices about it (hermetic installs, honoring the repo's own
  declared deps, no global package pollution, `npm ci`/virtualenv where
  appropriate). The executor may need to IMPLEMENT this — extend
  `plugins_install.rs`, don't reinvent.

### 3. External binaries (OS libraries) — NOT the API's concern

- Video/graphic/OS libraries that must exist in the OS belong in the
  **image** (Dockerfile). The install API must not try to apt-get/yum etc.

### 4. Tester: integration tests

- Add integration tests (omni-deployer `scripts/tests.py`, new group — G31 is
  boards; use e.g. G32) covering **at least 1 tool of each of the 7 servers**.
- Assert the RETURN is correct (shape + content), using the executor's live
  verification as reference for what "correct" means.
- Existing groups: G26 (plain kanban no workflow), G29 (status-change
  dispatch/redispatch), G30 (surgical stop), G31 (boards).

## Acceptance criteria

1. All 7 Reference Servers added as remote MCPs in omnidev; ≥1 tool call each
   with **correct returns** (executor live-verified).
2. Python/NodeJS install support implemented if needed (requirements.txt /
   package.json) — Rust compile flow unchanged.
3. External OS binaries live in the image, not in the API.
4. Integration tests cover ≥1 tool per server with correct-return assertions;
   all gates green (cargo fmt/check/clippy, `cargo test` live DB, tests.py
   new group, dashboard suite if touched).
5. omnidev-only; **omnistable frozen** (no migrations, no rebuild/restart in
   omnistable; shared config file presence is harmless — old binary ignores
   it; verify via schema unchanged + container RestartCount=0).

## Notes for the executor

- Live verification is the POINT: external MCP servers must WORK (calls
  succeed with correct returns), not just install.
- Dev loop per `dev-development.md`: live temp DB, `SQLX_OFFLINE=false`;
  `SQLX_OFFLINE=true` is CI-only. Never touch the live omnistable stack.
- Reuse the plugin install machinery (`plugins_install.rs`) — extend, don't
  reinvent.
- The dashboard should not need changes; if the install API response shape
  changes, keep it backward compatible.
