# SSH Plugin (Implementation)

**Status:** IMPLEMENTED (omniagent `bccfd2a` — builtin mcp-server-ssh: ssh_run/ssh_copy/ssh_status tools; keys/config from `{OMNI_DIR}/data/ssh/`; see remote-development skill)
**Date:** 2026-08-16
**Scope:** omniagent (new builtin `ssh` tool plugin), omni-stack (plugins.yml/config/template/skill wiring), omni-deployer (integration tests)

## Goal

Create a **builtin ssh plugin** in omniagent (same class as git, docker, prompt,
memory, skills — a Rust MCP stdio server under `plugins/tools/ssh/`). The plugin
lets the agent run commands on and copy files to/from a **remote machine** over
SSH, using keys/config from a directory inside OMNI_DIR data (default
`{OMNI_DIR}/data/ssh/`). It is deliberately **agnostic**: the plugin knows
nothing about what the agent uses ssh for — it just executes ssh/scp operations
safely and reports results. Remote-development workflows (clone repo → copy
secrets → compose up → wait-task → logs/status) are built ON TOP of the plugin
as a skill + template guidance, NOT baked into the plugin.

## Why (verified)

- omniagent already ships builtin tool plugins with a proven pattern:
  - `plugins/tools/git/` (`mcp-server-git`): shells out to the `git` CLI via
    fully-async `tokio::process::Command`, `kill_on_drop(true)`, piped
    stdout/stderr, stdin=/dev/null, per-call timeout — `run_git` at
    plugins/tools/git/src/main.rs:314 is the canonical subprocess pattern.
  - `plugins/tools/docker/` (`mcp-server-compose`): same pattern for `docker
    compose`, with background-task integration (tool returns
    `{"status":"processing","task_id":...}`; agent follows with
    `builtin_wait-task`/`poll-task`/`cancel-task` — main_loop.rs:1347). No
    default timeout (explicit `timeout` param only).
- The dev template (profiles/omni/templates/dev-development.md) already teaches
  the docker-based local workflow with wait-task; the ssh plugin extends the
  same pattern to remote machines.
- ssh/scp/sftp CLIs are present in the image (OpenSSH_10.0p2 Debian) — no new
  runtime deps needed. Plugin is a thin safe wrapper around them, like git is
  for git CLI.
