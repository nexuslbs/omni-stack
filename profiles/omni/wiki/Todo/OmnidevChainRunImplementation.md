# Run the omnidev chain (setup → test → agent → prepare) successfully (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-22
**Scope:** omni-deployer (omnidev.py) + the OMNIDEV stack
**Workflow:** dev-executor (executor-only, auto_approve — no tester/reviewer; the
executor's own verification IS the acceptance gate)

## Goal

Run the full omnidev chain, the 4 steps, in `/opt/workspace/omni-deployer` so
each completes successfully:

1. `python3 omnidev.py setup` — build/start/configure the omnidev stack
2. `python3 omnidev.py test` — comprehensive plugin/tool testing
3. `python3 omnidev.py agent` — send a math question via Mattermost and verify
   the agent answers correctly (expects `597`)
4. `python3 omnidev.py prepare` — create mm-kanban MM channel, register via
   `$new`, patch to opencode-go/deepseek-v4-flash + profile omni, enable
   opencode-go provider + all builtin tool MCPs

Fix any issue that happens in the middle. **Never stop the omnistable stack**:
that is the agent's own runtime (the task executor runs inside
`omnistable-omniagent-1`); stopping it would kill the task mid-run.

## Why this is safe to run from omnistable (verified live 2026-08-22)

- `shared.py:395` — `OMNI_STACK_PROJECTS = ["omnidev", "omnideploy", "omnistable"]`
- `shared.py:398-402` — `STOP_TARGETS = {"omnidev": ["omnideploy"], "omnistable":
  ["omnideploy"], "omnideploy": ["omnidev", "omnistable"]}` — omnidev.py setup
  (project "omnidev") stops ONLY omnideploy, never omnistable.
- `omnidev.py:27-38` — `Settings(project_name="omnidev",
  container="omnidev-omniagent-1", setup_channel="dev-channel", use_api=False)`.
  `use_api=False` = docker-exec mode: `oc()` runs `docker exec -i
  omnidev-omniagent-1 <cmd>` (shared.py:80-84), `oc_curl` curls
  `localhost:8080` via docker exec (shared.py:86-105).
- The task executor container (`omnistable-omniagent-1`) has:
  - docker CLI `/usr/local/bin/docker` + compose v5.4.0 (verified)
  - `/opt/workspace/omni-deployer` mounted (omnidev.py + secrets.env present)
  - docker socket access → can drive the omnidev stack containers
- Current omnidev stack state: only `omnidev-noop-provider-1`,
  `omnidev-toolbox-db-1`, `omnidev-toolbox-toolbox-1` are running; the main
  omnidev services (omniagent/postgres/mattermost) are DOWN — `setup` will
  (re)build and start them.

## Verified inventory (do not re-derive)

- `omnidev.py` subcommands (lines 82-107):
  - `setup` → `shared.setup()` + `patch_channel_to_deepseek()`
    (omnidev.py:94-96; patches the mattermost dev-channel to
    deepseek/deepseek-v4-flash — omnidev.py:43-67)
  - `agent` → `shared.agent()` (omnidev.py:97-98)
  - `test` → `shared._check_container()` + `shared.run_tests()`
    (omnidev.py:99-101)
  - `prepare` → `shared._check_container()` + `shared.prepare()`
    (omnidev.py:102-104)
- `shared.setup()` (shared.py:666-745): stop other stacks → generate env →
  stop own stack → build dev image (dev overlay) → start services →
  configure secret refs → create secrets from secrets.env → enable
  mattermost platform → configure mattermost (setup_channel="dev-channel",
  admin lucasbasquerotto) → run mattermost setup w/ readiness + retries →
  enable prompt plugin. Success marker: `Setup complete! Channel:
  dev-channel`.
- `shared.agent()` (shared.py:841-938): login testuser → find dev-channel →
  post `What is 15 * 37 + 42? Please show your work.` → wait for a NEW thread
  (since_id = latest before post) → require `597` in the last agent message
  (rejects noop canned echo). Success marker: `✅ AGENT TEST PASSED`.
