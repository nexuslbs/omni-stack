---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-10T02:43:16Z
created_at: 2026-08-10T02:43:16Z
expires_at: 2026-09-09T02:43:16Z
---# Memory: kanban-dispatch-ready-retired-fixed-5e9559d

Kanban "ready" status fully retired: commit 5e9559d on nexuslbs/omniagent origin/main fixes the last production write — src/server/kanban.rs dispatch_handler (step 6, ~line 2287) now calls update_kanban_task_status(&state.pool, &detail.id, "running") instead of "ready" (thread is created with workflow_step Some("running") immediately before, so this matches executor pickup). Verified: grep 'update_kanban_task_status.*"ready"' src/server/kanban.rs → no matches; only remaining "ready" mention is the invariant test assert!(!validate_status("ready")) at line 2477. Gates: cargo check/clippy -D warnings/test --lib (417 pass) all green. NOTE: `cargo fmt --check` STILL fails on origin/main at HEAD 5e9559d due to pre-existing violations in cfad5352 files (plugins/tools/filesystem/src/main.rs, plugins/tools/prompt/src/*.rs, src/agent/{context_dump,fail_thread,helpers,main_loop}.rs) — kanban.rs is fmt-clean; do not "fix" other files under a single-file task.