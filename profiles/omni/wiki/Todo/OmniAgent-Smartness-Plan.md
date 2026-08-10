# OmniAgent Smartness Plan — Durable Working Memory + Anti-Re-Read Loop

> **Status:** Refined design (v3) per Lucas's direction: notes = files in
> `OMNI_DIR/data/threads/<id>/` acting as a temporary wiki; pruned context dumped to a
> recovery file; anti-loop guarantees built in; filesystem write sandbox expanded to
> OMNI_DIR subdirectories via configurable checkboxes.
> **Source evidence:** Thread 342 (2026-08-09) burned 120/120 iterations on task 1 of the
> omniagent-dev workflow, ~60-70% re-reading the same files: 13× identical
> `git show HEAD:src/server/kanban.rs`, 7× full reads of `plugins/tools/kanban/src/main.rs`,
> 6× identical greps. 1.6 MB of tool results consumed. Reached its conclusion only at
> iteration 120, then hit the cap (`max_iterations_plan = 120`).

---

## 1. Root cause (confirmed in code)

Context-amnesia death spiral:

1. **`helpers.rs:187` `prune_old_tool_results`** — at iteration ≥16 replaces every old tool
   result body with `[Tool result for X: N chars, omitted]`. The model literally cannot see
   what it read earlier.
2. **`compact.rs` / `helpers.rs:238` compaction** — drains old tool-call pairs; retained
   excerpt = first ~800 chars of raw output (file header noise, not the facts).
3. **No durable memory** — nothing persists findings across prune/compact. The model re-reads
   to re-learn → context floods → pruned again. Loop until the 120 cap.
4. **Prompt never teaches note discipline** — TOOL_GUIDANCE has 9 rules, none about notes,
   verify-once, or read dedupe.
5. **No budget visibility** — only a "last turn" hint at the very end.

**Environment constraints discovered:**
- `OMNI_DIR` = `/opt/omni` in container = host `/opt/workspace/omni-stack` (bind mount).
- Filesystem plugin **writes** are sandboxed to `workspace_dir` (default `/opt/workspace`);
  `/opt/omni` is lexically OUTSIDE it. **WS-6 expands the sandbox** to OMNI_DIR subdirs
  (profiles/, data/, plugins/) via checkboxes enabled by default, plus an opt-in "entire
  OMNI_DIR" checkbox (disabled by default) — so `filesystem_write` into the thread dir
  works once WS-6 lands. Until then, the notes tools write directly to disk.
- `McpMeta.thread_id` is auto-injected on every tool call → the notes plugin resolves
  `<omni_dir>/data/threads/<thread_id>/` with no extra args.
- `fail_thread` already copies parent script to a rerun thread (Bug B) → parent `notes.md`
  inheritance is a small extension.

---

## 2. Design overview

```
/opt/omni/data/threads/<thread_id>/
├── notes.md            # agent-written durable findings (the PRIMARY memory)
├── context-<iter>.json # PLATFORM-written digest dump of pruned/compacted tool results
│                       #   (one per compaction event, capped, auto-cleanup)
├── <any file>          # agent-fetched reference files / temp wiki (via note_write)
└── (retry: parent's notes.md copied in before rerun)
```

Three layers, strictly ordered:
1. **notes.md** — agent's deliberate, compact, structured memory. Survives everything.
2. **context-<iter>.json** — automatic *digest* of what pruning/compaction destroyed. Read
   ONLY as recovery, at most once per event, immediately summarized into notes.md.
3. **Everything else in the dir** — reference files the agent fetched (temp wiki).

The anti-loop contract: **notes are the memory; the dump is a last-resort fallback; reading
the dump twice for the same fact is an engine error, not a prompt violation.**

---

## 3. WS-1: Notes toolset in the prompt plugin (temporary wiki)

All tools derive the thread dir from `meta.thread_id` + `cfg.omni_dir` — no thread_id arg.
Path sandbox: every resolved path must stay inside `<omni_dir>/data/threads/<thread_id>/`
(reject `..`/absolute escapes) — plugin writes directly to disk (bypasses filesystem sandbox;
once WS-6 lands the same dir is also reachable via `filesystem_write`, which is fine — the
note tools remain the structured convenience + read-once guard layer).

