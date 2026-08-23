# Run deploy.py dev to green — verify HOST_OMNI_DIR mapping (Implementation)

**Status:** Todo (mirrors kanban task)
**Date:** 2026-08-22
**Scope:** omni-deployer (deploy.py dev) + HOST_OMNI_DIR data-dir mapping verification
**Workflow:** dev-executor (executor-only, auto_approve)

## Goal

Run `python3 deploy.py dev` in `/opt/workspace/omni-deployer` to successful
completion (stop omnidev → build dev images → start DBs → migrations → pretests
→ prepare.py → build all binaries → start services → register noop → Rust
integration tests → integration tests PASS 1 + PASS 2 → shared tool tests),
fixing any issue mid-run.

## Data-dir mapping verification (the acceptance gate)

The compose data-dir mount is now driven by `HOST_OMNI_DIR` (default
`/opt/omni`). This run must VERIFY the mapping is correct:

- **omnideploy (this deploy) must map to omni-stack**: `deploy.py generate_env`
  writes `HOST_OMNI_DIR=/opt/workspace/omni-stack` into omni.env; the omnideploy
  containers must bind `/opt/workspace/omni-stack` at `/opt/omni`.
  Verify: `grep HOST_OMNI_DIR /opt/workspace/omni-deployer/omni.env` and
  `docker inspect omnideploy-omniagent-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'`
  → must show `omni-stack -> /opt/omni`.
- **omnistable must map to omni-root** (the launcher stacks, NOT touched by
  deploy.py dev — dev mode stops ONLY omnidev, never omnistable):
  `docker inspect omnistable-omniagent-1 ...` → must show
  `omni-root -> /opt/omni`. omnistable container count unchanged before/after.
- **omni-deployer ships NO compose files** — the compose files live in
  omni-stack + omni-root (equal mirrors); deploy.py uses
  `OMNI_STACK_DIR/docker-compose.yml`.

## Safety invariants (HARD)

- `deploy.py dev` stops ONLY omnidev (MODE_STOP_EXCLUDE dev = {omnistable}).
  NEVER stop/restart omnistable containers; count before == after (7).
- omnideploy containers/volumes are the deploy's own scope.
- No real-LLM key changes; no omni-stack config changes beyond what
  deploy.py dev needs (it restores tracked config to HEAD in its finally).

## Task steps

1. Run `python3 deploy.py dev` in `/opt/workspace/omni-deployer`.
2. Fix any issue mid-run; commit + push fixes to nexuslbs/omni-deployer (or
   omni-stack/omni-root if the fix lands there) with clear messages.
3. Verify the data-dir mapping (above) — omnideploy → omni-stack,
   omnistable → omni-root, omnidev stopped (expected teardown).
4. Report each step's result + remaining blockers.

**Token-efficiency rules (MANDATORY — see omni profile MEMORY.md TOKEN EFFICIENCY):**
- NEVER query token_usage / threads token columns (Hermes monitors the budget).
- Run the deploy as ONE background command logging to a file, then
  `builtin_wait-task(task_id, timeout_secs=1800, tail=200)`; NEVER poll.
- After wait-task returns, read the log ONCE (combined `grep -c ALL.TESTS.PASSED`
  + `tail -60` in ONE call); NEVER re-read repeatedly.
- Read files once into notes; batch independent checks; bounded exploration (≤10).
- Notes/subtasks are fine — they prevent re-derivation; they are NOT waste.

## Acceptance criteria

- `deploy.py dev` exits 0 with "ALL TESTS PASSED" (149/0 + shared tool tests).
- omnideploy containers bind omni-stack at /opt/omni (HOST_OMNI_DIR).
- omnistable containers bind omni-root at /opt/omni; count unchanged (7).
- omni-deployer has no compose files; compose comes from omni-stack/omni-root.
- Any fix committed + pushed; summary lists results + remaining blockers.

## Non-goals

- No omnistable stack config changes; no real-LLM key changes; no changes to
  the omnidev/omnistable data-dir choice (omni-root stays).
