# Per-Role `max_tokens` + Reasoning-Aware Truncation Retry (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-13
**Scope:** omniagent + omni-stack

## Goal

Two related fixes for output-budget handling on workflow step threads:

1. **Per-role `max_tokens`**: let workflows.yml roles (reviewer/tester) raise the
   output token cap above the global `max_tokens: 4096` — DeepSeek v4 supports
   more output; 4096 is the limiter that killed review thread 290.
2. **Reasoning-aware truncation retry**: when the LLM response is cut at
   `finish_reason=length`, stop telling the model "continue exactly where you
   left off" (which makes DeepSeek restart its long reasoning chain and hit the
   same wall). Instead: fail fast on reasoning-only truncation (the thread-290
   signature) and/or nudge the model to produce a SHORTER answer.

## Why

- `settings.yml:9` sets `max_tokens: 4096` (global). `main_loop.rs:753` sends
  exactly `cfg.config_snapshot().max_tokens` to the LLM. For DeepSeek reasoning
  mode, **reasoning tokens count against that same budget** — a long review
  reasoning chain blows 4096 before content even starts.
- Thread 290 (review step, channels.yml task) died exactly this way: iter 35-39
  read the 25K-char task body (prompt at 36-46K tokens), iter 40 started
  reasoning, hit `finish_reason=length`, retried 3× (each retry regenerated the
  same long reasoning), then "giving up truthfully" → thread failed → retry 296.
- The retry nudge at `main_loop.rs:1017-1022` says "Continue exactly where you
  left off" — wrong for reasoning models: they restart reasoning from scratch,
  burn the whole budget on reasoning again, truncate again. 3 doomed retries.
- `workflows.rs` `WorkflowDefaults` (`:66-74`) has profile/provider/model/
  plan_mode/retries but **no `max_tokens`** — roles cannot raise their own cap.

## Verified inventory (do not re-derive)

- `settings.yml:9` — `max_tokens: 4096` (global; code default is 32768 at
  `config.rs:219` but settings.yml overrides it)
- `src/agent/config.rs:74` — `pub max_tokens: u32` in `AgentConfig`
- `src/agent/main_loop.rs:753` — `max_tokens: cfg.config_snapshot().max_tokens`
  (the per-call completion request)
- `src/agent/main_loop.rs:442` — `max_output_tokens` (Output Limit system msg)
- `src/agent/main_loop.rs:1003-1027` — truncation branch: `finish_reason ==
  "length"` → `llm_error_retries += 1`; at 3 consecutive → "giving up truthfully"
  (`final_tool_call=false; break`); else retry nudge at `:1017-1022`
- `src/agent/main_loop.rs:982-991` — reasoning-only-with-no-tool-call is a
  TERMINAL state (voluntary stop) — separate from truncation
- `src/workflows.rs:66-74` — `WorkflowDefaults` (flattened into both `Workflow`
  and `WorkflowRole`) — add `max_tokens: Option<u32>` here
- `src/workflows.rs:56-63` — `role_for_step("running"|"testing"|"review")`
- `src/agent/kanban_updater.rs:372-434` — `resolve_step_identity` returns
  `(profile, provider, model, plan, template)` — extend for max_tokens
- `src/agent/kanban_updater.rs:472` (`create_review_thread`) and `:549`
  (`create_testing_thread`) — both call `resolve_step_identity` then
  `create_thread` with identity fields; add max_tokens there
- `omni-stack/config/workflows.yml` `omniagent-dev` — reviewer + tester roles
  already have `plan_mode: on`; add `max_tokens: 16384` to both
- threads table has NO `max_tokens` column today (only provider/model/plan/
  template/workflow_id/workflow_step) — migration needed to store per-thread cap

## Design direction (executor decides cleanest implementation)

- Add `max_tokens: Option<u32>` to `WorkflowDefaults` (workflows.rs) so a role
  can set it; thread it through `resolve_step_identity` → step-thread creation
  (store on the thread, new nullable `threads.max_tokens` column + migration,
  consistent with how provider/model/plan/template are resolved once at
  creation) OR resolve per-call from workflows.yml — pick the consistent path.
- `main_loop.rs` uses the resolved per-thread value with fallback to global:
  `thread.max_tokens.unwrap_or(cfg.config_snapshot().max_tokens)` at `:753` and
  `:442`.
- Truncation retry (`:1003-1027`):
  - If the truncated response is **reasoning-only** (reasoning present, content
    empty, no tool calls) → **fail fast** (don't retry; break with
    `final_tool_call=false` so the truthful give-up fires). This is the
    thread-290 signature — a retry just regenerates the same long reasoning.
  - Otherwise (content/tool-calls were being produced) → change the nudge text
    to instruct a SHORTER answer: e.g. "Your previous response was cut off by
    the token limit. Produce a shorter response now: either a small tool call
    or a concise final answer. Do NOT regenerate a long reasoning chain."

## Non-goals / DO NOT CHANGE

- Do NOT change global `max_tokens` in settings.yml (operator may tune it
  separately; this task is about per-role override + retry behavior)
- Do NOT touch executor-role budgets unless trivially implied (executor keeps
  the global fallback)
- Do NOT change the reasoning-only TERMINAL state at `main_loop.rs:982-991`
  (that's a deliberate voluntary-stop contract, separate from truncation)
- Do NOT change plugin token budgets (prompt compact-messages) — unrelated
- Do NOT touch db-migrations unrelated to the new column; keep the migration
  ORDER-INDEPENDENT vs sibling tasks (channels/planning/default-channels all
  touch db-migrations/src/lib.rs)
- Do NOT revert or commit sibling WIP (channels.yml, plan normalization,
  default channels, cron/hooks, channel_subscriptions, restart endpoint —
  all in-flight on the same working tree). Commit ONLY your own files.

## Verification gates (bare canonical commands, omnidev container)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  `SQLX_OFFLINE=true` in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- If a new SQL query was added (threads.max_tokens read/write): run
  `cargo sqlx prepare --workspace` ONCE at the end with DATABASE_URL set, commit
  the changed `.sqlx/` files, and verify the CI path once with
  `SQLX_OFFLINE=true cargo check --workspace --all-targets`
- Verify `omni-stack/config/workflows.yml` shows `max_tokens: 16384` on both
  reviewer and tester roles of `omniagent-dev`

## Deliverable

- Commit + push to origin/main: **omniagent** (code) + **omni-stack**
  (workflows.yml). Report both commit SHAs.
