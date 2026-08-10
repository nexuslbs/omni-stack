---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-10T02:01:07Z
created_at: 2026-08-10T02:01:07Z
expires_at: 2026-09-09T02:01:07Z
---# Memory: r8-n-kanban-blocked-fix-verified

R8-N fix (no-workflow interrupted/failed threads → kanban task on 'blocked', NOT zombie 'running') is VERIFIED on nexuslbs/omniagent. Commit 4c355fd "fix(agent): no-workflow interrupted/failed threads land kanban task on 'blocked' (R8-N)" is on origin/main (ancestor of HEAD 8d86d2c, tree clean), touches ONLY src/agent/fail_thread.rs (+329). Code: RerunKind::Failed && !has_wf → final_status="blocked"; RerunKind::Interrupted && !has_wf → final_status="blocked"; workflow paths unchanged (interrupted reruns same step, failed reruns executor, task stays 'running'). Verified first-hand by tester thread #504: 4 DB-backed ignored tests (agent::fail_thread::tests_r8n_no_workflow_blocked) PASS against live omnidev DB — no_workflow_failed/interrupted_lands_blocked (assert result None + task status 'blocked' + history "Moving kanban task to \"blocked\" status due to no workflow"), workflow_failed_reruns_executor, workflow_interrupted_reruns_same_step. Tests self-clean (0 leftover r8n-* rows in kanban_tasks/threads after run). Gates on current tree: cargo test --package omniagent --lib = 417 passed/0 failed/5 ignored; cargo clippy --workspace --all-targets -- -D warnings = clean. Run command: docker_compose(project_dir=/opt/workspace/omni-stack, compose_file=docker-compose.dev.yml, env_file=/opt/workspace/omni-deployer/omnidev.env, service=omniagent).