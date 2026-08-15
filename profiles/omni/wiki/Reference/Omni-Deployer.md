# Omni-Deployer: Deployment Harness & Test Suite

**Status:** Active (2026-08-15 — deploy.py dev verified exit 0, run #10)
**Scope:** `/opt/workspace/omni-deployer` (`deploy.py`, `shared.py`, `omnidev.py`,
`omnistable.py`, `scripts/tests.py`)
**Related:** [Deployment Checklist](./Deployment-Checklist.md) · [DeepSeek Prefix-Cache Misses](./DeepSeek-Prefix-Cache.md) · [Deploy.py dev Run](../Todo/DeployPyDevRunImplementation.md)

## What it is

The omni-deployer repo is the single entry point for building, deploying, and
testing the OmniAgent stack. It owns the compose lifecycle, env generation,
DB setup, migrations, and the full test suite (Rust + Python + MCP tool tests).

Entry points:

| Script | Purpose |
|---|---|
| `deploy.py` | Orchestration: `dev` (build from source), `ci` (pre-built images), `test` (run tests only) |
| `shared.py` | Shared logic: env generation, stack stop/start, secrets via API, `run_tests()` (Phase 1 + Phase 2 tool tests) |
| `omnidev.py` / `omnistable.py` | Launchers for the two permanent stacks (dev / stable runtime) — read `secrets.env` via `shared.setup()` |
| `scripts/tests.py` | Python integration suite (kanban, workflows, hooks, platforms, stop-thread…) piped into the omniagent container |

## The deploy.py dev pipeline (verified green, exit 0)

1. **Step 0.5** — pre-flight: auto-restores known omni-stack residue (untracked
   `actions.yml`, `remote.yml`, `settings.yml`, `.taskj-*.patch`, wiki files;
   tracked config reverts are *not* done here — only the final restore reverts
   tracked configs). Tolerates the deploy's own `channels.yml`/`tasks.yml` mutations.
2. **Step 0.6** — `patch_deploy_channels_noop()`: pins the `cron` channel to
   `provider: noop / model: test-tool-caller` in `config/channels.yml`
   (deploy-only; idempotent; reverted by the final seed restore).
3. Images → databases (postgres, mattermost-db) → migrations.
4. **Pretests** (inside the dev image): `cargo fmt --check`, `cargo check`
   (warnings-as-errors, workspace all targets), `cargo clippy`, `cargo test --workspace --release`.
   ⚠️ Verification gates in task bodies must say plain `cargo check`/`cargo test` —
   **never `SQLX_OFFLINE=true cargo check`** (SQLX_OFFLINE is CI-only; the dev
   overlay validates against the live DB).
5. `prepare.py` (cargo fmt + sqlx prepare) → build all binaries → start services.
6. **Rust integration**: `api_tests` + `plugin_tests` (API contract, plugin
   install/enable/disable/restart, remote plugin registration).
7. **Python integration PASS 1 + PASS 2** (identical; catches order-dependence
   and state leakage): kanban lifecycle, workflow roles, hooks/schedules,
   stop-thread surgical behavior, terminal-status invariants, platform plugins
   (Python/JS/Rust multi-source + lifecycle).
8. **Shared tool tests** (`shared.run_tests()`): Phase 0 env setup → Phase 1
   (each MCP tool in enabled/disabled/restricted states) → Phase 2 (agent
   integration via Mattermost, 22 tools × 3 states) → profile restore.
9. **Final seed restore**: `git checkout HEAD --` the tracked configs the tests
   persisted (actions/channels/plugins/settings/workflows/tasks/relevant-index),
   then FAILS if any tracked change remains — guarantees the next run's Step 0.5
   passes and the live omnistable config is untouched.

## Invariants (learned the hard way — do not break)

- **The deploy is noop-only.** The deploy DB is fresh with NO LLM secrets
  (only the 4 Mattermost ones). `secrets.env` is omnidev/omnistable-only —
  `deploy.py` never reads it; `shared.setup()` (omnidev/omnistable) does.
  The `omni` profile pins `provider: deepseek`, so ANY thread on a channel
  without an explicit provider 401s with
  `$secret:DEEPSEEK_API_KEY not found in secrets table` — that is why Step 0.6
  pins the `cron` channel (the only system channel tests execute threads on).
- **`deploy.py dev` must never touch omnistable.** `DEV_STOP_EXCLUDE =
  {"omnistable"}` in deploy.py; the dev-mode stop targets only omnidev.
  omnistable runs on `ghcr.io/nexuslbs/omni-deployer/omniagent:latest`
  (distinct CI image name) — a bare `docker compose up -d` for omnistable is
  WRONG: it skips `omnistable.env` (which pins `OMNIAGENT_IMAGE` +
  `COMPOSE_PROFILES=noop,mattermost`) and falls back to the clobbered default
  image. Always `python3 omnistable.py setup/up`.
- **Fresh data volumes every run** — the DB is wiped, so every fix must be
  seedable/deploy-time, never reliant on persistent state.
- **Config files under omni-stack are root-owned** (the omniagent container
  writes them as root) → all config writes go through a temp file +
  `sudo mv` (deploy.py installs a no-op sudo shim when running as root).

## Schema facts that bite the tests

- The legacy `channels` DB table was **dropped**. Channels live in
  `channels.yml`; `threads.channel_id` holds the channel **NAME** (a string).
  - `query_database` tests must query surviving tables, e.g.
    `SELECT channel_id AS channel, status FROM threads ORDER BY id LIMIT 1`.
  - `query_channel-prompts` takes `{"channel_id": "kanban", ...}` — a numeric
    id fails with `'channel_id' is required … Pass channel_id explicitly`.
- seq-0 messages are created with `role='cause'`, `msg_type='Cause'`/`'kanban'`
  (role/msg_type rename) — thread finders must match `role IN ('user','cause')`.
- Task delete detaches threads (`UPDATE threads SET task_id = NULL`) — an empty
  task_id after cleanup is expected, not a bug.
- The channel-busy dispatch gate counts `status IN ('pending','processing')`
  only (deliberately NOT terminal-based). Test-side serialization
  (`_wf_drain_channel`) is the fix, not a gate change.

## Test-fix patterns (all real race/schema fixes — never weaken a test)

| Fix | Root cause |
|---|---|
| `_wf_drain_channel` (tests.py) | wf8's executor thread can still be pending when wf9 dispatches → `dispatched:false, "Channel busy"`. Drain the shared channel before every workflow test. |
| Atomic `tasks_yml_remove_keys` (mkstemp + os.replace + chmod) | The hooks engine loads tasks.yml on every event; a truncate+write let it read a partial file → parse-fail → treated as EMPTY → hooks missed events. |
| g29 accepts `scheduled`\|`running` | The channel handler flips thread_status scheduled→running on pickup — either proves the dispatch marker was set. |
| g30 `since_id` baseline | The unbaselined finder latched onto a stale terminal thread from another group with the same script marker. |
| Query tool args (shared.py `TOOL_DEFS` + `phase2_tools_list`) | Post-migration schema: channels table gone, channel_id is a NAME. |
| Git-hygiene tolerance (channels.yml/tasks.yml) | The deploy's noop pin and the API's serde rewrite (comments stripped) must survive mid-run; the final seed restore reverts both. |

## Running it

```bash
cd /opt/workspace/omni-deployer && python3 deploy.py dev > /tmp/deploy-dev.log 2>&1
# ~28–30 min; exit 0 = fully green
```

Quick shared-tool-test iteration without the full pipeline (stack already up):

```python
# /tmp/run_shared_tests.py — mirrors deploy.py Step 11
import sys; sys.path.insert(0, "/opt/workspace/omni-deployer")
import shared
s = shared.Settings(env_path="/opt/workspace/omni-deployer/omni.env",
    compose_file="/opt/workspace/omni-stack/docker-compose.yml",
    dev_overlay="/opt/workspace/omni-stack/docker-compose.dev.yml",
    project_name="omnideploy", container="omnideploy-omniagent-1",
    setup_channel="setup", omni_stack_dir="/opt/workspace/omni-stack",
    workspace_dir="/opt/workspace", script_dir="/opt/workspace/omni-deployer/scripts",
    use_api=False)
shared.init(s); shared.run_tests()
```

## Secrets hygiene

- Values live in Postgres `secrets` (columns `name`, `field_type`,
  `current_value` — NOT `value`); `DEEPSEEK_API_KEY` / `OPENCODE_API_KEY` exist
  ONLY in the omnidev/omnistable `secrets.env`, never in the deploy DB.
- Test scripts read keys via `docker exec … psql` subprocess — never inline in
  argv (process-list exposure).
- omni.env (generated Mattermost passwords) is gitignored; so are
  `secrets.env.bak*` backups.
