---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T18:40:22Z
created_at: 2026-08-09T18:40:22Z
expires_at: 2026-09-08T18:40:22Z
---# Memory: group22-deployed-omnistable-image-stale-r7-d4

GROUP 22 (workflow integration tests) is fully written and committed to nexuslbs/omni-deployer at HEAD 008942a (2026-08-09 17:52, pushed, tree clean). It runs via `COMPOSE_PROJECT_NAME=omnistable python3 -u /opt/workspace/omni-deployer/scripts/tests.py --group 22_workflow` inside the omnistable-omniagent-1 container (docker_compose MCP: project_dir=/opt/workspace/omni-stack, env_file=/opt/workspace/omni-deployer/omnistable.env, service=omniagent). The `--group` arg sets TEST_FILTER (function-name substring). DO NOT run without COMPOSE_PROJECT_NAME=omnistable — tests.py `_check_mm_container()` defaults to project 'omnideploy' (0 containers) and crashes.

Against the DEPLOYED omnistable image: T1-3 + T8 PASS (workflow_id plumbing, step threads, D9 done-only gate all live), but T4-T7 FAIL with a consistent pattern: the deployed engine routes ALL executor/tester failures straight to `review` with comment "Tester passed (thread #N). Task in review (manual review — no reviewer role)." — no running→running retry, no `blocked` even with clear_executions_on_review=false, no interruption rerun, workflow_state (executions counter) stays NULL. Manual repro with retries=3 confirmed: single thread, single running→review transition.

Root cause: the deployed image is an INTERMEDIATE Phase-4-era engine (comment string matches kanban_updater.rs line 227, added in 4b6b234 2026-08-06) that predates the R7-D4/D5 engine fixes now on omniagent main @ 8c2468b: b540e89 (executor self-fail at 'running' → rerun), invalid-caller workflow_step → blocked (route_fail_tool F1/F2 in src/agent/fail_thread.rs), D7 retry-limit review-vs-blocked per clear_executions_on_review (guard_at_retry_limit), and interruption rerun. Current source implements exactly what the tests assert, so the TESTS ARE CORRECT — the fix is a CI image rebuild + redeploy of omnistable-omniagent-1 (NOT test changes, NOT faking a pass). Re-run `--group 22_workflow` (then GROUP 21: `--group 21`) after the image is rebuilt; expect all green.