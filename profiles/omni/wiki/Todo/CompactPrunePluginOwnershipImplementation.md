# Compact + Prune + Budget → Prompt Plugin Only — Implementation

**Status:** Todo (task 15 — LAST in the serial chain, after dead-code removal)
**Date:** 2026-08-19
**Scope:** omniagent repo (core Rust + prompt plugin) — architecture fix

## Goal

Context management must be the **prompt plugin's** job. Today the core engine
has a second, parallel pruning mechanism (`prune_old_tool_results` in
main_loop.rs Layer 3) with its own budgets — code smell. A user must be able to
write a **custom prompt plugin** that implements compaction/pruning in a
completely different way, as long as the plugin interface stays the same.
Therefore: **no budgets in core, no tool pruning in core** — budgets live only
in the prompt plugin config; tool-result pruning moves INTO the
compact-messages tool. Interface changes are allowed if needed (e.g. the tool
must know which messages are tool results).

## Verified facts (do not re-derive — greps from 2026-08-19)

- Core Layer 3: `helpers::prune_old_tool_results` called from
  `src/agent/main_loop.rs:843-855` EVERY iteration with
  `PruneConfig { hard_budget: cfg_snapshot.char_budget_hard,
  soft_budget: cfg_snapshot.char_budget_soft, read_keep_last,
  read_excerpt_chars, auto_note_max_chars, auto_note_entry_chars }`
  (config.rs:115/118, settings keys `prompt_char_budget_hard/soft`).
- Core Layer 2: prompt plugin `compact-messages` MCP tool called every N
  iterations (main_loop.rs:800-836) — the designated context manager.
- Prompt plugin `handle_compact_messages` (plugins/tools/prompt/src/main.rs:1679)
  receives `messages: Vec<ChatMessage>` (JSON) and compacts them.
- `ChatMessage` (src/llm/mod.rs:550) carries `role`, `content`,
  `tool_call_id: Option<String>` (tool results), `tool_calls` (assistant),
  `name: Option<String>` (tool result name), `reasoning_content`. → Tool
  results ARE identifiable inside the plugin (role="tool" or tool_call_id/name
  present); read-type results identifiable by tool `name` (filesystem_read etc.).
- Core prune behavior to preserve: (a) keep last N read-type results in full
  (`read_keep_last`), (b) excerpt older ones (`read_excerpt_chars`), (c)
  auto-note them to the thread's `notes.md`/`auto-notes.md`
  (`auto_note_max_chars`, `auto_note_entry_chars` — the thread-700 re-read
  death-spiral fix), (d) hard=trigger/soft=reduction-target gate.
- `old_message_char_budget` / `old_msg_budget`: char-based, its only consumer
  (legacy `condense_messages`, helpers.rs:594) is dead — removed by the
  dead-code task (14). Do NOT resurrect it.
- Budget-unification task (12, runs before this) removes char budgets and
  keeps ONLY token budgets in the prompt plugin (chars/4 fallback when no
  tokenizer). Core budget fields are NOT renamed there (deferred to this task
  for removal).

## Architecture rule (user, 2026-08-19 — do NOT re-litigate)

- **No global settings budget.** No `prompt_*_budget_*` keys in settings.yml /
  settings.rs whitelist / /settings API.
- **No tool pruning in core.** main_loop.rs has NO prune call, NO PruneConfig,
  NO budget fields in AgentConfig.
- The prune MAY exist, but **as part of compact-messages** (the prompt plugin),
  which knows which messages are tool results.
- A custom prompt plugin can do context management completely differently;
  only the plugin interface binds it. If the interface must change (e.g. prune
  needs to know which messages are tool results or needs thread_dir for
  auto-notes), change it — documented in plugin.json.

## LLM cache requirements (user directive 2026-08-19 — do NOT re-litigate)

Context management directly shapes the prompt PREFIX, which is what DeepSeek's
prefix cache keys on. The compact+prune refactor MUST NOT degrade the cache —
it should IMPROVE it. Expected cache hit ratio ≥ 95% (target: higher).

