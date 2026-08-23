# Live Smoke-Testing a New omniagent Build (Isolated Toolbox)

Use when you must live-smoke-test a NEW omniagent binary (API behavior of current
HEAD) WITHOUT touching the deployed omnistable/omnidev stack. Validated on
2026-08-18 (threads 10-11, kanban board-validation smoke) — do not re-derive the
setup.

## Why

The deployed stack can run a PRE-CHANGE binary: unit/integration tests pass on
new code while the live API still behaves old. A dedicated toolbox gives a fresh
DB + the new binary in ~30s and lets you assert real HTTP behavior end-to-end.

## Layout (already exists — reuse, don't recreate)

- Compose project: `/opt/workspace/omni-dev-toolbox/docker-compose.yml`
  (compose project name `omnidev-toolbox` — isolated, `up` does NOT touch
  omni-stack). Services:
  - `db`: `pgvector/pgvector:pg16` (POSTGRES_DB/USER/PASSWORD = omniagent/omniagent/omnidev)
  - `toolbox`: `rust:1.96.0`, env `DATABASE_URL=postgres://omniagent:omnidev@db:5432/omniagent`,
    `OMNI_DIR=/workspace/omni-stack`, `SQLX_OFFLINE=true`,
    `CARGO_TARGET_DIR=/workspace/omniagent-target-toolbox`; volumes
    `/opt/workspace:/workspace:rw` + docker.sock; `command: tail -f /dev/null`.
  - `db` healthcheck = the `depends_on: condition: service_healthy` gate.
- New binary: build with `CARGO_TARGET_DIR=/opt/workspace/omniagent-target-toolbox`
  so the artifact lands at `/opt/workspace/omniagent-target-toolbox/release/omniagent`
  (= `/workspace/...` inside the toolbox container; ~23 MB).
- Smoke scripts live in `/opt/workspace/omni-dev-toolbox/smoke*.sh`.

## Procedure

1. **Build the new binary** (in any rust-capable container):
   `cargo build --release --bin omniagent` with
   `CARGO_TARGET_DIR=/opt/workspace/omniagent-target-toolbox` (and the repo's
   sqlx offline cache so no DB is needed at build time).
2. **Start the toolbox**: `docker_compose(project_dir="/opt/workspace/omni-dev-toolbox", command="up -d")`
   — wait for db healthy (compose `depends_on` handles it).
3. **Write smoke.sh** (`set +e` on top):
   - `BIN=/workspace/omniagent-target-toolbox/release/omniagent`
   - `export DATABASE_URL=postgres://omniagent:omnidev@db:5432/omniagent`
     (and any other env the server needs, e.g. OMNI_DIR).
   - Start `$BIN` in the background, wait for `SERVER_UP` (poll /health or the
     port) with a timeout (observed: up in ~2s).
   - Assert each API behavior with curl + explicit PASS/FAIL echoes; capture the
     server log tail on failure.
   - End with `set +e`-safe exit code aggregation.
4. **Run it**: `docker_compose(project_dir="/opt/workspace/omni-dev-toolbox", command="exec", service="toolbox", args="bash /workspace/omni-dev-toolbox/smoke.sh")`
   — long-running → wait-task with a timeout (observed ~17-22s for 3 rounds).
5. **Cleanup**: delete any test tasks/artifacts created during the smoke, then
   verify the DB query returns empty (e.g. `WHERE title LIKE 'SMOKE%'`).
6. **Report**: per-check results + the exact binary HEAD (`git rev-parse HEAD`)
   the smoke ran against.

## Verification checklist

- Every expected HTTP status asserted (400s for invalid, success for valid).
- Auto-dispatch verified if the feature under test dispatches (thread spawned
  without manual POST /kanban/dispatch).
- Cleanup verified by query, not assumed.
- Report notes the caveat: deployed stack may still run the old binary.

## Pitfalls

- `docker_compose ps` on the TOOLBOX project shows its own containers — do not
  confuse with the omni-stack project (`omnidev-toolbox-*` vs `omnistable-*`).
- The `toolbox` service mounts the whole `/opt/workspace`; keep binary + scripts
  under it so both host and container paths work.
- Never run the toolbox against the deployed stack's DB — it has its own
  `toolbox_pgdata` volume.
