---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-10T02:01:07Z
created_at: 2026-08-10T02:01:07Z
expires_at: 2026-09-09T02:01:07Z
---# Memory: omniagent-origin-main-fmt-check-fails-cfad5352

As of 2026-08-10 (HEAD 8d86d2c), `cargo fmt --check` FAILS on nexuslbs/omniagent origin/main — but the violations are NOT from the R8-N commit 4c355fd (its fail_thread.rs is fmt-clean, verified via `git archive 4c355fd | rustfmt --check` = exit 0). Violations are in files from commit cfad5352 "Hermes Agent 2026-08-10 01:30" (smartness WS-2/3/4: src/agent/context_dump.rs, main_loop.rs, compact.rs, dump.rs, notes.rs, retry-notes test in fail_thread.rs lines ~1423-1438, plugins/prompt/src/main.rs, plugins/filesystem/src/main.rs) — landed AFTER the R8-N gate ran (FMT_EXIT=0 at 00:47). So the smartness workstream was pushed without passing `cargo fmt --check`. Any thread claiming "all gates pass" on current main must either exclude fmt or fix the formatting; R8-N itself is fmt-clean. Verified by blame: fmt-violating lines in fail_thread.rs are from cfad5352, not 4c355fd.