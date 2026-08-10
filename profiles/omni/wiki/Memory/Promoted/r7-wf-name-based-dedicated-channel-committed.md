---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T20:52:32Z
created_at: 2026-08-09T20:52:32Z
expires_at: 2026-09-08T20:52:32Z
---# Memory: r7-wf-name-based-dedicated-channel-committed

R7-WF NAME-BASED FIX (committed+verified 2026-08-09 on nexuslbs/omni-deployer origin/main, replaces id-based commits 856730f/725aebe which were REJECTED): scripts/tests.py _wf_dedicated_channel() now resolves the wf-test omniagent channel BY NAME (platform=mattermost AND name='mattermost-test-channel') via GET {BASE}/channels — NO hardcoded id 35 / resource_identifier faownqu7 / name mattermost-faownqu7. If missing, _wf_bootstrap_test_channel() creates it: MM admin login (lucasbasquerotto/Mattermost_Fresh_Start_1) → find team 'omni' via /api/v4/users/me/teams → create MM channel test-channel (display_name 'Workflow Test Channel', type O) → add omnibot+admin members (tolerate HTTP 400 already-member) → POST '$new test-channel' post so omniagent poller creates the channel (wait up to 60s polling /channels for resource_identifier==mm_channel_id) → PATCH rename to 'mattermost-test-channel' → PATCH current_provider=noop/current_model=test-tool-caller (permanent). _wf_dedicated_channel asserts noop/test-tool-caller and FAILS LOUDLY (no fallback patching of any other channel). _wf_channel_restore no-op for orig=None. Verified: GROUP 22 run in omnistable-omniagent-1 created all wf_test_* threads on channel_id 35; kanban channel id=4 stayed opencode-go/deepseek-v4-flash before+after; tests 1,2,3,8 PASS, 4-7 FAIL on stale-image workflow-engine assertions (expected, not harness defect). MM admin API base: http://mattermost:8065 (also hardcoded in G12/G13/G14).