**New tools** (registered in the prompt plugin's tool list):

| Tool | Args | Behavior |
|---|---|---|
| `note_append` | `entry: str` | Append `[HH:MM:SS] <entry>` to `notes.md` (create dir/file lazily) |
| `note_read` | `file: str = "notes.md"` | Read any file in the thread dir (default notes.md), capped at ~8 KB |
| `note_write` | `file: str, content: str` | Write/overwrite any file in the thread dir (temp-wiki use: save fetched reference) |
| `note_list` | — | List files + sizes in the thread dir |
| `note_rm` | `file: str` | Delete a file in the thread dir (destructive — requires confirm in prompt) |

**TOOL_GUIDANCE additions (prompt_builder.rs):**

> 10. TAKE NOTES: every durable fact you learn (file+line, commit SHA, function location,
> conclusion) → `note_append` immediately. Before reading a file or re-running a query,
> `note_read` first. If the fact is already noted, DO NOT re-read/re-run. Notes survive
> compaction; context does not. Your notes dir is `/opt/omni/data/threads/<id>/` — use
> `note_write` to save fetched reference files there (temporary wiki).
>
> 11. VERIFY ONCE: for verification tasks, check each claim exactly once, record the evidence
> in notes, then proceed. Re-verify only if underlying state changed.
>
> 12. DUMP RECOVERY (anti-loop): if a needed fact was pruned, you may read the matching
> `context-<N>.json` ONCE via `note_read`, extract what you need, `note_append` it to notes.md,
> and NEVER read that dump file again. Re-reading a dump regrows context and triggers another
> compaction — that is a loop and is forbidden.

---

## 4. WS-2: Platform-side pruned-context dump (the recovery file)

**Who writes it:** the platform, never the agent. Two writers, same format:

- **Prune** (`helpers.rs`): when `prune_old_tool_results` would destroy a tool result body,
  first append a *digest* entry to `context-<current_iter>.json`:
  `{"tool":"git_run-command","args":"show HEAD:src/server/kanban.rs","chars":42315,"head":"<400 chars>","tail":"<400 chars>"}`
  (head+tail per WS-3 — the useful part), then apply the prune. Dump format = JSON Lines.
- **Compact** (prompt plugin `compact.rs`): when draining old tool-call pairs, append the same
  digest for each drained result to `context-<iteration>.json` (it knows iteration via
  `current_iteration`; thread dir via meta). Dedupe: skip entries already dumped by prune
  (same tool+args hash).

**Cap & cleanup (anti-growth):**
- Per-file cap: 200 KB (roughly 100-200 digest entries). When exceeded, oldest entries drop.
- Keep at most the last 3 `context-*.json` files; delete older on compaction. Thread-dir
  cleanup on terminal thread state (after summary), EXCEPT when a child/retry thread exists.

**Why digest not raw:** a raw 1.6 MB dump would flood context on read → trigger compaction →
loop. A 200 KB digest of head+tail is bounded, readable in 2-3 `note_read` calls, and contains
the actual facts (definitions/locations are usually at the end of tool output).

---

## 5. WS-3: Compaction event notice + injection (prompt plugin informs)

**On compaction** (`handle_compact_messages` in the plugin, when `was_compacted=true`):
return in the tool result `event: {iteration, dump_file, entries}`. The main loop
(`main_loop.rs` condense block) then pushes a system message BEFORE the next LLM call:

```
=== Context Compacted (iteration N) ===
M tool results were archived to /opt/omni/data/threads/<id>/context-N.json (digest form).
Your notes.md is intact. If you need a pruned fact: 1) note_read your notes.md first;
2) if absent, note_read context-N.json ONCE; 3) note_append the recovered fact to notes.md;
4) never re-read context-N.json. Re-reading regrows context and causes another compaction.
```

**Notes injection (survives compaction):** in `main_loop.rs`, AFTER the condense + prune block
(so it is never compacted away), read `notes.md` (≤8 KB) and push:
`=== Working Notes (durable) ===\n<content>` — if non-empty. Because this is added after
compaction and notes stay small, the model always has its memory.

---

## 6. WS-4: Engine-level read guards (the anti-loop guarantee)

Even with perfect prompts, models loop. Add structural guards:

1. **Dump read-once enforcement (note_read):** the prompt plugin tracks, per thread, which
   `context-*.json` files were read. A second read of the SAME dump file returns a synthetic
   result instead of content:
   `[duplicate read: context-47.json already read at iteration 60. Extracted facts should be
   in notes.md. Re-reading is forbidden by rule 12.]`
2. **Identical read-only call suppression (extends WS-5):** in `main_loop.rs`, keep
   `HashMap<(tool, args_hash), (iteration, len)>` for read-only tools (`git_*`,
   `filesystem_read/info/list`, `search_*`, `note_read`). Exact-repeat call → synthetic result
   `[duplicate of <tool> at iteration 47 — see your notes]`. Only for read-only tools; never
   after a state-changing op.
3. **Budget line:** inject `=== Budget === Iteration {i}/{limit}. Remaining: {N}. If N < 20
   stop exploring, start producing.` each call (replaces last-turn-only hint as primary;
   keep last-turn hint as backstop).

---

## 7. WS-5: Retry inheritance (fixes the 342→343 waste)

`fail_thread` reruns create a new thread with `parent_id`. Extend it:
- On rerun, copy parent's `<thread_dir>/notes.md` → child `<thread_dir>/notes.md` (and include
  the parent's notes in the child's first prompt via the notes injection).
- Child thread therefore starts with everything the interrupted parent learned — thread 343
  would have started knowing "kanban.rs:2062 = dispatch handler, tests present" instead of
  re-exploring 120 iterations.
- This composes with the existing "inject prior thread content" task (R7-D4 chain).

---

## 8. WS-6: Filesystem write sandbox — OMNI_DIR subdirectory toggles

**Requirement (Lucas):** the agent can filesystem-READ anything (already true), and
filesystem-WRITE in the workspace (already true), AND in OMNI_DIR under `profiles/`, `data/`,
and `plugins/` — with a checkbox for each of the 3 cases, enabled by default — plus another
checkbox for the entire OMNI_DIR, disabled by default.

