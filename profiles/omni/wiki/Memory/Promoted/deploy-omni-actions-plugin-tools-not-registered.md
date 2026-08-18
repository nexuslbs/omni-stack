---
type: memory
confidence: medium
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-18T07:21:21Z
created_at: 2026-08-18T07:21:21Z
expires_at: 2026-09-01T07:21:21Z
---# Memory: deploy-omni-actions-plugin-tools-not-registered

deploy.py dev (task_18ccb0a9ec956199 sibling, Aug 2026) 5 runs: pretests/build/migrations/api_tests(19)/plugin_tests(13) all pass; the persistent blocker is the REMOTE actions python MCP plugin in the deploy env: status=error "MCP server failed to start: binary may not have compiled successfully", actions_* tools never register → GROUP 37/40/41 fail. Evidence: python3 server.py process alive in /opt/omni/plugins/tools/.remote/actions/tools/actions/; manual MCP stdio probe of server.py returns initialize+tools/list with the 3 tools; but omniagent logs NEVER show "MCP server 'actions' connected" or "Hot-reloaded N external tool(s) from 'actions'". install-git handler does NOT call reload_tool_plugin (only /install and /reinstall do — src/server/plugins_install.rs:146/253); the 2s periodic discover tick only logs config load, never spawns new servers. Fix likely in omniagent (spawn/register remote plugin tools after install-git, or ensure reload/restart registers them), or check omni-plugins tools/actions/server.py configure-method handling.