- `shared.prepare()` (shared.py:943+): login admin → find/create mm-kanban →
  add bot/testuser/admin members → post `$new mm-kanban` as testuser → wait
  for omniagent registration (resource_identifier = MM channel id) → PATCH
  channel to opencode-go/deepseek-v4-flash/profile=omni (API uses bare yml
  field names since the Aug-19 rename — legacy `current_*` keys are silently
  ignored) → enable opencode-go provider → enable all builtin tool MCPs.
- Secrets: omni-deployer `secrets.env` present (deepseek/opencode keys are
  read from it; NO key is passed as an argument — shared.py:669-672).
- API secrets are sourced via `$secret:` refs configured in plugins.yml
  (shared.setup() `configure_secret_refs()`).

## Task steps (for the executor)

Run in `/opt/workspace/omni-deployer` inside the omnistable container
(`docker exec` into `omnistable-omniagent-1` — or run the commands directly
since the repo is mounted there). Use `python3 omnidev.py <step>` for each of
the 4 steps, IN ORDER: setup → test → agent → prepare.

1. **setup** — `python3 omnidev.py setup`
   - Expect: build + start omnidev stack, mattermost setup OK, channel
     patched to deepseek/deepseek-v4-flash, exit 0.
   - Gate: `Setup complete! Channel: dev-channel` in output; `docker ps`
     shows omnidev-omniagent-1/postgres-1/mattermost-1 up; omnistable-*
     container count UNCHANGED.
2. **test** — `python3 omnidev.py test`
   - Expect: `shared.run_tests()` passes (comprehensive plugin/tool testing).
   - Gate: exit 0; fix any failing test group by fixing the underlying issue
     (repo code) or the test, then re-run.
3. **agent** — `python3 omnidev.py agent`
   - Expect: math question posted, agent thread completes, `597` in the final
     message.
   - Gate: `✅ AGENT TEST PASSED` in output.
4. **prepare** — `python3 omnidev.py prepare`
   - Expect: mm-kanban channel created/registered, channel patched to
     opencode-go/deepseek-v4-flash, provider + builtin tool MCPs enabled.
   - Gate: exit 0; verify via API: `GET /channels` shows mm-kanban with
     provider opencode-go, model deepseek-v4-flash, profile omni.

**Safety invariants (HARD):**
- NEVER stop/restart the omnistable stack (`omnistable-*` containers). If a
  script would stop omnistable, FIX the script first (mode-aware
  STOP_TARGETS, like the a49286d deploy.py fix), commit + push to
  nexuslbs/omni-deployer, then run.
- Only omnideploy may be torn down (omnidev setup stops it — expected).
- No real LLM key changes to omnistable config; this task operates on the
  omnidev stack only.

**Long-running commands:** setup (build + start) can take 5-15 min. If a tool
call returns `status: processing` with a `task_id`, block on
`builtin_wait-task(task_id=<id>, timeout_secs=900, tail=2000)` immediately —
NEVER poll with other tools and NEVER pass `timeout` on docker_compose calls
(it kills the command).

**Reporting (dev-executor has NO tester/reviewer — your verification IS the
gate):** for each step, report the exact exit code + success marker. If a step
fails and you fix it, report root cause + fix commit. If you cannot fix
something, report exactly what remains and why (never soften a failure).

## Acceptance criteria

- All 4 steps exit 0 with their success markers (setup complete / tests pass /
  ✅ AGENT TEST PASSED / prepare OK).
- omnistable-* containers untouched throughout (count before == count after).
- Any code fix committed + pushed to nexuslbs/omni-deployer (or
  nexuslbs/omni-stack if the fix lands there) with a clear message.
- Summary lists each step's result and any remaining blockers.

## Non-goals

- No changes to the omnistable stack configuration.
- No changes to the omniagent/omni-dashboard source repos unless a test
  failure genuinely requires it (then commit + push + note it).
- No new features; this is an operational run-to-green task.
