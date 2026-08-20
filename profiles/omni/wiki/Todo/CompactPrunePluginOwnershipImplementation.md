# Compact + Prune + Budget → Prompt Plugin Only — Implementation

**Status:** IMPLEMENTED 2026-08-19 (task 15; executor #64, tester #65 PASS, reviewer #67 APPROVE) — omniagent `e8239a0` + omni-deployer `0553cbc`/`f76d74f` + omni-stack `fde68b7`
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
- Budget-unification task (12, runs before this): removes char budgets, keeps
  ONLY token budgets, and renames the core fields to `token_budget_hard/soft`
  as GLOBAL SETTINGS (`prompt_token_budget_hard/soft` in settings.yml +
  settings.rs whitelist). The plugin's token_budget_* config fields remain
  INTERIM until THIS task moves them to compact-messages params.

## Architecture rule (user, 2026-08-19 v2 — do NOT re-litigate)

- **Budgets are GLOBAL SETTINGS in omniagent** (user decision v2): hard/soft
  token budgets live in settings.yml (`prompt_token_budget_hard/soft`) +
  settings.rs whitelist + /settings API, with AgentConfig
  `token_budget_hard/soft` fields (task 12 renamed them). The prompt plugin
  has NO budget config.
- **compact-messages MUST receive the soft and hard token budget as PARAMS**
  (tool args, e.g. `soft_budget`/`hard_budget`). omniagent resolves the
  effective per-thread budgets and passes them in; the prompt plugin stays
  AGNOSTIC of where the budgets come from (models.yml / providers.yml /
  settings). The fallback chain is owned by the models.yml task (model_config
  > provider(models.yml) > global settings; global defaults soft 100000 /
  hard 500000) — this task only wires the params through.
- **No tool pruning in core.** main_loop.rs has NO prune call, NO PruneConfig.
  The AgentConfig budget FIELDS stay (they are global settings); only the
  pruning USE is removed. main_loop passes the budgets to compact-messages.
- The prune MAY exist, but **as part of compact-messages** (the prompt plugin),
  which knows which messages are tool results; it uses the budget PARAMS for
  the gate + drain.
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
1. **Stable prefix invariant (user-corrected 2026-08-19).** compact+prune must
   NEVER modify, reword, renumber, or reorder any message that precedes the
   newest appended block — and crucially NEVER modify a message that stays in
   the tail: rewriting an old message shifts every byte after it → the whole
   tail becomes a cache miss on the next call. That INCREASES misses; it does
   not reduce them. Truncation is allowed ONLY in two cache-safe places:
   (a) at SOURCE — when a tool result is created, before it enters context;
   (b) at DRAIN time — old content being removed is excerpted INTO the frozen
   summary block, never written back into its old position. Surviving
   messages keep byte-identical content and relative order.
2. **Frozen summary block** (CacheFriendlyCompaction design): on compaction,
   build ONE summary block at a FIXED index right after the main system
   prompt; reuse it byte-identical on subsequent calls; fold newly drained
   content into it only at the NEXT compaction (strict superset, append-only).
   Replace-don't-scatter: no per-message inline markers at scattered
   positions. Keep the null-contract (no drain → "messages": null).
3. **Minimize per-iteration miss tokens — via AGENT-SIDE WINDOWING, not
   silent truncation (user-refined 2026-08-19).** Do NOT silently
   cap/truncate tool results at the source — the full content MAY be needed,
   and black-magic truncation makes the agent misunderstand what it read.
   Instead:
   (a) AGENT-SIDE WINDOWING (preferred): skills + templates teach the agent to
       prefer SMALLER result windows and use the tools' windowing params —
       `filesystem_read` already supports char-based offset/limit paging
       (verified plugins/tools/filesystem/src/main.rs:173-181, default limit
       50000); fetch should expose ranges too where the protocol allows. Read
       a slice, not the whole file; page only when needed. The cache benefit
       follows: fewer NEW tokens appended per call + compaction delayed —
       from the agent's OWN explicit choice, never from silent truncation.
   (b) SAFE CONTENT-SEARCH TOOL (grep/rg, user-suggested 2026-08-19): add a
       file-content search tool (filesystem plugin — `filesystem_search`
       today matches NAMES only) so the agent finds the relevant lines instead
       of reading whole files. SAFETY-CRITICAL constraints: fixed `rg`
       binary, path-restricted to the allowed roots (no escape), validated
       args (pattern + path whitelist + max results/context; NO shell, NO
       arbitrary code), returns matching lines with line numbers + context
       window. If rg is unavailable, vendor a static binary or implement a
       bounded in-process matcher — do NOT shell out to user-controlled
       commands.
   (c) DRAIN-time compaction (safety valve, only when over the hard budget):
       remove ONE contiguous old region (oldest → keep-point); read-type
       results in the drained region excerpted INTO the frozen summary block
       (auto-notes preserved — death-spiral fix). Excerpts preserve MEANING
       (what was read + why), not arbitrary head-truncation. The surviving
       tail stays full + verbatim ("keep last N full" = the surviving tail;
       "excerpt older" = drained content folded into the summary). NEVER
       excerpt/modify a message that remains in the tail (user-corrected
       anti-pattern: in-place rewrites increase cache misses). Do NOT make the
       agent dumb: read results stay preserved via auto-notes.
4. **Compaction cadence (threshold-gated — user-corrected 2026-08-19).** The
   compact-messages tool is CALLED every iteration but COMPACTS only when the
   hard budget is exceeded; under budget it returns "messages": null (the
   null-contract) and the core applies nothing — the prefix stays untouched.
   Verify the no-op path is byte-identical (never rewrite/reorder when under
   budget). With tokens-only budgets (task 12), pick defaults so compaction
   fires rarely (bigger hard budget = longer stable-prefix window). Must not
   regress below current cadence. (The 08-14 "compaction every iteration"
   observation was a misconfiguration symptom — thread 5x over the 100K char
   hard budget — NOT the intended design.)
5. **No mid-context upserts with changing content.** Verify the "=== Budget ==="
   iteration hint (WS-4c) sits at the END of the context (it changes every
   iteration; at the end its changed bytes are in the miss region — acceptable,
   but VERIFY; if any upsert lands mid-context, move it to the end).
6. **Custom-plugin cache compatibility.** The stub-plugin test must produce
   cache-compatible output; the stable-prefix property is a PLUGIN
   responsibility — document it in plugin.json tool description + interface
   docs ("the returned messages array must keep the prefix byte-stable; only
   the tail may change").
7. **Skills/templates guidance (omni-stack, the PRIMARY lever).** Update the
   omni profile skills + templates that guide file reading to teach: (a)
   prefer smaller result windows; (b) use `filesystem_read` offset/limit
   paging and fetch ranges; (c) use the content-search tool BEFORE reading
   whole files. This is the main mechanism for fewer miss tokens — NOT
   runtime truncation. The agent should never receive a silently-truncated
   result it doesn't know about.

## Requirements

1. **Core changes** (src/):
   - main_loop.rs: delete the Layer-3 `prune_old_tool_results` call (843-855)
     and its doc comments; INSTEAD pass the resolved budgets
     (`cfg_snapshot.token_budget_hard/soft`) as `soft_budget`/`hard_budget`
     params in the compact-messages tool call (Layer 2); keep the iteration
     "=== Budget ===" hint (WS-4c) — it is iteration-based, not
     budget-based.
   - config.rs: KEEP `token_budget_hard`/`token_budget_soft` (global settings
     from task 12 — do NOT remove); remove the pruning-only fields
     read_keep_last/read_excerpt_chars/auto_note_max_chars/
     auto_note_entry_chars ONLY if nothing else uses them — grep first;
     if the plugin takes them over, they become plugin config or params.
   - helpers.rs: remove `prune_old_tool_results` + PruneConfig (move the
     retained behavior into the plugin); keep `estimate_chars`/`count_tokens`
     if genuinely reused elsewhere (document).
   - settings.rs: KEEP `prompt_token_budget_hard/soft` in categories +
     writable whitelist (global settings — task 12 renamed them; they are NOT
     removed).
2. **Plugin implementation** (plugins/tools/prompt):
   - REMOVE budget fields from PluginConfig (`token_budget_soft`/`token_budget_hard`
     + any leftover char fields from task 12). Budgets come ONLY as
     compact-messages params.
   - compact-messages REQUIRES soft/hard token budget params (e.g.
     `soft_budget`, `hard_budget` — add to plugin.json tool description +
     config_schema). chars/4 fallback stays INTERNAL: when tokenizer
     missing/invalid, measure chars and compare against the params (chars as
     4× token budget).
   - Extend compact-messages (interface change OK, document in plugin.json +
     tool description): accept the info needed to prune tool results — e.g.
     messages already carry tool_call_id/name, so identification is possible;
     if auto-notes need the thread dir, add an optional arg (thread_dir /
     notes_path) — decide with the dashboard/API consumers in mind.
   - As part of compact-messages: gate on the hard/soft PARAMS; after
     condensation, prune tool results per the budgets — preserve read results
     + auto-note them (keep the death-spiral fix): keep last N read-type
     results full, excerpt older, write auto-notes to the thread notes file if
     the arg is provided.
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

- `grep -rn "prune_old_tool_results\|PruneConfig"` in `src/` → 0 hits (core
  pruning gone). `token_budget_hard/soft` remain ONLY as AgentConfig global
  settings + settings keys; the main loop passes them as compact-messages
  params — no budget USE for pruning in core.
- settings.yml + settings.rs + /settings API: `prompt_token_budget_hard/soft`
  present (global settings, from task 12); no char-budget keys.
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
  - **Content-search safety gate (if the grep/rg tool is added):** no shell
    invocation, no arbitrary code; path-restricted to allowed roots (escape
    attempts rejected); arg validation tests pass (pattern/path/limit);
    `rg` fixed binary or in-process matcher only.
  - **Guidance gate:** omni profile skills/templates contain the
    smaller-windows + paging + search-first guidance; a read-type tool result
    is never silently truncated (any truncation is agent-visible).

## Deliverable

omniagent commit(s) + SHAs + grep/clippy/test evidence + live-smoke notes in
the thread. Standing release loop: tasks → deploy.py dev → main → stable
(never push stable while omnistable tasks run).


---

## Implementation (2026-08-19/20)

**Status: IMPLEMENTED** — executor #64, tester #65 PASS, reviewer #67 APPROVE (all in-window).

| Repo | Commit | What |
|---|---|---|
| omniagent | `e8239a0` | Core pruning deleted (`prune_old_tool_results` + `PruneConfig` + `context_dump` module + `read_keep_last`/`read_excerpt_chars`/`auto_note_*` config fields); main_loop.rs:772-773 passes `soft_budget`/`hard_budget` (= `cfg_snapshot.token_budget_soft/hard`, global settings) as REQUIRED compact-messages params; plugin `PluginConfig` loses `token_budget_soft/hard` + `old_msg_budget`; prune + auto-notes moved INSIDE compact-messages (thread_dir arg); `handle_condense` removed; plugin.json/tool docs/config_schema updated; unit tests (gate, chars/4 fallback, null-contract, keep_recent verbatim, prune+auto-notes, missing-param error) |
| omni-deployer | `0553cbc` | GROUP 11 updated (budget params); new p8 prune-in-compact tests (auto-notes drain, tail byte-verbatim, under-budget null + byte-identical input, missing-param error); p9 custom-plugin stub |
| omni-deployer | `f76d74f` | TESTER FIX: 2 bugs in 0553cbc's tests (tester #65 found + fixed; the fixed suite is what passes) |
| omni-stack | `fde68b7` | Reference/Budget-and-Context.md: context management is PLUGIN-OWNED (budgets as params, prune inside compact-messages, cache-friendly frozen summary block, smaller-windows guidance) |

Verification (tester #65 + reviewer #67, fresh-HEAD binary in omnidev-toolbox): grep gates `prune_old_tool_results|PruneConfig` in src/ → 0 hits; budgets only as global settings (config.rs:250-253/359-362 reads `prompt_token_budget_hard/soft`, defaults soft 100000 / hard 500000; settings.rs:186-187,575-585,656-657,776-777 categories + writable whitelist; no char-budget keys); main_loop.rs:772-773 passes params; WS-4c "=== Budget ===" iteration hint retained (840-845); GROUP 11 + p8 + p9 pass. Cache ≥95% gate: still to be measured live post-deploy (threads table cached/input ratio) — the code-level stable-prefix invariants are implemented per spec.
