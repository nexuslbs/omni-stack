---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-09T20:30:38Z
created_at: 2026-08-09T20:30:38Z
expires_at: 2026-09-08T20:30:38Z
---# Memory: r7-wf-tester-verified-no-patching-identical-4of8-baseline

R7-WF TESTER VERIFICATION (thread #448, 2026-08-09, harness HEAD 725aebe on nexuslbs/omni-deployer origin/main, tree clean): Ran GROUP 22 workflow suite in omnistable-omniagent-1 (COMPOSE_PROJECT_NAME=omnistable python3 -u /opt/workspace/omni-deployer/scripts/tests.py --group 22_workflow). Result: tests 1,2,3,8 PASS; tests 4,5,6,7 FAIL with EXACTLY the same signatures as the PRE-FIX baseline (tester #412 log committed at 665c791: test 4 expected retry running->running got running->review 'Tester passed'; test 5 expected blocked got review; test 6 expected >=2 threads got 1 completed; test 7 clear_executions_on_review=false expected blocked got review). So NO regression from R7-WF. The 4 failures are pre-existing, caused by the STALE deployed omnistable omniagent image (lacks R7-D workflow-executor behavior: retry-on-fail, blocked-on-missing-tester, interruption rerun, clear_executions_on_review) — NOT channel related. PROOF THE FIX WORKS: pre-fix log line 59 = '[channel 4 patched to noop/test-tool-caller for G12]' (harness patched kanban channel!); post-fix log line 59 = '[using dedicated wf-test channel 35 for GROUP 12]', zero 'patched' lines anywhere, and GROUP 22 task dumps show channel_id 35. Kanban channel id=4 remained opencode-go/deepseek-v4-flash BEFORE and AFTER the full run; channel id=35 stayed noop/test-tool-caller. Verdict: PASS for task scope (never patch; use dedicated wf-test channel).