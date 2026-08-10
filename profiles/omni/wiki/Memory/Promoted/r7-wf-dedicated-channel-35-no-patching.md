---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T20:20:19Z
created_at: 2026-08-09T20:20:19Z
expires_at: 2026-09-08T20:20:19Z
---# Memory: r7-wf-dedicated-channel-35-no-patching

R7-WF FIX (committed to nexuslbs/omni-deployer origin/main, HEAD 725aebe, 2026-08-09): scripts/tests.py NEVER patches channels anymore. GROUP 22 and G12/G13/G14/G16 use the DEDICATED wf-test channel — omniagent channel id=35, name mattermost-faownqu7, resource_identifier faownqu7nb8t9q7nhn7q867too (MM 'wf-test', team omni) — which is PERMANENTLY noop/test-tool-caller. _wf_channel_patch() returns (35, None) via _wf_dedicated_channel(), which looks the channel up and asserts provider/model, failing loudly if missing (no fallback patching — 2026-08-09 incident: a never-restored patch left kanban channel id=4 on noop and falsely completed task R7-D). _wf_channel_restore no-ops on orig=None. GOTCHA: GROUP 12/14/13b module-level dispatch blocks run unconditionally on EVERY tests.py invocation, so _wf_channel_patch/_wf_dedicated_channel must be defined BEFORE the GROUP 12 section (defs at ~line 3722/3738), not near GROUP 22. Verification command: COMPOSE_PROJECT_NAME=omnistable python3 -u /opt/workspace/omni-deployer/scripts/tests.py --group 22_workflow (exec into omnistable-omniagent-1 via docker_compose with omnistable.env). GROUP 22 wf tests 1/2/3/8 pass; wf 4/5/6/7 fail on stale deployed image (R7-D4/D5 retry/blocked/clear_executions behaviors not in the image) — expected, not a harness defect. Kanban channel id=4 must stay opencode-go/deepseek-v4-flash; wf-test id=35 stays noop/test-tool-caller.