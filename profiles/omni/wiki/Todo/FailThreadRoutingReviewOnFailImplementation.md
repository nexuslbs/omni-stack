# Fail-Thread Routing (review_on_fail) + Double-Normalization Fix

**Status:** Planned (mirrors kanban task — see board)
**Date:** 2026-08-17
**Scope:** omniagent (`src/agent/fail_thread.rs` + unit/integration tests)

## Goal

Fix the fail-thread transition matrix so the `review_on_fail` workflow flag is
actually honored, and repair the F0 (empty `workflow_step`) default which is
currently broken by double normalization.

## Background (observed 2026-08-17, task_18cc95fc8fbba9e0 thread #112)

- Tester thread #112 called `builtin_fail-thread` with **NO** `workflow_step`
  (F0 = executor default) → task went **BLOCKED** instead of re-running the
  executor / going to review.
- History row: *"Task failed in thread #112. Moving kanban task to 'blocked'
  status due to invalid workflow_step for status testing"* — i.e. the F0
  default resolved to "invalid" (F4 → blocked).
- The reviewer thread #110, by contrast, called fail-thread with an explicit
  `workflow_step: "running"` and the engine correctly created executor re-run
  thread #111. So explicit steps work; the EMPTY default is broken.

## Root cause: double normalization in fail_thread.rs

`normalize_workflow_step()` is applied **twice** on the same value:

1. `fail_thread_tool` (line 541): `let step = normalize_workflow_step(workflow_step);`
   — `None`/`""` → `"executor"` (F0 = re-run executor).
2. `engine_transition` (line 833, `RerunKind::FailTool` arm):
   `let normalized = normalize_workflow_step(Some(step.as_str()));`
   — re-normalizes `"executor"` → **`"invalid"`** (F4 → blocked), because the
   function only accepts `""`/`"running"`/`"testing"`/`"blocked"` as inputs,
   not its own output `"executor"`.

Explicit values (`"running"`, `"testing"`, `"blocked"`) are idempotent, which
is why reviewer #110's explicit call worked while tester #112's empty call
broke. The unit test `route_fail_tool_f0_executor` passes only because it
calls `route_fail_tool("executor", ...)` directly, bypassing the double
normalization.

## Verified facts (do not re-derive — greps from 2026-08-17)

- `src/agent/fail_thread.rs`:
  - `normalize_workflow_step` (:437-445): `""→executor`, `running→running`,
    `testing→testing`, `blocked→blocked`, `_→invalid`.
  - `route_fail_tool` (:673-717): pure F-matrix —
    F0 `executor` → re-run executor if has_wf else blocked;
    F1 `running` → executor rework (valid callers: testing/review/running);
    F2 `testing` → re-test (caller must be review);
    F3 `blocked` → blocked; F4 `_` → blocked.
  - `fail_thread_tool` (:532-636): normalizes (1st), persists Error message,
    ends thread FAILED, calls `apply_fail_step_transition` (:1193-1212) →
    `engine_transition` (RerunKind::FailTool).
  - `engine_transition` (:749-1189): atomic tx; retry guard (limit =
    retries + 1, :915-939); D7 `clear_executions_on_review` → executor/tester
    limit sends to review (+ zero counters); reviewer limit ALWAYS blocked;
    `block_reason` mapping (:843-860).
  - `retry_limit` (:518-526) = role override retries, else workflow default,
    else 0, **+1**.
- `review_on_fail` / `auto_approve` flags are being added by the sibling task
  (WorkflowRoleModeAutoApproveImplementation) — this task builds on them.
  This task does NOT re-implement the flags; it wires `review_on_fail` into
  the fail-thread transition decision.
- workflows.yml (`config/workflows.yml:1-51`): `omniagent-dev` has
  `retries: 3`, `clear_executions_on_review: true`, roles executor/tester/
  reviewer.

## Requirements

### 1. Fix the double normalization (F0 must actually re-run the executor)

In `engine_transition`'s `RerunKind::FailTool` arm, the incoming `step` is
ALREADY normalized by `fail_thread_tool`. Do not normalize again:

```rust
RerunKind::FailTool { step } => {
    let normalized = step.as_str(); // already normalized by fail_thread_tool
    ...
```

(Or, equivalently, make `normalize_workflow_step` idempotent by accepting its
own outputs — but the single-call fix is minimal and keeps the F-matrix
meaning clear. Prefer the single-call fix; update the comment at
`normalize_workflow_step` to document that callers must pass the RAW tool
argument exactly once.)

After the fix: `fail-thread` with NO `workflow_step` from an executor or
tester thread → F0 → **re-run the executor** (task → `running`, new executor
thread) when `has_wf`, matching the documented F0 semantics and the existing
unit test.

### 2. Wire `review_on_fail` into the fail-thread transition

The workflow-level `review_on_fail` flag (added by the sibling task) must be
honored by `route_fail_tool` / `engine_transition`:

**When `review_on_fail = true`:**
- **Tester fail with NO `workflow_step` (F0) → go to REVIEW** (reviewer step),
  NOT blocked, NOT executor re-run. The reviewer decides.
