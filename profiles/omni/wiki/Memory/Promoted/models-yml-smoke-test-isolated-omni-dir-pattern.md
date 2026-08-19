---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-19T23:16:58Z
created_at: 2026-08-19T23:16:58Z
expires_at: 2026-10-18T23:16:58Z
---# Memory: models-yml-smoke-test-isolated-omni-dir-pattern

# Memory: isolated OMNI_DIR live-smoke pattern for omniagent API changes (models.yml task, 2026-08-19)

To live-smoke omniagent HTTP API changes without touching the real stack: run the debug binary with an ISOLATED OMNI_DIR (e.g. /app/.smoke-omni) + the dev-toolbox postgres, PORT=18081, HOST=127.0.0.1. Pattern (verified working for the /api/models feature):

1. `.smoke-omni/config/` holds models.yml (plugin-less provider my_provider_01 + deepseek override), settings.yml (prompt_token_budget_hard/soft), plugins.yml (minimal, 38 bytes — no provider entries so the smoke is plugin-free).
2. Smoke script (python): start_server() = subprocess.Popen([BIN], env with OMNI_DIR/DATABASE_URL/PORT/HOST), poll /health until 200, then run checks: GET /api/models shows providers deepseek+my_provider_01; GET /api/plugins providers list includes the synthetic plugin-less provider; provider detail config_schema default_model.allowed_values == models.yml models list (deepseek override); PUT /api/models persists (re-GET shows new models); then RENAME the models.yml away and re-check: GET /api/models returns {} and provider list has NO plugin-less provider (absent file = zero behavior change).
3. GOTCHAS: (a) the debug binary is STALE after source edits — must `cargo build` (dev profile, 1-2 min) before smoke or the new routes 404; (b) urllib json.load on /health fails — health returns plain text, use raw=True for that endpoint only; (c) kill leftover omniagent PIDs (pgrep -af omniagent) before re-running or the OLD binary keeps port 18081 and answers 404 for new routes; (d) run via `docker compose -f /opt/workspace/dev-toolbox/docker-compose.yml exec -T builder python3 /app/.smoke-omni/smoke.py` — the dev-toolbox compose mounts /opt/workspace/omniagent:/app and /opt/workspace/omniagent/target:/target, CARGO_TARGET_DIR=/target, and its postgres service gives a live DB (SQLX_OFFLINE=false builds validate queries).
4. Dashboard smoke: `node --import tsx --test tests/import.test.ts tests/models.test.ts` in the omni-dashboard toolbox; the dashboard server tests (routes.test.ts OmniDashboard API suite) FAIL when no live dashboard server runs (dash:REFUSED) — expected in the isolated toolbox, not a code regression.