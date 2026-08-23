# Unify Context Budgets: Remove Char Budgets, Token-Only (chars/4 fallback)

**Status:** IMPLEMENTED 2026-08-19 (task 12, task_18cd3920aeeea608; omnidev
board) — omniagent `bf2af90`, omni-stack `451a461`, omni-deployer `3386e1d`.
**Scope:** omniagent core (config + settings API), omni-stack settings.yml,
omni-deployer tests.py.

## What changed (final state, verified threads 48/49/51/52/53/54)

- **All char budgets removed everywhere** (`char_budget_soft/hard`, `SizeUnit`,
  `measure_size`): `git grep char_budget` → 0 hits in omniagent `src/` +
  `plugins/` and omni-stack `config/` + `plugins/`.
- **Budgets are GLOBAL SETTINGS in core** (user architecture decision v2 —
  supersedes the "prompt-plugin-only" scope of task 15):
  - `AgentConfig.char_budget_hard/soft` renamed → `token_budget_hard/soft`
    (`src/agent/config.rs`), read from settings keys
    `prompt_token_budget_hard` / `prompt_token_budget_soft` with **defaults
    soft 100000 / hard 500000** at BOTH load sites (`from_env`,
    `from_settings_yaml`) + both test defaults; `src/server/settings.rs`
    SettingMeta defaults flipped to 500000/100000 (the API defaults table).
  - `main_loop.rs` prune passes the renamed fields; `helpers.rs` doc comment
    updated.
- **omni-stack `451a461`**: `config/settings.yml` now sets
  `prompt_token_budget_hard: 500000` / `prompt_token_budget_soft: 100000`
  (was 100000/50000 — defaults flipped to match the user-pinned chain),
  `old_message_token_budget: 100000` already token-based.
- **omni-deployer `3386e1d`**: `scripts/tests.py` NameError fixes —
  `test_p7_idempotent` `CHAR_SOFT` → `_msgs_size_tokens(...) <= TOKEN_SOFT`
  (assertions now in token units under the deterministic chars/4 fallback);
  other `CHAR_HARD`-based tests reworked to token-budget assertions.
- **Fallback when no tokenizer**: chars/4 proxy (a 200K-char context counts
  as 50K tokens).
- **Budget fallback chain (user-pinned, see log 2026-08-19)**: model_config
  (models.yml) > provider (models.yml) > global settings defaults soft
  100000 / hard 500000; resolved by omniagent per thread and passed as
  compact-messages `soft_budget`/`hard_budget` params (tasks 15/16).
- `old_message_token_budget` (100000) stays as a token-based setting.

## Round 1 was REJECTED — lesson

First attempt (thread 48 executor): omniagent `360e998`, omni-deployer
`d9e2c66`, omni-stack `6bc9b99` — implemented token budgets ONLY inside the
prompt plugin, leaving core `char_budget_*` intact. Reviewer (thread 51)
independently grepped origin/main and REJECTED against the current task body
(SCOPE UPDATE v2: budgets are GLOBAL settings in core). Tester thread 49's
verdict (FAIL) was correct; the reviewer failed the thread (F1 executor
rework). Re-dispatch (thread 52) applied the missing core rename — APPROVED
(thread 54).

**Takeaway**: when a task body carries a "SCOPE UPDATE … SUPERSEDES" header,
verify the implementation against the CURRENT body, not the original text;
and testers/reviewers must re-grep origin/main, never trust executor
self-reports.

## Related

- `Reference/Budget-and-Context.md` (compaction mechanics, updated defaults)
- `Todo/CompactPrunePluginOwnershipImplementation.md` (task 15: prune moves
  into compact-messages; budgets passed as params)
- `Todo/ModelOverridesConfigImplementation.md` (task 16: models.yml feeds the
  fallback chain)
- `Todo/DeadCodeRemovalImplementation.md` (task 14: removes the last
  `old_message_char_budget` stragglers)
