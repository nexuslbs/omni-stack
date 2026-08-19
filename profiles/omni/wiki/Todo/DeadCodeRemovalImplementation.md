# Dead Code Removal — Implementation

**Status:** Todo (task 14 — LAST in the serial chain, after wiki skill task)
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

## Requirements

1. Remove `get_recent_summaries()` (+ its `#[allow(dead_code)]`; drop any
   tests that only exercised it).
2. Remove `condense_messages()` + its unit tests (helpers.rs:1451–1518) —
   BEFORE deleting, `grep -rn condense_messages` across src/ AND plugins/ to
   prove no production caller remains (expected: only the tests + docstring).
3. After task 12 lands, grep `old_message_char_budget` — 0 hits expected
   (plugin config, settings.rs whitelist, helpers docstring). If any remain,
   remove them.
4. **General dead-code sweep**: `grep -rn "#\[allow(dead_code)\]" src/ plugins/`,
   `cargo clippy` warnings, unused imports (`cargo fix` or manual), unused
   settings keys in `src/server/settings.rs` whitelists (check settings.yml +
   runtime /settings for live usage first — a key may be whitelisted because
   it's user-set). Remove only what has ZERO callers.
5. **Safety rule**: only remove symbols with no callers ANYWHERE (core +
   builtin plugins + omni-plugins python + dashboard TS if referenced). If a
   symbol is referenced by an external/remote plugin or the dashboard, it is
   NOT dead — leave it and note why.
6. No behavior change to live paths (`prune_old_tool_results`, compact
   tool, main loop layers) — this task is deletion-only.

## Non-goals / DO NOT CHANGE

- Do NOT refactor or "improve" any live code path while deleting (no
  drive-by changes; separate PR if needed).
- Do NOT remove public API surface used by plugins/dashboard.
- Do NOT touch `search_wiki`, wiki vectorizer, or the wiki data source.

## Verification gates

- `grep -rn "get_recent_summaries\|condense_messages" src/ plugins/` → 0 hits.
- `grep -rn "old_message_char_budget" src/ plugins/` → 0 hits (after task 12).
- `cargo check` / `cargo clippy -- -D warnings` / `cargo test` / `cargo fmt
  --check` all clean in omniagent repo.
- Zero NEW `#[allow(dead_code)]` annotations introduced by the sweep.
- `deploy.py dev` passes (omni-deployer, dev-flavor) — regression gate.
- Live smoke on omnidev: agent thread runs normally (no compaction/pruning
  regressions).

## Deliverable

- omniagent commit(s) with the removals + commit SHAs + grep/clippy/test
  evidence in the task thread. Follow the standing release loop: tasks →
  deploy.py dev → main → stable (never push stable while omnistable tasks run).
