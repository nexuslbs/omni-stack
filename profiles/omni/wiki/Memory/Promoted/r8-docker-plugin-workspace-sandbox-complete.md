---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T22:16:52Z
created_at: 2026-08-09T22:16:52Z
expires_at: 2026-10-08T22:16:52Z
---# Memory: r8-docker-plugin-workspace-sandbox-complete

R8 (docker plugin sandbox: compose/env files anywhere inside workspace_dir) is COMPLETE on nexuslbs/omniagent origin/main. The change lives in plugins/tools/docker/src/main.rs, committed by thread #204 as a721230 "feat(docker-plugin): allow compose/env files anywhere inside workspace_dir (R8)" (+122/-6, ONLY that file). Current HEAD 8c2468b, tree clean, ahead=0. Behavior: resolve_project_file(file, project_dir, configured_workspace, what) accepts absolute paths OR relative-to-project_dir (back-compat); final canonical check is starts_with(configured_workspace), NOT starts_with(project_dir); ..-escape and absolute-outside-workspace are rejected; is_file() check kept; doc comment at file top updated; 4 unit tests added (env_file outside project_dir accepted, absolute-in-workspace accepted, outside-workspace rejected, relative-in-project_dir back-compat). VERIFIED GATES (omnidev-omniagent-1): cargo fmt --check && cargo clippy -p mcp-server-compose -- -D warnings && cargo test -p mcp-server-compose — all 12 tests pass. CRITICAL NAME FACT: the docker plugin crate package name is mcp-server-compose (Cargo.toml name), NOT mcp-server-docker — `cargo clippy -p mcp-server-docker` fails with "package ID specification did not match any packages".