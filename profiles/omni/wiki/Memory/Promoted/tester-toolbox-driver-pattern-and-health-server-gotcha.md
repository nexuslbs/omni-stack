---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-19T19:03:34Z
created_at: 2026-08-19T19:03:34Z
expires_at: 2026-10-18T19:03:34Z
---# Memory: tester-toolbox-driver-pattern-and-health-server-gotcha

When running omni-deployer tests.py groups against the omnidev-toolbox (fresh HEAD binary), two gotchas (2026-08-19, wiki-skill task testing):

1. A stray `python3 /opt/workspace/omni-deployer/scripts/health_server.py` can be bound to 8080 inside the toolbox container (GET-only Python http.server). It answers /health (fools SERVER_UP checks) and returns 501 "Unsupported method ('POST')" + empty /mcp/tools for everything else. Kill it before starting the omniagent: `pgrep -f 'health_serve[r].py'` then kill by PID (avoid pkill -f with the plain name — the exec shell's own cmdline contains the pattern and pkill self-matches → exit 143).

2. tests.py module-level blocks (GROUP 9 mattermost container check, GROUP 11 prompt enable/disable/register wait, GROUP 12 setup calls) abort ANY --group run on a stack that lacks omnideploy mattermost/prompt-disable semantics. To run a single group, build a minimal driver: take tests.py, keep head (imports+constants+test() globals, everything before the 'GROUP 1:' banner), append the helpers slice (def _g24_mcp_execute → def _g24_size, plus def api_post_body), append the target test function defs + test() calls + sys.exit. Patch WORKSPACE to the container path (/workspace/omni-stack in toolbox). This bypasses all module-level group code; verified RC=0 for GROUP 45 and GROUP 25's search_wiki.