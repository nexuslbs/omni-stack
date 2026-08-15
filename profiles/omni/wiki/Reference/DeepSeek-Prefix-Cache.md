# DeepSeek Prefix-Cache Misses: Root Cause & Fix

**Status:** Resolved (2026-08-15, omniagent `9c5bb60`)
**Scope:** omniagent core (`src/agent/helpers.rs`, `src/agent/main_loop.rs`)
**Related:** [Cache-Friendly Compaction](../Todo/CacheFriendlyCompactionImplementation.md) — that task fixed the *plugin* compaction budgets; this report covers the remaining *core* cache killer.

## Symptom (live thread 514)

- 247 iterations, **26,723,744 input tokens / 1,840,128 cached = 6.9% hit rate**
  (~24.9M tokens billed at full price — ~93% waste).
- `cached_tokens` froze at **exactly 7,424** from iteration 4 onward while the
  prompt grew 16,384 → 87,004+ tokens.
- All threads showed the same pathological 5–12% pattern (thread 264: 45.4M
  prompt / 2.48M cached; 297: 22.9M / 2.74M; 263: 40.8M / 2.57M; 116: 35.8M /
  2.62M; 256: 47.9M / 2.08M).
- Calls were only 2–5 s apart — far inside DeepSeek's cache TTL, so timing was
  NOT the cause.

## What 7,424 is

The static preamble = messages 0–6 (system prompt 11,114ch + MEMORY 4,648ch +
Task Template 6,119ch + Context 6,390ch + Generated Plan 783ch + user task
4,461ch + Output Limit 386ch) ≈ **7,424 tokens**, and all freeze values are
×128 block-aligned (7,424 = 58 × 128; 12,032; 9,216; 8,320…). The cache never
covered a single tool-call message for 243 iterations.

## Root cause

**DeepSeek hoists `system`-role messages into the system-prompt region of its
cache key.** Any mid-conversation `system`-role message whose text changes
breaks the byte-identical prefix at that point — and everything after it
(which on DeepSeek includes the *entire rest of the conversation* once a
system message sits mid-stream) becomes a cache miss on every call.

`helpers::upsert_system_message` (helpers.rs:221–224) does:

```rust
messages.retain(|m| m.role != "system" || !m.content.starts_with(marker));
messages.push(ChatMessage::system(content));
```

Remove-old-anywhere + re-insert-at-END, with **changing text every iteration**.
Used every loop for the `=== Budget ===` block (iteration counter), Working
Notes, and `=== Auto-Saved Reads (engine) ===` (main_loop.rs:639–691). So each
call had a different `system` block in a different position → the cache key's
system region changed → the prefix broke at the static head (7,424) on EVERY
call. `prune_old_tool_results` (in-place truncation once >500K chars) is a
second guaranteed mid-conversation mutation.

### Why stored payloads replay at 96–99%

The DB snapshots (`messages` rows, `serde_json::to_string(&messages)`) append
cleanly and are byte-identical between consecutive iterations — replaying them
against the live API cached at 99%. The freeze only reproduced with the exact
live wire: `include_reasoning: true` + the ~40-tool array + the system-block
upsert. Empirical probe `probe_final2.py` isolated the exact mechanism:
**USER-role upsert → cached 9,472→9,600→9,728 (98.8%→99.7%, grows each
iteration); SYSTEM-role upsert → frozen at 7,424 (76.8–77.7%)** — a faithful
reproduction of thread 514's freeze.

## Fix (omniagent `9c5bb60`)

`upsert_system_message` now retains any prior `system|user` marker instance
and pushes **`ChatMessage::user(&content)`** instead of system. A `user`-role
block stays in the conversation stream at the tail — it does not participate
in the hoisted system-prompt region, so the byte-identical prefix rides across
iterations.

- Call sites unchanged (Budget, Working Notes, Auto-Saved Reads, compaction
  notice, Output-Limit re-upsert) — only the role changed.
- The 5 remaining direct `system` pushes (last-turn hint, subtask
  enforcement, empty-response nudges) are exceptional-path only and safe.

## Verification

- omnidev threads 395/396 (fixed binary, deepseek/deepseek-v4-flash):
  - Thread 395: **86,424 input / 44,928 cached = 52% aggregate** (was 6.9%);
    per-call cache GROWS: 10,608 cold → 17,280 (62%) → ~27,648 (**89.9%**).
  - Thread 396: **93,959 input / 62,464 cached = 66.5% aggregate**; steady-state
    calls 91.6% → 93.3%.
- `cargo check --workspace` clean; 37/37 `agent::helpers` unit tests pass.

## Follow-ups

- Budget/Working Notes/Auto-Saved Reads blocks should be genuinely append-only
  (single fused tail block) to eliminate remove/reinsert entirely.
- Consider summary-based compaction emitting ONE stable summary block as the
  boundary (extends Cache-Friendly Compaction).
- `deploy.py dev` full-stack verification (deploy-dev2 run) should show the
  same hit-rate improvement on the deploy instance.
