# Remove SOUL.md Support + Single Root MEMORY.md (Implementation)

**Status:** BACKLOG (omnidev board, omnistable) — NOT to be dispatched until explicitly requested.
**Date:** 2026-08-23
**Scope:** omniagent + omni-dashboard + omni-deployer + omni-stack/omni-root (profile layout)
**Spec:** omni-stack (this file) — mirrored in the kanban task body.

## Goal

Remove SOUL.md support entirely. The system should use ONLY `MEMORY.md` (which may
include anything that could have lived in SOUL.md). A single `MEMORY.md` file lives at
the **profile directory root** (e.g. `profiles/omni/MEMORY.md`), NOT inside
`memories/`.

**Transitional requirement (user):** initially copy and keep BOTH files before the
next released version — so a profile has both `profiles/omni/MEMORY.md` AND
`profiles/omni/memories/MEMORY.md` (same content). The code reads the ROOT
`MEMORY.md`; the `memories/MEMORY.md` copy remains only as a transitional duplicate
and is dropped in the next release (deferred, NOT part of this task's removal scope —
just keep it present and synced).

## Verified inventory (do not re-derive — grep at create time)

### omniagent (nexuslbs/omniagent)

Prompt plugin returns a `"soul"` field; omniagent consumes it:

- `plugins/tools/prompt/src/main.rs:1559` — result JSON includes `"soul": soul`
- `plugins/tools/prompt/src/main.rs:1323-1347` — splits prompt parts into
  system/memory/soul (`soul_text` = the `system_message` part)
- `src/agent/context_builder.rs:13` — `PromptParts.soul: String`
- `src/agent/context_builder.rs:79` — `soul: parsed["soul"].as_str().unwrap_or("").to_string()`
- `src/agent/main_loop.rs:239-240` — planning messages push `prompt_parts.soul` as system msg
- `src/agent/main_loop.rs:498-499` — main messages push `prompt_parts.soul` as system msg

Memory API supports a `soul` type that maps to `USER.md`:

- `src/server/memory.rs:426-434` — `resolve_memory_path`: `"soul" => "USER.md"` (memory → MEMORY.md)
- `src/server/memory.rs:455-472` — `edit_handler` maps `"soul" => "USER.md"`, writes to `profiles/<p>/memories/`
- `src/server/memory.rs:545-561` — `upload_handler` same mapping
- `src/server/memory.rs:515-543` — `text_handler` reads via `resolve_memory_path`
- Routes: `GET/POST /memory/text|upload|edit/{profile}/{type}` (memory.rs:33-37)

Settings expose `soul_max_chars`:

- `src/server/settings.rs:166` — `soul_max_chars` in the `general` settings group
- `src/server/settings.rs:418-421` — SettingMeta "Max characters for SOUL.md in the system prompt"
- `src/server/settings.rs:659` — `"soul_max_chars" => "memory"` category
- `src/server/settings.rs:760` — in the settings whitelist

Server volatile-tier placeholder:

- `src/server/mod.rs:855` — comment "Volatile tier: memory/soul placeholders"
- `src/server/mod.rs:867` — `<<soul>>` placeholder in LOCKED INSTRUCTIONS

Prompt plugin config + memory store:

- `plugins/tools/prompt/plugin.json:43` — `soul_max_chars` config_schema entry ("Soul (User Profile) Max Chars")
- `plugins/tools/prompt/src/main.rs:60,85,154-155,165` — `soul_max_chars` config field/parse
- `plugins/tools/prompt/src/memory_store.rs:84-85` — loads `memories/MEMORY.md` + `memories/USER.md`
- `plugins/tools/prompt/src/memory_store.rs:87-93` — MEMORY.md sha256 hash tracking
- `plugins/tools/prompt/src/prompt_builder.rs:17-18,24-25` — `memory_max_chars`/`soul_max_chars` builder config
- `plugins/tools/prompt/src/prompt_builder.rs:227-240` — `read_user_profile_section` (USER PROFILE section)
- `plugins/tools/prompt/src/prompt_builder.rs:319-324` — memory + user sections pushed into parts

**Target memory path:** `profiles/<profile>/MEMORY.md` (profile root). The prompt
plugin's `MemoryStore` currently joins `base_path/memories` — change to read the root
`MEMORY.md` (base_path itself, i.e. `profiles/<profile>/MEMORY.md`), keeping the
transitional `memories/MEMORY.md` duplicate on disk untouched.

