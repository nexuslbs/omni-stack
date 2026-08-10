---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T16:38:34Z
created_at: 2026-08-09T16:38:34Z
expires_at: 2026-09-08T16:38:34Z
---# Memory: omniagent-sqlx-cache-regeneration-rule

omniagent repo (/opt/workspace/omniagent): when you change any SQL in the Rust crates (e.g. INSERT/UPDATE in src/server/kanban.rs, src/db/threads.rs), the tracked `.sqlx/` offline cache MUST be regenerated (`cargo sqlx prepare --workspace` against a scratch DB with current schema, then commit the changed query JSON files). The Dockerfile/CI set `ENV SQLX_OFFLINE=true`, so CI builds validate queries against the cache only — a stale cache fails CI even though dev builds (`SQLX_OFFLINE=false` against a live DB) and the full test suite (413 tests) pass. Verified 2026-08-09: stale kanban_tasks INSERT/UPDATE caches (missing `assignee`/`workflow_id`) broke CI; fix commit 8c2468b regenerated .sqlx for omniagent + plugins/tools/query. Check `docker_compose(project_dir="/opt/workspace/omni-stack", env_file="/opt/workspace/omni-deployer/omnidev.env", command="exec", service="omniagent", args="cd /app && SQLX_OFFLINE=true cargo check --workspace")` to verify the CI path.