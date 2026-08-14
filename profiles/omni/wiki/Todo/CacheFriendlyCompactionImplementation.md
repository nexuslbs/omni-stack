# Cache-Friendly Compaction: Stable Summary Block (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-14
**Scope:** omniagent (prompt plugin, `plugins/tools/prompt`)

## Goal

Make compaction **cache-friendly**: when the compact-messages tool fires, it must
NOT rewrite the entire message prefix. Instead it produces a **stable summary
block** — a frozen system message at a fixed position that is reused verbatim
(byte-identical) on subsequent calls, with only the conversation tail appending
after it. This preserves DeepSeek prefix caching across iterations.

## Why (verified live 2026-08-14)

- **Cache is dead:** `cached_tokens` frozen at **12,032** while prompt grows
  72K→86K tokens. Only the system prompt + static prefix ever matches — the
  entire message history is a cache miss on every LLM call.
- **Compaction fires EVERY iteration:** container logs show
  `[context] Condensed messages via prompt_compact-messages: N → M`
  on every single iteration (e.g. 149→147, 150→149, 160→158, 160→159…,
  15:25–15:36). The log line only fires when the tool returned a messages
  array (`src/agent/main_loop.rs:568` + `:592`) — so real compaction (not
  no-op calls) happens every call.
- **Root trigger:** the plugin's OWN config (root `plugins.yml` prompt section)
  is `char_budget_hard: 100000` / `char_budget_soft: 50000` /
  `token_budget_hard: 100000` / `token_budget_soft: 50000`, with
  `tokenizer_encoding=""` → measures **chars**, hard = **100K chars**. Live
  request dump `20260814_141224` shows a thread at **313 messages / 501,032
  chars** — **5× over the hard budget**, so the tool legitimately compacts
  every iteration.
- **Mechanism kills the prefix:** `handle_compact_messages`
  (`plugins/tools/prompt/src/main.rs:1599`) drains old assistant tool-call
  pairs into inline `[compact: name()…]` markers **scattered at their original
  positions** and DELETES the tool messages (`del messages[idx+1:tool_end]`,
  Python port; Rust equivalent). Deleting from the middle shifts every
  subsequent byte → the common prefix ends at the first drained message →
  entire tail is a cache miss. The markers are also recomputed each iteration
  as more messages drain, so the array never stabilizes.

## Current correct behavior (do not regress)

- The tool already honors the null-contract:
  `main.rs:1704-1714` — returns `"messages": null` when nothing was compacted;
  the core applies the result only when it is an array (`main_loop.rs:568`).
- `was_compacted` / `before_count` / `after_count` plumbing is consumed by the
  core for the compaction-notice system message.

## Design direction (executor picks the cleanest implementation)

1. **Fixed-position summary block.** On compaction, build ONE system message
   (e.g. marker `=== Compaction Summary ===`) inserted at a **fixed index**
   (right after the main system prompt). Everything before it (system prompt +
   any earlier stable content) is never touched.
2. **Frozen until next compaction.** Once written, the summary content is
   reused **verbatim** on every subsequent call. Only newly-drained content
   folds into it at the NEXT compaction event. Between compactions the array
   is `[system][frozen summary][growing tail]` — the prefix
   `[system][frozen summary][tail-so-far]` is byte-identical across calls, so
   DeepSeek caches it; only the newest appended messages are uncached.
3. **Replace, don't scatter.** The drained region is replaced by the single
   summary block; the remaining tail keeps its relative order and is appended
   after the block. Avoid per-message inline markers at scattered positions.
4. **Keep the null-contract.** No drain → `"messages": null` → core unchanged.
5. **Budget alignment is a prerequisite.** The design only pays off if
   compaction stops firing every iteration. Align the plugin's char/token
   budgets with the core's (`settings.yml` `prompt_char_budget_hard: 500000` /
   `soft: 350000`; `prompt_token_budget_hard: 350000` / `soft: 200000`) and/or
   set `tokenizer_encoding: gpt-4` in the plugin config so real tokens are
   measured. State the chosen values in the PR.

## Non-goals / DO NOT CHANGE

- Do NOT change the core's apply-logic contract in `src/agent/main_loop.rs`
  (apply iff array present).
- Do NOT change `prune_old_tool_results` (Layer-3 core pruning, separate
  mechanism, `src/agent/helpers.rs`) or its budgets.
- Do NOT touch the `prompt_generate` tool, system-prompt assembly, or the
  memory/skills/wiki guidance layers.
- Do NOT modify the DB schema or kanban workflows.

## Verification gates (BARE canonical commands, run in the dev container)

```bash
cargo check --workspace --all-targets
cargo test --workspace
cargo fmt --check
```

- Unit test: with no drain (small conversation), consecutive calls return
  `messages: null` and the message array is byte-identical.
- Unit test: after one compaction, two consecutive non-compacting calls
  produce identical prefixes `[system][summary][tail]` up to the tail.
- Unit test: a second compaction with new drained content produces a summary
  that is a strict superset of the first (frozen block property).
- Live check (omnistable, after deploy): `cached_tokens` in DeepSeek usage
  grows with prompt size instead of staying frozen at ~12K.

## Related

- `references/prompt-plugin-config-and-budgets.md` (plugin config wiring)
- `references/token-consumption-analysis.md` (cache-hit measurement)
- Task `task_18cbb20c4a3a43c4` (LLM client transport hardening — separate)