Reference numbers (user, 2026-08-19):
- Hermes 2026-08-02: 311M tokens cache hit / 5M miss (98.4%).
- omniagent 2026-08-18: 252M hit / 11M miss (95.8%) — user expected <5M misses.
- Live omnistable baseline (threads table, this day): 7-day = 94.4%
  (126.4M input / 119.3M cached); 08-18 = 93.8%; 08-19 = 94.6% — BELOW the 95% target.

Cache mechanics (verified):
- DeepSeek cached_tokens = longest byte-identical prefix of the prompt. ANY
  byte change in the prefix (reworded/renumbered/deleted messages, reordering,
  system-role content changed, summary regenerated) invalidates the cache from
  that point on.
- Verified failure mode (Todo/CacheFriendlyCompactionImplementation.md,
  2026-08-14): compaction deleted messages from the middle and scattered
  inline markers at original positions → every subsequent byte shifted →
  whole tail cache miss; cached_tokens frozen at ~12K while prompt grew
  72K→86K tokens. That spec's scope is ABSORBED by this task (it owns
  compaction now); its "do not touch core prune" non-goal is superseded.
- Existing fix pattern (already live, omniagent 9c5bb60): user-role for
  dynamic blocks raised hit rate 6.9% → 90%+.
- Cache miss ≈ newly appended content per call: smaller tool results = fewer
  misses per iteration + compaction delayed.

Requirements (cache):
1. **Stable prefix invariant.** compact+prune must NEVER modify, reword,
   renumber, or reorder any message that precedes the newest appended block.
   Only the tail (newest messages) may change between LLM calls. Tool-result
   truncation/excerpting must be deterministic (same input → same bytes) and
   must not shift earlier bytes (replace content in place, never delete rows
   from the middle of the array).
2. **Frozen summary block** (CacheFriendlyCompaction design): on compaction,
   build ONE summary block at a FIXED index right after the main system
   prompt; reuse it byte-identical on subsequent calls; fold newly drained
   content into it only at the NEXT compaction (strict superset, append-only).
   Replace-don't-scatter: no per-message inline markers at scattered
   positions. Keep the null-contract (no drain → "messages": null).
3. **Minimize per-iteration miss tokens.** The prune-in-compact aggressively
   compacts read-type results (keep last N full, excerpt older, auto-note) AND
   measure the top token producers (query messages by msg_subtype / tool name,
   sum content length) — if filesystem_read etc. dominate, add output capping
   at the source. Do NOT make the agent dumb: read results stay preserved via
   auto-notes (death-spiral fix).
4. **Compaction cadence.** With tokens-only budgets (task 12), pick defaults
   so compaction fires only when needed (bigger hard budget = longer
   stable-prefix window). Must not regress below current cadence.
5. **No mid-context upserts with changing content.** Verify the "=== Budget ==="
   iteration hint (WS-4c) sits at the END of the context (it changes every
   iteration; at the end its changed bytes are in the miss region — acceptable,
   but VERIFY; if any upsert lands mid-context, move it to the end).
