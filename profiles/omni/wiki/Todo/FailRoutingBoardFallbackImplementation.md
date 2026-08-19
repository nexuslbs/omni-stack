# Resolve Fallback Fields ONCE at Load — Universal Resolution Pattern (kanban tasks, channels, provider/model, settings)

**Status:** Todo (task 17 — LAST in the serial chain, after models.yml task 16)
**Date:** 2026-08-19 (generalized twice: fail-routing bug → kanban task fields → ALL fallback fields)
**Scope:** omniagent (resolution pattern + all domains with fallbacks)

## Goal (user principle 2026-08-19 — do NOT re-litigate)

ANY place that uses fields that have fallbacks — **kanban task fields
(workflow, channel, profile, plan, provider, model) being ONE such case, but
also channel fields, provider/model fields, settings fields — anywhere there
is such a fallback chain — MUST resolve the fallbacks FIRST before any
shallow use of the raw fields.** The fix applies to ALL such cases. The code
should be more robust: **resolve fallbacks EARLIER rather than later — as
close as possible to where the values are loaded** (compute the effective
values once at load; consumers use the resolved values).

Kanban task fields are the pilot case (a live bug); the same pattern extends
to every other domain with fallbacks.

## Fallback domains (verified chains, 2026-08-19)

1. **Kanban task fields** — documented resolution order
   `Workflow Role > Workflow > Kanban Task > Board > Channel > Global
   Settings` (config/boards.yml). Task.workflow_id/channel_id/profile/plan/
   provider/model are NULL for board-based tasks; the board (boards.yml by
   task.board) and channel/global settings supply the effective values. The
   DISPATCH path resolves them; fail routing does NOT (the bug below).
2. **Channel fields** — channels.yml fields fall back through
   `resolve_default_channel(id_or_name, default_key)` (channels_yaml) to a
   default channel key in settings, then to "". Channel profile/provider/
   model fields fall back to global settings; consumers must use the
   effective channel, not the raw name.
3. **Provider/model resolution** — per-thread provider/model fallback:
   thread-stamped → channel → profile → global settings → env
   (LLM_PROVIDER/LLM_MODEL with openai/gpt-4 fallbacks; profile-level fields
   are stored but not consulted — verify). Resolve once per thread at
   creation; consumers use the resolved provider/model.
4. **models.yml** (task 16) — model_config > provider(models.yml) > global
   settings (defaults soft 100000 / hard 500000). Same pattern; omniagent
   resolves and passes down (compact-messages params).
5. **Settings defaults** — settings.yml value → defaults table
   (settings.rs); AgentConfig already reads via `get(key, default)` —
   formalize as resolved-at-load snapshot fields.

## Triggering bug (live-verified 2026-08-19)
Fail routing in `src/agent/fail_thread.rs` resolves the workflow ONLY from
`kanban_tasks.workflow_id` (engine_transition ~830-847; manual-review
~290-297). Board-based tasks have workflow_id NULL → has_wf=false →
has_executor_role=false → route_fail_tool F1 ("running") → blocked. Live:
reviewer thread 51 called builtin_fail-thread workflow_step="running"; log
`transition=no re-run thread (blocked or non-workflow task)`; kanban_history
#127 "no executor role in workflow for status review". Task blocked instead
of executor rework.

## Verified audit of shallow consumers (grep 2026-08-19)

- src/agent/fail_thread.rs — raw task.workflow_id 291/296/352/830 + raw
  task.channel_id 343.
- src/db/threads.rs — thread creation resolves channel (~1453) and workflow
  (~1477) with PARTIAL fallbacks; plan/profile/provider/model inserted from
  raw task fields (77/380/710/908/1507).
- src/kanban_dispatch.rs — per-consumer resolve_task_channel (125) + board
  fallback (290) — LOCAL resolver, not shared.
- src/server/kanban.rs — status transitions + resolve_workflow_reset (2208) +
  workflow reads (2305).
- src/kanban_action.rs — action context workflow_id (139/183/206).
- src/boards.rs — boards_enabled (175) + task_board (186) exist but NO full
  task-defaults resolver.
- Channel/provider-model chains: consumers read raw channel_name /
  thread.provider / thread.model across llm/mod.rs, threads.rs, server/
  without a shared resolved-at-load struct.

## Requirements

