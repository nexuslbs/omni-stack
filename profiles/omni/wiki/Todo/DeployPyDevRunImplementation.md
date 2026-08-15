# Run "deploy.py dev" successfully in omni-deployer (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-15
**Scope:** omni-deployer (deploy script) + omniagent stack

## Goal

Run `python3 deploy.py dev` in `/opt/workspace/omni-deployer` so it completes
successfully — build from source, migrations, pretests, shared tool tests, full
stack start — fixing any issue that happens in the middle. The run **will stop
the omnidev stack — that is fine and expected**. It must **NOT stop the
omnistable stack**: that is the agent's own runtime; stopping it would kill the
task mid-run.

## Why (verified live 2026-08-15)

`shared.py:398-402` — `STOP_TARGETS`:

```python
STOP_TARGETS = {
    "omnidev": ["omnideploy"],
    "omnistable": ["omnideploy"],
    "omnideploy": ["omnidev", "omnistable"],   # ← deploy.py dev stops BOTH launchers
}
```

deploy.py (compose project "omnideploy") calls
`shared.stop_other_stacks("omnideploy")` (deploy.py ~line 386) before starting
its own stack, with the comment "deploy.py (project 'omnideploy') tears down
the launcher stacks (omnidev/omnistable) BEFORE starting its own — CI wants a
clean slate." That clean-slate intent is fine for CI, but the omnistable agent
RUNS on the omnistable stack. `deploy.py dev` stopping omnistable would kill
the agent's own postgres/omniagent containers mid-task. The task must make
`deploy.py dev` stop ONLY omnidev (acceptable collateral) and never omnistable.

## Verified inventory (do not re-derive)

- `shared.py:395` — `OMNI_STACK_PROJECTS = ["omnidev", "omnideploy", "omnistable"]`
- `shared.py:398-402` — `STOP_TARGETS` — the fix location: the `"omnideploy"`
  entry must NOT include `"omnistable"` (mode-aware: dev stops only omnidev;
  CI/hybrid clean-slate may be preserved).
- `shared.py:405-431` — `stop_other_stacks(current_project)` — matches by
  compose project label (`com.docker.compose.project`), `docker rm -f` + best
  effort network prune; unrelated containers never touched.
- `deploy.py:386-390` — `shared.stop_other_stacks("omnideploy")` call + the
  "CI wants a clean slate" comment.
- `deploy.py:446-470` — Step 2 (dev): build omniagent + dashboard images;
  Step 5 (dev): build db-migrations binary, run migrations, THEN pretests
  (SQLX_OFFLINE=false dev overlay, sqlx validates against the live migrated DB).
- `deploy.py:540-605` — Step 8a: register remote noop provider (needs omniagent
  running) — noop/test-tool-caller ONLY, never real LLM keys (user rule:
  "deploy.py tests NEVER use real LLM/keys — noop provider only").
- `deploy.py:10` — `python3 deploy.py dev` — "Dev mode (builds from source +
  shared tool tests)".
- Repo: `/opt/workspace/omni-deployer` (mounted into omnistable-omniagent-1),
  git remote `https://github.com/nexuslbs/omni-deployer.git`, branch `main`.

## Task steps (for the agent)

1. `cd /opt/workspace/omni-deployer`; confirm the current `STOP_TARGETS` in
   `shared.py`.
2. FIRST fix the deploy script so `deploy.py dev` does NOT stop omnistable
   containers (only omnidev is acceptable). Keep CI/hybrid clean-slate behavior
   (mode-aware) if that is the right shape. Commit + push to
   `nexuslbs/omni-deployer`.
3. Run `python3 deploy.py dev`. It will stop omnidev (fine). Fix ANY issue that
   happens mid-run (image build, migration, pretests, shared tool tests,
   startup, noop registration) until the run completes successfully.
4. Verify after the run: omnistable containers still up (`docker ps` shows
   omnistable-* running), deploy exited 0, noop provider registered.

## Verification gates

- `deploy.py dev` exits 0 after the full run (build → dbs → migrations →
  pretests → shared tool tests → start).
- `docker ps` after the run: omnistable-* containers still RUNNING (deploy must
  not have stopped them); omnidev-* may be stopped (expected).
- Deploy-script fix committed + pushed to nexuslbs/omni-deployer (main).
- No real LLM keys/secrets seeded (deploy dev uses noop/test-tool-caller only).

## Non-goals

- No workspace task / workspace-project routing — this is a NORMAL
  omniagent-dev kanban task (user: "No need for a workspace task, just a normal
  task").
- No changes to the omnistable stack's own config beyond what `deploy.py dev`
  needs to run cleanly.
- No real-secret seeding; no changes to omnidev behavior beyond the
  stop-targets fix.
