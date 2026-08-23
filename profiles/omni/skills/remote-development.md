# Remote Development (SSH)

Run development workflows on a **remote machine** over SSH using the `ssh`
plugin (`mcp-server-ssh`). The plugin is agnostic — it only runs ssh/scp
operations; this skill layers the remote-dev workflow pattern on top.

## Prerequisites

- The remote machine is reachable from the agent container over SSH, with a
  host alias (or key) configured in `{OMNI_DIR}/data/ssh/config` (see the ssh
  plugin's `ssh_dir` config; keys referenced by the config file must be
  `chmod 600`).
- `ssh_status` succeeds against the target host — run it FIRST to fail fast.

## Workflow (remote setup)

1. **Verify remote state cheaply first** — never redo verified work:
   - `ssh_run` a cheap probe (e.g. `hostname && uname -a`) or `ssh_status`
     to confirm connectivity.
   - `ssh_run` `ls` / `git -C <repo> rev-parse HEAD` to see what already
     exists on the remote before cloning/setting up.
2. **Clone / checkout code on the remote**:
   - `ssh_run` `git clone <url> <dir>` (or `git -C <dir> fetch && git -C <dir>
     checkout <ref>`).
3. **Copy secrets / env / keys to the remote**:
   - `ssh_copy` `direction: to-remote` with the local secret/env file as
     `source` and the remote path as `destination`. Use `recursive: true` for
     directories. Never log secret contents; note only paths.
4. **Bring services up**:
   - `ssh_run` `cd <dir> && docker compose up -d` — for long-running commands
     omit `timeout`; the call returns `{"status":"processing","task_id":...}`
     and you follow with `builtin_wait-task` (or poll/cancel), exactly like
     local docker compose.
5. **Check status / logs / artifacts**:
   - `ssh_run` `docker compose ps` / `docker compose logs --tail=50` /
     `docker compose status` on the remote.
   - Pull artifacts back with `ssh_copy` `direction: from-remote`.

## Discipline

- Take working notes (`notes_note-write`/`notes_note-append`) with remote
  paths, hosts, and state as you go — notes survive compaction.
- Commit partial work on the remote repo as you go (`ssh_run` git commit/push
  on the remote) — a thread can die at any moment.
- Prefer `ssh_status` + one cheap command before scripting a long setup.
- The plugin never exposes keys: keep them in `ssh_dir` with 600 perms.