**Implementation (plugins/tools/filesystem/src/main.rs + plugin.json):**

1. **Config schema** (`plugin.json` `config_schema`, rendered by the dashboard's existing
   boolean-checkbox renderer):
   - `omni_dir` (string, default `$env:OMNI_DIR` → `/opt/omni`) — base for the toggles.
   - `write_profiles` (boolean, default `true`) — allow writes under `{omni_dir}/profiles/`.
   - `write_data` (boolean, default `true`) — allow writes under `{omni_dir}/data/`.
   - `write_plugins` (boolean, default `true`) — allow writes under `{omni_dir}/plugins/`.
   - `write_omni_all` (boolean, default `false`) — allow writes ANYWHERE under `{omni_dir}`
     (overrides/supersedes the 3 subdir toggles when enabled).
   - `workspace_dir` stays (default `/opt/workspace`) — always allowed, independent of toggles.

2. **Sandbox check** — replace the single-root `restrict_to_workspace` with
   `restrict_write_path(path, cfg)` that builds the allowed-roots list at configure time:
   `[workspace_dir]` + `[omni_dir]` if `write_omni_all` else
   `[omni_dir/profiles]` if `write_profiles` + `[omni_dir/data]` if `write_data` +
   `[omni_dir/plugins]` if `write_plugins`. Pass iff the normalized path starts_with ANY
   allowed root (existing lexical normalization preserved; error message lists the roots).
   This is a pure function — unit-testable with the existing test style.

3. **Tool descriptions** (`filesystem_write` description + plugin.json description): update the
   SANDBOX wording to mention the OMNI_DIR subdir toggles.

4. **Keep reads unrestricted** — no change to read/list/search/info.

**Why this matters for the plan:** it makes `/opt/omni/data/threads/<id>/` reachable via plain
`filesystem_write`, so the notes temp-wiki works even without the note tools; and it gives the
deployer fine-grained control (e.g., disable `write_plugins` in prod, keep `write_data` on).

---

## 9. Task breakdown (for dispatch to omnidev agent)

Ordered, each TDD where feasible (`cargo build --release -p <pkg>` + `cargo test`, commit,
push to main):

1. **Notes toolset (WS-1):** `note_append/read/write/list/rm` in prompt plugin; thread-dir
   resolution + path sandbox; unit tests (sandbox rejects `..`, round-trip write/read,
   thread_id from meta).
2. **Prune dump (WS-2):** `helpers.rs` writes digest entries to `context-<iter>.json` before
   destroying bodies; cap + rotation; unit test (16+ bucket still dumps, cap enforced).
3. **Compact dump + notice (WS-3):** `compact.rs` appends digests (dedupe by tool+args hash);
   `main_loop.rs` pushes the compaction system message; prompt plugin returns `event` object.
4. **Notes injection (WS-3):** `main_loop.rs` reads `notes.md` post-compaction, pushes
   `=== Working Notes ===`; TOOL_GUIDANCE rules 10-12.
5. **Read guards (WS-4):** dump read-once in note_read; identical read-only call suppression
   map in main_loop; Budget line injection; unit tests for suppression + read-once.
6. **Retry inheritance (WS-5):** fail_thread copies parent notes.md; test that child prompt
   contains parent's notes.
7. **Filesystem sandbox toggles (WS-6):** `plugins/tools/filesystem` — `omni_dir` +
   `write_profiles`/`write_data`/`write_plugins` (default true) + `write_omni_all` (default
   false) config schema; `restrict_write_path` multi-root check; unit tests (each toggle
   on/off, omni_all overrides, workspace always allowed, traversal still rejected); update
   tool/plugin descriptions.
8. **Verification (omnidev integration):** re-dispatch the R7 workflow-plumbing task; assert
   notes appear in thread messages, dump files exist, identical calls suppressed, thread
   completes < 50 iterations, noop test suite (Groups 13/14/22) still passes.

---

## 10. Verification plan

1. **Unit:** sandbox rejection, note round-trip, dump cap, prune-dumps-before-destroy,
   compact-dedupe, read-once marker, budget-line math, retry notes copy.
2. **Integration (omnidev):** re-dispatch workflow-plumbing task → expect ≤50 iterations,
   notes in system messages, context-N.json files present, duplicate-read markers in messages.
3. **Regression:** noop test-tool-caller suite (Groups 13/14/22) — compaction threshold gating
   unchanged; note injection inert when no notes exist.

---

*Open questions for Lucas:* (a) notes toolset lives in the prompt plugin (recommended — it
already has omni_dir + thread_id meta; a separate plugin adds plumbing for no gain) vs new
`notes` plugin; (b) dump retention = last 3 events / 200 KB each OK? (c) `note_rm` needed in
v1 or defer? — **RESOLVED (WS-6):** filesystem write sandbox now toggleable for
`{omni_dir}/profiles|data|plugins` (default on) + `{omni_dir}` whole (default off), per
Lucas's requirement; dashboard checkboxes come free via the existing boolean renderer.
