---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-15T15:26:27Z
created_at: 2026-08-15T15:26:27Z
expires_at: 2026-10-14T15:26:27Z
---# Memory: deploy-omni-stack-known-test-residue

omni-deployer's deploy.py (Step 0.5 pre-flight) whitelists exactly these tracked omni-stack files as "known test residue" and auto-restores them to HEAD at run start/end: config/actions.yml, config/channels.yml, config/plugins.yml, config/settings.yml, config/workflows.yml, config/remote.yml, config/tasks.yml, profiles/omni/wiki/relevant-index.md. Untracked plugins/ entries are test-created plugin residue that deploy.py also sweeps. Any OTHER dirty tracked file in omni-stack makes deploy.py refuse to run. As of 2026-08-15 the live omni-stack tree had exactly this residue (modified config/*.yml + untracked plugins/, remote.yml, settings.yml, workflows.yml, .taskj-channels.patch, two wiki Todo pages) — i.e. a normal post-test state, not user changes.