6. **Custom-plugin cache compatibility.** The stub-plugin test must produce
   cache-compatible output; the stable-prefix property is a PLUGIN
   responsibility — document it in plugin.json tool description + interface
   docs ("the returned messages array must keep the prefix byte-stable; only
   the tail may change").

## Requirements

1. **Core removals** (src/):
   - main_loop.rs: delete the Layer-3 `prune_old_tool_results` call (843-855)
     and its doc comments; keep the iteration "=== Budget ===" hint (WS-4c) —
     it is iteration-based, not char-budget-based.
   - config.rs: remove `char_budget_hard`/`char_budget_soft` (+ the pruning
     fields read_keep_last/read_excerpt_chars/auto_note_max_chars/
     auto_note_entry_chars ONLY if nothing else uses them — grep first;
     if the plugin takes them over, they become plugin config).
   - helpers.rs: remove `prune_old_tool_results` + PruneConfig (move the
     retained behavior into the plugin); keep `estimate_chars`/`count_tokens`
     if genuinely reused elsewhere (document).
   - settings.rs: remove prompt_char_budget_* from categories + writable
     whitelist (task 12 already did the key rename/removal — verify).
2. **Plugin implementation** (plugins/tools/prompt):
   - Budgets: ONLY `token_budget_soft`/`token_budget_hard` (from task 12) in
     PluginConfig; chars/4 fallback when tokenizer missing/invalid.
   - Extend compact-messages (interface change OK, document in plugin.json +
     tool description): accept the info needed to prune tool results — e.g.
     messages already carry tool_call_id/name, so identification is possible;
     if auto-notes need the thread dir, add an optional arg (thread_dir /
     notes_path) — decide with the dashboard/API consumers in mind.
   - As part of compact-messages: after condensation, prune tool results per
     the token budget — preserve read results + auto-note them (keep the
     death-spiral fix): keep last N read-type results full, excerpt older,
     write auto-notes to the thread notes file if the arg is provided.
   - Keep behavior when plugin absent: document that NO prompt plugin = NO
     compaction/pruning (context grows to provider limit) — acceptable;
     core must not silently re-add pruning.
3. **Tests (lockstep):**
   - Remove/relocate core prune tests; add plugin tests for prune-inside-compact
     (tool-result identification by role/name, excerpt + auto-note).
   - omni-deployer tests.py: update the compaction groups (token budgets +
     chars/4 determinism per task 12; add a group covering prune-in-compact).
   - Add a **custom-plugin test**: a stub prompt plugin with a DIFFERENT
     compaction strategy runs through the same interface (proves plugin
     ownership — the core does not depend on any specific plugin behavior).
4. **Docs**: plugin.json tool description + any interface docs updated;
   note in wiki Reference/Agent-Guidance-Architecture or Budget-and-Context
   that context management is plugin-owned.

## Non-goals / DO NOT CHANGE

- Do NOT change the plugin loading/registry mechanism (MCP stays; only tool
  args/semantics change).
- Do NOT change Layer 1 (system prompt assembly) or the Layer-2 call cadence
  (iteration gating) unless required by the interface change.
- Do NOT re-add any budget/prune to core as a "safety backstop" — the user
  explicitly rejected the dual mechanism. If a real gap emerges, surface it
  to the user instead of silently re-adding.
- No DB migration. No unrelated config/env changes.

## Verification gates

- `grep -rn "char_budget\|token_budget\|prune_old_tool_results\|PruneConfig"`
  in `src/` → 0 hits (core is clean; plugin owns it all).
- settings.yml + settings.rs + /settings API: no prompt_*_budget_* keys.
- cargo check / clippy -D warnings / cargo test / fmt --check clean.
- deploy.py dev passes (omni-deployer dev-flavor).
- Live smoke (omnidev): long thread compacts AND prunes via compact-messages
  only; read results still preserved + auto-noted (no re-read death spiral);
  iteration budget hint still present.
- Custom-plugin test passes (stub plugin, different strategy, same interface).
- **CACHE GATES (user-mandated):**
  - Cache regression gate: measure from threads table
    (`sum(cached_tokens)/sum(input_tokens)`) after deploy — must be **≥ 95%**
    and IMPROVED vs the 94.4% 7-day baseline (08-19); report the daily %
    in the task thread.
  - Live cache check: `cached_tokens` grows with prompt size (never frozen at
    a small constant — the 08-14 failure mode).
  - Unit tests: (a) consecutive non-compacting calls produce byte-identical
    prefixes `[system][frozen summary][tail]` up to the tail; (b) a second
    compaction's summary is a strict superset of the first (frozen block);
    (c) deterministic truncation — same input → same bytes.
  - No mid-context upsert with changing content (verify WS-4c "=== Budget ==="
    hint sits at the end).
  - Quality guard: agent task runs complete normally (no "dumber" behavior) —
    full executor→tester→reviewer loop passes on a real task.

## Deliverable

omniagent commit(s) + SHAs + grep/clippy/test evidence + live-smoke notes in
the thread. Standing release loop: tasks → deploy.py dev → main → stable
(never push stable while omnistable tasks run).
