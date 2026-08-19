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

## Deliverable

omniagent commit(s) + SHAs + grep/clippy/test evidence + live-smoke notes in
the thread. Standing release loop: tasks → deploy.py dev → main → stable
(never push stable while omnistable tasks run).
