# Global `max_tokens_on_truncation`: escalate output budget on finish_reason=length (Implementation)

**Status:** Running (mirrors kanban task `task_18cb78c5045bae48` — see board)
**Date:** 2026-08-14 (rewritten from the per-role design of 2026-08-13)
**Scope:** omniagent + omni-stack

## Goal

ONE simple mechanism replaces the previously-planned per-role `max_tokens`
design and the "fail fast on reasoning-only truncation" heuristic: a global
`max_tokens_on_truncation` setting. Normal LLM calls keep the small global
`max_tokens` (4096); when a response is truncated (`finish_reason=length`),
the retry uses `max_tokens_on_truncation` (larger, e.g. 16384) so the model
gets a second chance with a bigger output budget — and if it STILL truncates
with the larger budget, fail fast (give up truthfully, no infinite loop).

## Why (verified live)

- `settings.yml:10` sets `max_tokens: 4096` (global; code default is 32768 at
  `config.rs:219` but settings.yml overrides it). `main_loop.rs:753` sends
  exactly `cfg.config_snapshot().max_tokens` to the LLM (`llm/mod.rs:907`
  `"max_tokens": request.max_tokens`). This request field IS the hard output
  ceiling — the provider truncates at that count and reports
  `finish_reason=length`.
- The advisory system message at `main_loop.rs:442-452` already tells the
  model its output ceiling and to chunk large writes — it must use the
  EFFECTIVE budget for the current attempt (normal vs escalated) so the hint
  matches reality on retries.
- Review thread 290 (channels.yml task, deepseek-v4-flash) died at iteration
  40 with 3 consecutive `finish_reason=length` truncations: it read the
  25K-char task body (prompt 36-46K tokens), started reasoning, blew the 4096
  output budget (reasoning counts against it), and every retry regenerated the
  same long reasoning chain and hit the same wall → "gives up truthfully" →
  thread failed.
- The retry nudge at `main_loop.rs:1017-1022` says "Continue exactly where you
  left off" — wrong for reasoning models: they restart reasoning from scratch
  and burn the whole budget on reasoning again. AND the retry reuses the SAME
  `max_tokens` — so even a perfect nudge can't succeed when the model needs
  >4096 output tokens.

## Why NOT per-role max_tokens (rejected design)

The original plan (2026-08-13) added `max_tokens` to workflow roles
(`WorkflowDefaults`), a nullable `threads.max_tokens` column + migration, and
threaded it through `resolve_step_identity` → step-thread creation. Rejected
by the operator 2026-08-14: heavy machinery (schema change, migration,
workflow config) for what is fundamentally an output-budget escalation
problem. The escalation approach needs NO schema change and NO workflow
changes — one setting + retry-budget logic.

## Design (executor picks cleanest implementation)

1. **New setting** `max_tokens_on_truncation: u32` in
   `omni-stack/config/settings.yml` `general:` section (explicitly set 16384;
   code default also 16384 at `src/agent/config.rs` next to `max_tokens`
   `:74`, `:219`).
2. **Escalated retry on truncation.** In `main_loop.rs` truncation branch
   (`:998-1027`), on `finish_reason=length`:
   - Track an `escalated_max_tokens: Option<u32>` state for the thread's
     current call sequence.
   - First truncation → set effective budget = `max_tokens_on_truncation`,
     append the truncated reasoning to the conversation (reasoning-forward:
     push the response's `reasoning` as a compact system note or assistant
     reasoning_content so the model does NOT re-derive it), nudge with a
     SHORTER-answer message ("Your previous response was cut off by the token
     limit (attempt 1/2). The reasoning above is preserved. Produce a SHORTER
     response now: emit a single small tool call or a concise final answer. Do
     NOT regenerate the long reasoning chain."), retry once.
   - If the retry truncates AGAIN (finish_reason=length with the escalated
     budget) → fail fast: `final_tool_call=false; break` (the post-loop
     give-up fallback reports it truthfully). Do NOT retry a third time with
     the same budget.
   - If the escalated retry succeeds → reset the escalation state.
3. **Effective budget everywhere.** `main_loop.rs:753` uses
   `escalated_max_tokens.unwrap_or(cfg.config_snapshot().max_tokens)`; the
   Output Limit system message at `:442` uses the same effective value.
4. **Request-level enforcement is unchanged** — `max_tokens` stays in the
   request body (`llm/mod.rs:907`); we only vary its value per attempt.
5. **Remove the per-role design entirely** — no `threads.max_tokens` column,
   no migration, no `WorkflowDefaults.max_tokens`, no workflows.yml role
   changes, no `resolve_step_identity` extension, no `kanban_updater` changes.
6. **Remove the "fail fast on reasoning-only truncation" heuristic** —
   replaced by the escalation mechanism. A reasoning-only truncated response
   is now retried ONCE with the bigger budget + preserved reasoning; only a
   second truncation fails fast. The voluntary-stop reasoning-only TERMINAL
   state at `main_loop.rs:982-991` stays untouched (deliberate stop, not
   truncation).

## Verified inventory (do not re-derive)

- `settings.yml:10` — `max_tokens: 4096` (global; code default 32768 at
  `config.rs:219`)
- `src/agent/config.rs:74` — `pub max_tokens: u32` in `AgentConfig`
- `src/agent/main_loop.rs:753` — `max_tokens: cfg.config_snapshot().max_tokens`
  (the per-call completion request)
- `src/agent/main_loop.rs:442` — `max_output_tokens` (Output Limit system msg)
- `src/agent/main_loop.rs:998-1027` — truncation branch: `finish_reason ==
  "length"` → `llm_error_retries += 1`; at 3 consecutive → "giving up
  truthfully" (`final_tool_call=false; break`); else retry nudge at
  `:1017-1022`
- `src/agent/main_loop.rs:982-991` — reasoning-only-with-no-tool-call is a
  TERMINAL state (voluntary stop) — separate from truncation, DO NOT touch
- `src/llm/mod.rs:907` — `"max_tokens": request.max_tokens` in the OpenAI
  request body

## Non-goals / DO NOT CHANGE

- Do NOT add per-role `max_tokens` or a `threads.max_tokens` column (no
  migration).
- Do NOT change the global `max_tokens: 4096` for normal calls — the whole
  point is a small default + escalation only when needed.
- Do NOT touch the voluntary-stop reasoning-only terminal path
  (`main_loop.rs:982-991`).
- Do NOT change executor-role budgets, plugin token budgets (prompt
  compact-messages), or `prune_old_tool_results`.
- Do NOT revert or commit sibling WIP (channels.yml, plan normalization,
  default channels, cron/hooks, channel_subscriptions, restart endpoint — all
  in-flight on the same working tree). Commit ONLY your own files.

## Verification gates (bare canonical commands, omnidev container)

- `cargo check --workspace` (dev overlay sets SQLX_OFFLINE=false; do NOT set
  `SQLX_OFFLINE=true` in the dev loop — CI-only)
- `cargo test --workspace`
- `cargo fmt --check`
- `cargo clippy --workspace -- -D warnings`
- Grep audit: `grep -rn 'Continue exactly where you left off' src/` must
  return NO matches (old nudge removed)
- Unit test: truncated response → retry uses `max_tokens_on_truncation` and
  includes preserved reasoning; second consecutive truncation →
  `final_tool_call=false` break (fail fast, no third retry); successful
  escalated retry → escalation state reset
- Verify `omni-stack/config/settings.yml` `general:` has
  `max_tokens_on_truncation: 16384`

## Deliverable

- Commit + push to origin/main: **omniagent** (code) + **omni-stack**
  (settings.yml). Report both commit SHAs.
