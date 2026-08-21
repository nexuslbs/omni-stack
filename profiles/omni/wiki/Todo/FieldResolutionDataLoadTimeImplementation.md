# Resolve Fields With Fallback AT DATA-LOAD TIME (Phase 2: channel identity + kanban API)

**Status:** IMPLEMENTED + TESTED + APPROVED (2026-08-21)
**Task:** `task_18cd7ecb9817b677` — "Resolve fields with fallback AT DATA-LOAD
TIME (loaders return resolved data, never shallow values)"
**Repo:** `omniagent` (data loaders / resolvers). omni-stack / omni-deployer
untouched (no field source changed there).
**Related:** [Field-Resolution](../Reference/Field-Resolution.md) (the universal
rule) · [FailRoutingBoardFallbackImplementation](./FailRoutingBoardFallbackImplementation.md)
(Phase 1 — kanban task defaults at load)

## Principle (extends Phase 1)

Phase 1 resolved kanban TASK fields at load (`resolve_task_defaults`). This task
completes the same rule for the CHANNEL tier and for the kanban API surface:
loaders (channel definitions, task rows) must hand out RESOLVED values — never
shallow raw fields that have a fallback chain.

## Implementation — omniagent `57e16da` (3 files, +221/−15)

Commit message: `feat(resolution): resolve channel identity + task defaults AT
LOAD TIME (loaders return resolved data, never shallow values)`.
Pushed `f29e9a4..57e16da main -> main`.

**1. `src/resolution.rs` (+152)** — `ResolvedChannelIdentity` struct +
`resolve_channel_identity(data_dir, def)` — the canonical channel-tier resolver:

| Field | Fallback order |
|---|---|
| `profile` | channels.yml `profile` → `default_profile_name()` |
| `provider` | yml `provider` → resolved profile's `provider` → global default provider (`get_global().default_provider`) |
| `model` | yml `model` → profile model **ONLY when the channel does not pin a provider** → `resolve_default_model(provider)` |

Semantics mirror `resolve_thread_identity`'s channel tier exactly. 3 new unit
tests: `resolve_channel_identity_falls_back_to_default_profile`,
`resolve_channel_identity_passes_through_yml_fields`,
`resolve_channel_identity_preserves_wf_test_pins` (regression guard `83f461b`:
wf-test → noop/test-tool-caller preserved).

**2. `src/db/channels.rs` (+15)** — `def_to_channel` now resolves
profile/provider/model via `resolve_channel_identity` **on every load**
(`load_channels_from` re-reads channels.yml fresh per call — **no boot-time
cache**). All 7 call sites (`load_channels`, `get_by_name`, `get_all`, …) flow
through it. A `channels.yml` provider edit now takes effect on the very next
thread for that channel, no restart. This fixes the ROOT-CAUSE bug: an
mm-kanban → opencode-go provider edit was ignored — threads kept using
`deepseek`.

**3. `src/server/kanban.rs` (+69)** — `task_row_to_entry(data_dir, r)` runs
`resolve_task_defaults` (task → board → channel → global) right after fetch; all
3 call sites (list, get, tests) pass `state.data_dir`. The kanban API **no
longer hands out shallow board-based rows** (NULL channel/workflow/profile) —
list/get return RESOLVED values. Invalid board → warn + raw-row fallback
(display-only; dispatch still fails loudly, matching prior semantics).

## Verification

- **Executor (1754)**: `cargo check` clean; `cargo test` resolution suite 16
  passed + 3 new channel-identity tests (the default-profile test was fixed to
  assert against the ACTUAL global default); `cargo fmt` + `clippy -D warnings`
  OK. Initial run had 1 failure
  (`resolve_channel_identity_falls_back_to_default_profile`) — fixed by
  asserting the real global default instead of a hardcoded profile name.
- **Tester (1755)**: full cargo gate — `CHECK_EXIT=0, FMT_EXIT=0, CLIPPY_EXIT=0,
  TEST_EXIT=0, ALL_GATES_DONE` (every workspace test binary passes incl. the
  541-test and 44-test bins). Pushed `45bc5c2` `fix(fmt): rustfmt
  plugins/tools/prompt/src/compact.rs` — a PRE-EXISTING rustfmt violation in a
  file NOT touched by `57e16da` (compact.rs:674) failed the fmt gate; minimal
  fix, committed separately. omniagent HEAD == origin/main == `45bc5c2`;
  omni-deployer clean at `7e49bb8`. Rebuilt missing release bins in the dev
  stack (`mcp-server-prompt`, `mattermost-platform`) and restarted the container.
- **GROUP 47 live** (omni-deployer `scripts/tests.py` lines ~12449–12856,
  "Resolve fallback fields ONCE at load — kanban task defaults
  (task→board→channel→global)", 7 test fns): **G47_EXIT=0** — 47-A review rework
  → running + NEW executor thread; 47-B review retest → testing + NEW tester
  thread; 47-C review block → blocked, no new thread; 47-D status-change
  dispatch → thread row; 47-E redispatch; 47-F explicit task fields win over
  board; 47-G unknown-board fail-loud (HTTP 400).
- **Reviewer (1756)**: APPROVE — commits verified on origin/main, code inspected
  in full, repo hygiene PASS (only source files at HEAD; no scratch/secrets —
  ancestor `8af0a28` carried smoke-test scratch files but they were removed by
  later commits and are absent at HEAD). Acceptance criteria all met; regression
  guard 83f461b holds.

## Notes / non-goals

- The running omnidev image was rebuilt/restarted during testing with the new
  binaries — "live" durability still depends on the release loop (`deploy.py
  dev`) rebuilding the image, as with all tasks.
- `plugins/tools/prompt/src/compact.rs` shows as modified in the working tree —
  deliberately untouched (another task's work).
- Display APIs: `GET /kanban/tasks` now returns RESOLVED values; `/channels` and
  `/threads` still report raw stored fields (per the Field-Resolution rule).
