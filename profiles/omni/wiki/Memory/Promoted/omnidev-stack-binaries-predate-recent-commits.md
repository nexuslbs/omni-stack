---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: ["task_514_102"]
last_verified_at: 2026-08-10T03:10:53Z
created_at: 2026-08-10T03:10:53Z
expires_at: 2026-09-09T03:10:53Z
---# Memory: omnidev-stack-binaries-predate-recent-commits

# Memory: omnidev-stack-binaries-predate-recent-commits

As of 2026-08-10 ~03:15, the RUNNING omnidev compose stack (project_dir /opt/workspace/omni-stack, env /opt/workspace/omni-deployer/omnidev.env) does NOT run the recent omniagent commits: the omniagent container's PID 1 (/target/release/omniagent, baked into the image) started Sun Aug 9 15:54:49 — BEFORE R8 (589101a), R8-N (4c355fd), kanban-ready fix (5e9559d), and the smartness WS commits (f32e760..8d86d2c) landed. The /app bind mount has current source and a fresh /app/target/release/omniagent (rebuilt Aug 10 03:02), but the live process uses the image's baked binary. CONSEQUENCE: scripts/tests.py integration groups (e.g. 13/14/22) executed against the omnidev stack validate OLD code — unit tests run via `docker_compose exec omniagent 'cd /app && cargo test ...'` (workspace root, deps prebuilt) are the reliable gate for landed changes. Rebuilding/restarting the omniagent service mid-thread kills the executing agent — never `docker_compose up -d --build omniagent` from inside a thread. Verified by tester thread 514.