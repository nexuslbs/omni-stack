# Run deploy.py hybrid within strict token budget (Implementation)

**Status:** Todo (mirrors kanban task — see board)
**Date:** 2026-08-22
**Scope:** omni-deployer (deploy.py hybrid) + omniagent agent efficiency
**Workflow:** dev-executor (executor-only, auto_approve)

## Goal

Run `python3 deploy.py hybrid` in `/opt/workspace/omni-deployer` to successful
completion (build images locally like CI would → start omnideploy stack →
migrations → pretests → shared tool tests), fixing any issue that happens in
the middle.

**Hard token budget (HERMES-enforced, the acceptance gate):** for the task's
executor thread(s), measured on the `threads` table:
- **cache hit (`sum(cached_tokens)`) ≤ 2,000,000 tokens total**
- **cache miss (`sum(input_tokens - cached_tokens)`) ≤ 200,000 tokens total**

These are the same gates as the user's standing cache requirement (cache hit
ratio ≥ 95%: 2M/2.2M = 90.9% is the floor implied by the absolute caps; the
absolute caps are the hard stop).

## Why (verified facts — do not re-derive)

- `deploy.py hybrid` (omni-deployer): build images locally tagged
  local/omniagent:latest + local/omni-dashboard:latest + local/omni-toolbox:latest
  (production Dockerfile builder stage runs fmt/check/clippy/test offline against
  the committed .sqlx cache), then up + migrations (production image has
  db-migrations) + pretests + shared tool tests. Base compose = image-only.
- **Hybrid stops NEITHER omnidev NOR omnistable** (omni-deployer `a62dc71`,
  2026-08-22: MODE_STOP_EXCLUDE hybrid = {omnidev, omnistable}) — safe to run
  from the omnistable agent container; it manages only its own omnideploy_*
  containers/volumes.
- Token recording is live: `threads.input_tokens / cached_tokens /
  output_tokens` + `messages.token_usage` JSONB (prompt_tokens / cached_tokens /
  completion_tokens).
- Baseline: prior chain task thread 80 = 848,969 input / 721,024 cached /
  127,945 miss — within the caps. A deploy-fix task must stay token-efficient
  (search-first, small read windows, wait-task not polling, commit-early).
- **Task-executor thread is the token furnace risk**: prior deploy-fix threads
  (2026-08-12) burned 10–27M tokens from re-read loops + one-shell-per-call
  exploration. The dev-executor template already mandates: ≤10 exploration
  calls, READ FILES ONCE → notes, wait-task with generous timeouts, commit
  early. Those rules are the budget's main defense.

## Token budget measurement (HERMES side)

```sql
-- per task: executor thread(s) token sums
SELECT t.id, t.status,
       sum(t.input_tokens)  AS input,
       sum(t.cached_tokens) AS cached,
       sum(t.output_tokens) AS output,
       sum(t.input_tokens - t.cached_tokens) AS miss
FROM threads t WHERE t.task_id = '<task_id>' GROUP BY t.id, t.status;
-- GATES: cached <= 2,000,000 AND miss <= 200,000
```

If a thread is mid-run, live-check `messages.token_usage` sums for the thread
(same fields) so we can stop BEFORE the caps are breached.

## Task steps (for the executor)

1. Run `python3 deploy.py hybrid` in `/opt/workspace/omni-deployer` inside the
   omnistable agent container (`/opt/workspace/omni-deployer` is bind-mounted).
2. Fix any issue mid-run (script bugs, test failures, build failures) — commit
   + push fixes to nexuslbs/omni-deployer (or omni-stack if the fix lands
   there) with clear messages.
3. Verify: deploy exits 0, "ALL TESTS PASSED", omnistable + omnidev containers
   untouched (count before == after), omnideploy stack started.
4. Report each step's result + remaining blockers.

**Token-efficiency rules (MANDATORY — this is a budget-gated task):**
- ≤10 exploration calls; read each file ONCE and put facts in notes.
- Prefer filesystem_search (names) / content grep for locating code over
  whole-file reads; use offset/limit paging for large reads.
- Long commands → `builtin_wait-task(task_id, timeout_secs=900, tail=2000)`
  immediately; NEVER poll, NEVER pass timeout on docker_compose.
- Commit after each logical unit; a thread can die at any moment.

**Safety invariants (HARD):**
- NEVER stop/restart omnistable or omnidev containers (deploy.py hybrid must
  not either — if the script would, FIX the script first).
- Only omnideploy containers/volumes are touched by the deploy.

## Acceptance criteria

- `deploy.py hybrid` exits 0 with "ALL TESTS PASSED".
- Executor thread token sums within caps: cached ≤ 2M AND miss ≤ 200K.
- omnistable/omnidev container counts unchanged before/after.
- Any fix committed + pushed with clear message; summary lists results +
  remaining blockers.

## Hermes enforcement loop (after task dispatch)

1. Monitor the task's executor thread(s) token sums (SQL above).
2. If caps breached mid-run → STOP (stop-thread), then fix: omnidev/agent
   prompts, skills/wikis, prompt-generate + compact-messages tools, tools that
   limit output, templates indicating different tools. Then re-run `deploy.py
   dev` (the faster dev-mode chain) and re-measure.
3. Repeat until caps respected.

## Non-goals

- No changes to omnistable stack config (channel provider failover stays as-is).
- No real-LLM key changes.

## Execution history

- **2026-08-22 first attempt (thread 81) FAILED pre-work**: `The LLM provider
  returned an error 3 consecutive times (max 3). Last error: rate limited
  (HTTP 429); retry after 141801s. The thread was marked as failed.` No code
  or config changes were made. Re-run the task when the provider quota allows
  (see Reference/Omni-Deployer.md — provider 429 failure mode).
