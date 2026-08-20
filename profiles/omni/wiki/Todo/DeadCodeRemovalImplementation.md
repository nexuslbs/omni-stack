# Dead Code Removal — Implementation

**Status:** IMPLEMENTED 2026-08-19 (task 14, executor thread 58 done &
pushed; tester #60 PASS / reviewer #61 APPROVE (in-window)) — omniagent `614a3dd`.
**Date:** 2026-08-19
**Scope:** omniagent repo only (Rust core + builtin plugins)

## Goal

Remove leftover dead code so the codebase stays honest and the
`#[allow(dead_code)]`/test-only leftovers that nothing calls don't accumulate.
User-flagged anchor: `get_recent_summaries()` in `src/db/summaries.rs`.

## Verified facts (do not re-derive — greps from 2026-08-19)

- **`get_recent_summaries()`** — `src/db/summaries.rs:36`, annotated
  `#[allow(dead_code)]`, NOTHING calls it (the summary read path used by
  prompt_generate is its own `get_latest_summary`). DEAD — remove.
- **`condense_messages()`** — `src/agent/helpers.rs:594`. Legacy whole-context
  condenser (separate system msgs / keep last N turns / compact metadata block
  / trim to `old_message_char_budget`). **Called ONLY by its own unit tests**
  (`helpers.rs:1451–1518`). The live main loop does NOT use it: Layer 2 =
  prompt plugin `compact-messages` MCP tool (main_loop.rs:800–836), Layer 3 =
  `prune_old_tool_results` (main_loop.rs:843–855). DEAD (test-only) — remove
  function + tests. This also closes the "legacy condense_messages decision
  open" design note from the budget-unification task.
- **`old_message_char_budget`** — parsed by the prompt plugin
  (`plugins/tools/prompt/src/main.rs:162`) but NEVER consumed by the plugin;
  whitelisted in `src/server/settings.rs:180`; only other reference is the dead
  `condense_messages` docstring (`helpers.rs:590`). Its only consumer is dead.
  ⚠️ **Coordinate with the budget-unification task (task 12, runs before this
  one):** it removes ALL char budgets incl. `old_message_char_budget` from
  plugin + settings. If task 12 landed, just verify 0 remaining references; do
  not double-remove.
- General sweep targets: other `#[allow(dead_code)]` occurrences, unused pub
  fns / imports / struct fields flagged by clippy, unused settings whitelist
  keys, test-only helpers with no production caller.

## What was delivered (executor thread 58)

**Commit `614a3dd`** — `chore(dead-code): remove get_recent_summaries,
condense_messages + sweep (no behavior change)` — 393 deletions / 3
insertions, pure deletion-only, verified: local HEAD == origin/main
(`git fetch` shows bf2af90..614a3dd), working tree clean:

| Symbol | Location | Removed |
|---|---|---|
| `get_recent_summaries` (+`#[allow(dead_code)]`) | src/db/summaries.rs:36 | ✓ + its tests |
| `condense_messages` (+ its unit tests) | src/agent/helpers.rs:594 | ✓ (grep proved no production caller) |
| stale `old_message_char_budget` stragglers | plugin config / settings.rs whitelist / helpers docstring | ✓ (task 12 removed most; 0 remaining after sweep) |
| other zero-caller `#[allow(dead_code)]`, clippy-unused imports, unused settings whitelist keys | general sweep | ✓ |

## Requirements (original)

1. Remove `get_recent_summaries()` (+ its `#[allow(dead_code)]`; drop any
   tests that only exercised it). ✓
2. Remove `condense_messages()` + its unit tests (helpers.rs:1451–1518) —
   BEFORE deleting, `grep -rn condense_messages` across src/ AND plugins/ to
   prove no production caller remains (expected: only the tests + docstring). ✓
3. After task 12 lands, grep `old_message_char_budget` — 0 hits expected. ✓
4. **General dead-code sweep**: `#[allow(dead_code)]` greps, clippy warnings,
   unused imports, unused settings keys — only zero-caller symbols removed. ✓
5. **Safety rule**: only remove symbols with no callers ANYWHERE; if
   referenced by an external/remote plugin or the dashboard, NOT dead — leave
   and note why. ✓
6. No behavior change to live paths (`prune_old_tool_results`, compact tool,
   main loop layers) — deletion-only. ✓

## Non-goals / DO NOT CHANGE

- Do NOT refactor or "improve" any live code path while deleting (no
  drive-by changes; separate PR if needed).
- Do NOT remove public API surface used by plugins/dashboard.
- Do NOT touch `search_wiki`, wiki vectorizer, or the wiki data source.

## Verification gates

- `grep -rn "get_recent_summaries\|condense_messages" src/ plugins/` → 0 hits. ✓
- `grep -rn "old_message_char_budget" src/ plugins/` → 0 hits. ✓
- `cargo check` / `cargo clippy -- -D warnings` / `cargo test` / `cargo fmt
  --check` all clean in omniagent repo. ✓ (executor-verified)
- Zero NEW `#[allow(dead_code)]` annotations introduced by the sweep. ✓
- `deploy.py dev` passes (omn