- Workspace Cargo.toml `members` lists every plugin; Dockerfile copies each
  plugin's Cargo.toml into the dep-cache layer and `COPY --from=builder
  /build/target/release/mcp-server-* /usr/local/bin/` auto-picks up new plugin
  binaries (Dockerfile:151) — so a new plugin needs: workspace member entry +
  Dockerfile Cargo.toml COPY line + `plugins/tools/ssh/` sources + plugins.yml
  enable + config.json allowed_tools entries.

## Design

### 1. `plugins/tools/ssh/` — new builtin MCP server (`mcp-server-ssh`)

Mirror the git/docker plugin layout exactly:

- `Cargo.toml` — name `mcp-server-ssh`, deps: mcp-server-util, anyhow, serde,
  serde_json, tokio (full), tracing, tracing-subscriber. NO new heavy deps.
- `plugin.json` — type=mcp, entrypoint `mcp-server-ssh` stdio.
- `mcp-config.json` — server name `ssh`, `allowed_tools: ["*"]`.
- `src/main.rs` — tools (each a `McpToolEntry` with `soft_error_async`):

  **`ssh_run`** — run a command on a remote host.
  - args: `host` (required — host alias from ssh config OR `user@host:port`
    inline), `command` (required — shell command, no char restrictions, wrapped
    in `sh -c` on the remote like docker compose args), `timeout` (optional —
    explicit seconds; when omitted NO timeout, rely on wait-task for
    long-running), `workdir` (optional — remote dir, cd before running),
    `script` (optional — multi-line script piped to remote `sh` via stdin, same
    idea as docker compose `script`), `ssh_dir` (optional override).
  - Returns: combined stdout/stderr, exit code, duration; `{"status":
    "processing", "task_id": ...}` for long commands (register in the core task
    registry so wait-task/poll-task/cancel-task work — follow docker compose
    behavior).
  - Subprocess hygiene (copy from run_git, CRITICAL): `Command::new("ssh")`
    with `stdout(Stdio::piped()).stderr(Stdio::piped()).stdin(Stdio::null())
    .kill_on_drop(true)`; pass `-o BatchMode=yes -o
    ConnectTimeout=<cfg>` and `-F <ssh_dir>/config` when config file exists;
    never inherit stdin/stdout (MCP JSON-RPC channel corruption class G17b).

  **`ssh_copy`** — copy files to/from a remote host (scp).
  - args: `host` (required), `direction` (`to-remote`|`from-remote`), `source`
    (local or remote path), `destination` (remote or local path), `recursive`
    (optional bool → `-r`), `timeout` (optional).
  - Used for copying secrets/keys/env files to the remote machine and pulling
    logs/artifacts back. Follows the same subprocess hygiene.

  **`ssh_status`** (optional but cheap) — check connectivity: run
  `ssh -o BatchMode=yes -o ConnectTimeout=10 host true`, return ok/error
  latency. Helps the agent fail fast before scripting a long setup.

- **Config** (plugin.json config_schema):
  - `ssh_dir` (default `{OMNI_DIR}/data/ssh/` — resolved from `$env:OMNI_DIR`,
    like git's `omni_dir`): the directory containing the ssh `config` file
    (hosts/aliases/keys) and any keys. Chosen over a single `ssh_key` config
    value because it supports multiple hosts/keys/aliases and matches how real
    ssh works; the config file can point to keys inside the same dir
    (`IdentityFile ~/.ssh/...` relative paths resolved against ssh_dir).
  - `connect_timeout_secs` (default 10).
  - `workspace_dir` optional (sandbox for local side of ssh_copy, like git).
  - The plugin must create `ssh_dir` if missing and chmod 600 any private key
    it references (fail with a clear error if perms can't be set — never run
    ssh with a world-readable key).

### 2. Registration (the 5 wiring points)

1. Root `Cargo.toml` — add `"plugins/tools/ssh"` to `members`.
2. `Dockerfile` — add `COPY plugins/tools/ssh/Cargo.toml
   ./plugins/tools/ssh/` in the dep-cache block (binary auto-copied by the
   `mcp-server-*` glob; sources copied by `COPY . .`).
3. `config/plugins.yml` — add under `tools:`: `ssh: {enabled: true, source:
   built-in, config: {}}`.
4. Profile `config.json` `allowed_tools` — add the ssh tools (e.g.
   `ssh_run`, `ssh_copy`, `ssh_status` — match actual registered names, use
   the same naming style as docker_compose/git_status).
5. `tests/plugin_tests.rs` — add `"ssh"` to the builtin listing test so the
   plugin's presence is covered.

### 3. Skill + template (remote development, SEPARATE from plugin)

- New skill (e.g. `remote-development` or extend `workspace-development`):
  documents the remote-setup workflow pattern:
  1. `ssh_run` git clone/checkout on the remote machine
  2. `ssh_copy` secrets/env/keys to the remote
  3. `ssh_run` docker compose up -d (background task + wait-task while long)
  4. `ssh_run` compose ps / logs --tail / status; pull artifacts back with
     `ssh_copy`
  - Emphasize: verify remote state cheaply first (ssh_status + one command),
    never redo verified work, keep the same "notes-first" discipline as local
    dev.
- Template guidance: dev-development.md (or a remote-dev flavor) references the
  ssh plugin for remote machines, mirroring the existing docker-plugin
  paragraph ("like docker for local, ssh for remote").

### 4. Tests (omni-deployer)

- GROUP 34 (`G34`) in scripts/tests.py, following the G33 pattern:
  - 34-A `ssh_run` against a **local throwaway sshd**: start `sshd` on
    127.0.0.1:port inside the test container (or a tiny ssh server in a
    container), generate a throwaway key into a temp ssh_dir, verify run/exit
    code/output.
  - 34-B `ssh_copy` to-remote/from-remote roundtrip against the same local
    sshd (perms preserved, recursive).
  - 34-C error paths: unreachable host, bad key, timeout, missing ssh_dir,
    world-readable key rejection.
  - Add `_run_g34.py` driver (pattern of `_run_g33.py`).
- If a local sshd is impractical in the test env, fall back to a **fake
  ssh/scp shim** in PATH that records invocations and returns canned output
  (assert the plugin builds correct args/options), plus real-command tests run
  manually in omnidev against the local sshd. Preference: real local sshd if
  it works in the omnidev container (openssh-server package install is allowed
  in the DEV container — never omnistable).

### 5. Verification steps (executor)

- `cargo build --release -p mcp-server-ssh` + `cargo clippy -p mcp-server-ssh
  -- -D warnings` + `cargo test -p mcp-server-ssh` in omnidev (SQLX_OFFLINE
  must stay false in dev).
- Live plugin listing shows `ssh` built-in with source; allowed_tools include
  the ssh tools.
- Functional check in omnidev: real `ssh_run` against localhost sshd with a
  throwaway key (or at minimum a shim test) proving the tool returns output +
  exit code, and `ssh_copy` roundtrips a file.
- omnistable stays frozen: NO migrations, NO rebuilds, NO restarts on
  omnistable stacks. Changes reach omnistable only via next CI build from main.

## Open items / decisions for executor

- Exact tool names (ssh_run/ssh_copy/ssh_status vs alternatives) — keep them
  consistent with the `{server}_{tool}` qualified format (e.g.
  `ssh_ssh-run`? — check how docker's `compose` becomes `docker_compose` and
  match the pattern; the registered name is what goes in allowed_tools).
- Whether `ssh_status` is worth a tool vs folding into ssh_run with `true`
  — executor picks the cleaner design; keep the tool surface minimal.
- sshd-in-test feasibility: verify `openssh-server` can run in the omnidev
  container before committing to G34 design.