1. **Resolution pattern (shared, documented)**: per domain, ONE resolver
   returning a resolved struct computed AS EARLY as possible (right after the
   row/config is loaded):
   - `ResolvedTaskDefaults { workflow_id, channel_id, profile, plan,
     provider, model }` ← `resolve_task_defaults(data_dir, task)`
     (task → board → channel/global settings);
   - `ResolvedChannel` / effective-channel helper (channels_yaml): raw name →
     default chain, profile/provider/model fallbacks applied once;
   - `ResolvedThreadProviderModel { provider, model }` ← resolved once per
     thread at creation (thread → channel → profile → settings → env);
   - settings snapshot fields (already `get(key, default)` — expose resolved
     fields on AgentConfig, no repeated get-with-default).
   Place the resolvers together (boards.rs + new src/resolution.rs or per
   domain next to their config module). Consumers take the RESOLVED struct.
2. **ALL consumers switch to resolved values — phase by domain**:
   - Phase 1 (the bug): kanban task resolution in fail_thread.rs
     (engine_transition + manual-review + re-run thread creation),
     db/threads.rs thread creation, kanban_dispatch.rs (replace local
     resolve_task_channel), status-change dispatch, /redispatch, startup
     recovery, kanban_action.rs context, server/kanban.rs transitions.
   - Phase 2: channel field resolution (effective channel name + channel
     profile/provider/model) — all consumers.
   - Phase 3: provider/model resolution per thread — all consumers.
   - Phase 4: settings resolved-at-load snapshot (no scattered defaults).
   Display-only API responses (GET /kanban/tasks, /channels, /threads…)
   keep the raw stored fields — behavior uses resolved values.
3. **No divergence**: every consumer of a domain uses the SAME resolver
   (extract + share; no per-consumer resolvers).
4. **Robustness**: unknown/malformed board/channel → explicit error at
   resolution time (fail loud, mirror task_board semantics), never a silent
   empty fallback that changes behavior.
5. **Documentation**: add a Reference page (e.g.
   `Reference/Field-Resolution.md`) stating the principle + the per-domain
   resolvers + "never shallow-read a field that has a fallback" rule, so
   future code follows it.
6. **Regression tests** (per domain):
   - kanban: board task (workflow_id NULL) + reviewer fail `running` → running
     + NEW executor thread (the bug); reviewer fail `testing` → tester thread;
     tester F0 → executor re-run (or review per review_on_fail); reviewer
     explicit `blocked` → blocked; status-change dispatch + redispatch resolve
     from board; thread creation resolves plan/profile/provider/model from
     board; NON-board tasks unchanged.
   - channels: effective channel resolution (name + profile/provider/model
     fallback) with and without defaults; unknown channel → explicit error.
   - provider/model: thread resolution chain incl. env fallbacks; stored vs
     resolved distinction.
   - settings: resolved snapshot equals get(key, default) results.
7. **Live verification** (omnidev): board-task reviewer-reject → rework
   thread; kanban_history "Creating thread #N" for step 'running' (not the
   "no executor role" block); status-change dispatch on a board task lands on
   the board channel.

## Non-goals / DO NOT CHANGE

- F0-F4 matrix semantics, review_on_fail, auto_approve — UNCHANGED (only
  field RESOLUTION changes).
- boards.yml / channels.yml / settings.yml content, task/channel creation,
  display API response shapes.
- models.yml chain itself (task 16 owns it) — this task only provides the
  shared pattern it should follow.

## Verification gates

- cargo check / clippy -D warnings / cargo test / fmt --check clean.
- deploy.py dev passes (omni-deployer dev-flavor).
- Grep audit gate: no behavior-path consumer reads raw
  task.workflow_id/task.channel_id/task.profile/task.plan/task.provider/
  task.model, raw channel_name-with-fallback, or raw thread.provider/model
  outside the domain resolvers + display-only responses.
- Live smoke (omnidev): kanban board-task F1/F2/F3/F0 + dispatch/redispatch;
  channel + provider/model resolution behave identically to explicit-field
  cases.

## Deliverable

omniagent commit(s) + SHAs + test/live evidence + Reference/Field-Resolution.md.
Standing release loop: tasks → deploy.py dev → main → stable (never push
stable while omnistable tasks run). Until the fix ships, board-task fails
block — recover manually (REDISPATCH NOTE + PATCH status → running).