### omni-dashboard (nexuslbs/omni-dashboard)

Memory page has a SOUL card + upload/edit wiring:

- `src/pages/memory.ts:65-82` — Block 4: SOUL card (title "💫 SOUL", edit btn, pre#mem-soul-text, textarea#mem-soul-editor, save/cancel, upload btn + file input)
- `src/pages/memory.ts:154-160` — SOUL upload wiring (`uploadMemoryFile(file, "soul")`)
- `src/pages/memory.ts:168-171` — SOUL edit wiring (`startEdit("soul")` / `saveEdit("soul")`)
- `src/pages/memory.ts:233` — `loadSoulText()` in init
- `src/pages/memory.ts:356-365` — `loadSoulText()` → `GET /memory/text/{profile}/soul`
- `src/pages/memory.ts:367-385` — `uploadMemoryFile(file, type: "memory" | "soul")`
- `src/pages/memory.ts:396-426` — `startEdit(type: "memory" | "soul")`
- `src/pages/memory.ts:426-460` — `saveEdit(type: "memory" | "soul")` → `POST /memory/edit/{profile}/{type}`

**Required:** Memory page has NO soul section anymore. Upload/edit/delete API calls
only use type `memory`. The SOUL card (Block 4) is removed.

### omni-deployer (nexuslbs/omni-deployer)

Integration tests cover soul/USER.md:

- `scripts/tests.py:2549` — `for f in ["MEMORY.md", "USER.md"]:` cleanup loop
- `scripts/tests.py:2563` — asserts `memories/USER.md` does NOT exist after edit-memory
- `scripts/tests.py:2573-2579` — `test_m3_edit_soul` (edit SOUL → USER.md created)
- `scripts/tests.py:2582-2594` — memory/soul consistency test (reads USER.md from disk)
- `scripts/tests.py:2648` — MEMORY.md path checks (`memories/MEMORY.md`)

**Required:** soul/USER.md test cases removed or reworked to memory-only. Tests that
check the memory file location must target the profile ROOT `MEMORY.md`.

### omni-stack / omni-root (profile layout)

Current: `profiles/omni/memories/MEMORY.md` exists (both repos, same 7704-byte file).
No `profiles/omni/MEMORY.md` at root yet. No USER.md exists anywhere.

**Required (transitional):** copy `memories/MEMORY.md` → `profiles/omni/MEMORY.md`
in both repos so BOTH exist. Commit both. The root file is the canonical one going
forward; `memories/MEMORY.md` stays as the transitional duplicate (dropped in the
next release — separate step, not this task).

## Non-goals / DO NOT CHANGE

- Do NOT delete `profiles/omni/memories/MEMORY.md` — keep it (transitional duplicate).
- Do NOT change `MEMORY.md` CONTENT semantics — memory entries stay as-is.
- Do NOT touch channels/plugins/settings unrelated to soul/memory.
- Do NOT change the `memory` type behavior of `/memory/text|upload|edit/{profile}/memory` beyond the path change (profile root).
- Do NOT remove the `memories/` directory itself.
- The `USER PROFILE` section concept: it can be folded into MEMORY.md content (user: "MEMORY.md that may include things that could be included in SOUL.md") — but the profile files are just markdown; no separate USER.md file should be created or read.

## Verification gates

- `grep -rn "soul\|SOUL\|USER.md" src/ plugins/` in omniagent → no code refs except possibly comments explaining removal history
- `grep -rn "soul" src/` in omni-dashboard → none
- `cargo check --workspace --all-targets` in omniagent (dev overlay, SQLX_OFFLINE=false)
- `cargo test` in omniagent
- `npm run build` in omni-dashboard
- `python3 -m py_compile scripts/tests.py` in omni-deployer; run the memory group (tests.py) via `deploy.py dev` or targeted group
- Prompt plugin response JSON has NO `"soul"` key: call the prompt tool / GET the prompt for a thread and assert `soul` absent
- `GET /memory/text/{profile}/memory` returns the ROOT MEMORY.md content
- `GET /memory/text/{profile}/soul` → 400 (type no longer valid)
- `profiles/omni/MEMORY.md` AND `profiles/omni/memories/MEMORY.md` both exist with identical content (both repos)

## Deliverable

- Commit + push to origin/main in EVERY touched repo: omniagent, omni-dashboard, omni-deployer, omni-stack, omni-root. Report each commit SHA.
