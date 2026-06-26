# Omni-Stack — AGENTS.md

## Planning Mode Resolution

Planning mode is resolved **at thread creation time** and stamped on `threads.planning_mode`.

**Source locations:**
- **Resolution:** `src/db/threads.rs` — `resolve_thread_planning_mode_with_content()` (core logic), `classify_complexity_for_planning()` (threshold logic), `resolve_cron_planning_mode()`, `resolve_max_plan()`
- **Max iterations:** `src/db/threads.rs` — `max_iterations_for_planning_mode()` maps mode → iteration cap
- **Prompt injection:** `src/prompt_builder.rs` — planning instructions injected based on `thread.planning_mode`
- **Table columns:** `threads.planning_mode` (runtime truth), `channels.planning_mode` (per-channel override), `cron_jobs.planning_mode` (per-job override)

**Modes:**

| Value | Meaning |
|-------|---------|
| `prompt_only` | No planning — LLM responds immediately |
| `auto_plan` | Single planning step before responding |
| `auto_subtasks` | Full subtask decomposition (only when explicitly configured — see below) |
| `always` | Legacy alias for `auto_subtasks` |

**When is `auto_subtasks` available?**

`auto_subtasks` (full subtask decomposition) is **not** the default. It is only available when explicitly configured in one of these ways:

- **Global `PLANNING_MODE` env var** set to `auto_subtasks` or `plan with subtasks`
- **Channel** `planning_mode` set to `auto_subtasks` or `always`
- **Cron job** `planning_mode` set to `plan_with_subtasks` or `auto_subtasks`
- **Kanban tasks** — always use the max plan mode derived from the global `PLANNING_MODE` (so if global is `auto_subtasks`, kanban gets `auto_subtasks`)
- **Task-level explicit override** (for cron jobs and kanban tasks)

If none of these explicitly enables it, the complexity-based classification caps at `auto_plan` — it will never spontaneously promote to `auto_subtasks`.

**Priority chain** (first non-empty wins):

1. **Cron task** `planning_mode` — highest priority, overrides channel and global
   - Valid values: empty (→ complexity-based default), `no_plan` (→ `prompt_only`), `simple_plan` (→ `auto_plan`), `plan_with_subtasks` (→ `auto_subtasks`), `max_plan` (→ `resolve_max_plan(global_mode)`), or direct canonical values
2. **Channel** `planning_mode` — override for the entire channel
   - Valid values: empty (→ default), `prompt_only`, `auto_plan`, `auto_subtasks`, `never` (→ `prompt_only`), `always` (→ `auto_subtasks`)
3. **Kanban tasks** — always `resolve_max_plan(global_mode)` (no complexity classification)
4. **User / Cron default** — `classify_complexity_for_planning()` via content heuristics (see below)

**Complexity classification (`classify_complexity_for_planning`):**

The classifier evaluates prompt content against threshold heuristics and returns a canonical planning mode. The outcome is **capped by the resolved planning mode context** — `auto_subtasks` is only returned when the global `PLANNING_MODE` or an explicit task/channel setting has enabled it.

| Complexity Level | Criteria | Resulting Mode |
|---|---|---|
| **Simple** | `char_len < SIMPLE_MAX (60)` or `word_count ≤ 3 + greeting` | `prompt_only` — no planning needed |
| **Standard** | Everything between Simple and Complex | `auto_plan` — single planning step |
| **Complex** | `char_len > STANDARD_MAX (200)` or action keywords match | `auto_subtasks` **iff** the resolved planning mode context permits it (global `PLANNING_MODE` is `auto_subtasks`, or an explicit task/channel/cron setting enables it); otherwise caps at `auto_plan` |

**Env vars:** `PLANNING_MODE`, `PLANNING_COMPLEXITY_SIMPLE_MAX_CHARS`, `PLANNING_COMPLEXITY_STANDARD_MAX_CHARS`, `PLANNING_COMPLEXITY_KEYWORDS` — all adjustable via `/settings` endpoint.

**Iteration caps** per mode (configured in `AgentConfig`):
- `prompt_only` → `max_iterations_no_plan` (default 5)
- `auto_plan` → `max_iterations_simple_plan` (default 10)
- `auto_subtasks`/`always` → `max_iterations_complex_plan` (default 25)

The per-`process_message` cap was previously hardcoded to 12 (`remaining.clamp(0, 12)`). It now uses the full remaining budget from the MAX_ITERATIONS_* settings directly (`remaining.max(0)`), so a single user message can consume all remaining iterations for the thread.

**When the iteration limit is reached**, the thread is marked `interrupted` (not `failed`). Instead of a hardcoded message, the executor calls the LLM to generate a summary that includes:
- The iteration count (`{current_iter}/{iter_limit}`)
- What was accomplished
- What remains to be done

The LLM summary is saved as the only post-loop message (type `summary`, subtype `interrupted`, `is_summary=true`).

## Cron Schedule Format

Cron expressions use **5-field Linux format** (`min hour day month weekday`). The scheduler prepends `"0 "` (second=0) for the `cron` crate (which expects 6-field). Both `create_cron_job` and `update_cron_job` MCP tools validate exactly 5 fields.

Examples:
- `0 * * * *` — every hour
- `*/15 * * * *` — every 15 minutes
- `0 9 * * 1-5` — weekdays at 9am
