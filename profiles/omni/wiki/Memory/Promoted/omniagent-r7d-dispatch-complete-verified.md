---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T20:03:02Z
created_at: 2026-08-09T20:03:02Z
expires_at: 2026-09-08T20:03:02Z
---# Memory: omniagent-r7d-dispatch-complete-verified

R7-D (core POST /kanban/dispatch API + dispatcher thin-caller) is COMPLETE and merged on omniagent origin/main. Key commits: 9ed7faf (server-side dispatch endpoint persists resolved task template to threads.template), 6790e4c (plugins/tools/actions kanban_dispatcher = thin HTTP caller of POST {omniagent_url}/kanban/dispatch, url from config.omniagent_url fallback http://localhost:8080, no direct SQL), 556cd0d (R7-D3: workflow_id + workflow_step='running' threaded through ThreadCauseParams), 8c2468b (.sqlx cache regen). Location: src/server/kanban.rs dispatch_handler + route .route("/kanban/dispatch", post(dispatch_handler)) + unit tests dispatch_no_eligible_tasks / dispatch_deps_gate_skips_unsatisfied / dispatch_template_and_profile_resolution (pure-function tests, no DB). Verified 2026-08-09 in omnidev container: cargo fmt --check clean, cargo clippy -p omniagent -p mcp-server-actions -- -D warnings clean, cargo build -p mcp-server-actions OK, cargo test -p omniagent --lib dispatch 3/3 pass, tree clean ahead=0. DB-side dispatch behavior covered by omni-deployer GROUP 22 integration tests, not by in-crate tests. Do NOT re-implement R7-D.