- **Only the reviewer can send the task to `blocked`**, in exactly these cases:
  1. reviewer explicitly calls fail-thread with `workflow_step: "blocked"`; or
  2. the reviewer's retry limit is reached (D7 guard — reviewer is never
     overridden, unchanged boundedness guarantee).
  (Plus the existing skip path: thread/channel explicitly stopped or closed —
  R3 re-schedule, no retry consumed, status unchanged.)
- Therefore, with the flag true, ANY non-reviewer fail request that would land
  on `blocked` must instead route to **review**:
  - F0 from a tester → review (explicit user rule above).
  - F0 from an executor → executor re-run is NOT blocked, so keep F0 executor
    re-run? NO — user rule for the flag: failed steps go to review instead of
    blocked, and the reviewer decides. See the matrix below.
  - F3 explicit `workflow_step: "blocked"` from a non-reviewer → review
    (the flag means only the reviewer may block).
  - F4 invalid value from a non-reviewer → review.
  - Retry-limit hit on executor/tester step (without D7 clear) → review
    instead of blocked.
- **Skip (thread/channel stopped/closed) → unchanged**: re-schedule the same
  step, no retry consumed, status unchanged (R3).

**When `review_on_fail = false` (default):** current behavior unchanged after
the double-normalization fix (F0 → executor re-run, F1/F2/F3/F4 as today,
D7 as today).

**Routing matrix (target status):**

| Caller | workflow_step | review_on_fail=false | review_on_fail=true |
|---|---|---|---|
| tester | (none) F0 | running (executor re-run) | **review** |
| tester | running | running | running |
| tester | blocked | blocked | **review** (only reviewer may block) |
| executor | (none) F0 | running | **review** (failed steps → review; reviewer decides) |
| executor | running | running | running |
| reviewer | (none) F0 | running | running |
| reviewer | blocked | blocked | blocked (reviewer may block) |
| reviewer | testing | testing (re-test) | testing |
| any | invalid F4 | blocked | **review** (non-reviewer) / blocked (reviewer) |
| any | retry-limit hit (non-reviewer step) | blocked (or review if D7 clear) | **review** (non-reviewer) / blocked (reviewer) |
| any | skip (stop/close) | same-step re-schedule, no retry | unchanged |

Implementation notes:
- `route_fail_tool` needs the flag: add a `review_on_fail: bool` parameter
  (and the caller's role — it already receives `caller_step`, so the reviewer
  caller can be detected via `caller_step == Some("review")`).
- `engine_transition` resolves the flag from the task's workflow
  (`workflows.yml` → `workflow.auto_approve`/`review_on_fail`); remember the
  sibling task's rule: `auto_approve=true` forces `review_on_fail=false`.
- When routing to `review` with the flag true, mirror the existing D7 review
  thread creation path (create a review thread when the workflow has a
  reviewer role; otherwise land the task in `review` as a manual state).

### 3. Tester adds transition tests (unit + integration)

The tester role MUST add tests covering these transition cases, each with
`review_on_fail` BOTH `true` and `false`:

1. **Go to executor** — fail-thread with explicit `workflow_step: "running"`
   (from tester and reviewer callers) → executor re-run thread created, task
   status `running`.
2. **Tester failed WITHOUT specifying to go to anyone** — fail-thread with NO
   `workflow_step` (F0) from a tester thread:
   - `review_on_fail=false` → executor re-run (task `running`).
   - `review_on_fail=true` → review (reviewer thread created / task `review`).

Plus, at minimum, unit tests for:
- F0 empty default after the double-normalization fix
  (`normalize_workflow_step` single-call invariant; a regression test that
  exercises the FULL `fail_thread_tool → engine_transition` path with an
  empty `workflow_step`, not just `route_fail_tool` directly).
- Blocked-restriction: non-reviewer explicit `blocked` + flag true → review;
  reviewer explicit `blocked` + flag true → blocked.
- Retry-limit + flag true on an executor step → review (not blocked).

Unit tests go in `src/agent/fail_thread.rs` (extend the existing
`route_fail_tool_*` / `normalize_workflow_step` tests, keeping the pure
function style). Integration tests go in `scripts/tests.py` (new GROUP,
following the existing GROUP 22/39 pattern — create task, run role thread,
call fail-thread, assert kanban status + history comment). All tests must
pass with the flag both ways; do NOT weaken existing assertions.

## Non-goals

- Do NOT re-implement the `review_on_fail`/`auto_approve` flags themselves
  (sibling task owns workflows.yml parsing/dashboard).
- Do NOT change `auto_approve` semantics.
- Do NOT change interruption retries (max-LLM) — same-step re-run until
  retries+1, then the D7/flag-aware outcome (blocked, or review with the flag
  true for non-reviewer steps).
- No DB migrations.

## Verification

- `cargo fmt --all --check`, `cargo check --workspace --all-targets --release`
  with `RUSTFLAGS=-D warnings`, `cargo clippy -D warnings`, unit tests pass.
- Live verification on omnistable: a tester thread failing with NO
  `workflow_step` and `review_on_fail=false` → task `running` (executor
  re-run); with `review_on_fail=true` → task `review` (reviewer thread).
- New integration GROUP passes (both flag values).
- Commit + push when the step completes.
