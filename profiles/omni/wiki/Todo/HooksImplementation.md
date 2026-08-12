# Hooks Implementation Plan

**Status:** Plan of action — NOT yet implemented
**Source design:** Task `task_18cb1c10324f7240` (kanban, omniagent-dev workflow) — this page is
the versioned summary of everything decided
**Date:** 2026-08-12
**Scope:** omniagent event-driven Hooks system — event sources, counters, scopes, execution
modes, infinite-loop protection, error isolation.

This page is the implementation blueprint for the Hooks feature. It captures every decision that
was made so implementation can proceed without re-deriving anything. The kanban task
(`task_18cb1c10324f7240`) is the executable copy; this page is the durable reference.

---

## 1. Goal

Implement a **Hooks** system in omniagent. Hooks work like cron schedule jobs (explicit profile,
channel, planning mode, execution mode), but instead of running periodically based on a time
schedule, they run **triggered by events** in the system.

---

## 2. Hook definition

A hook mirrors a cron job definition:

| Field | Meaning |
|---|---|
| `event_type` | Which event triggers this hook (`thread_started` \| `thread_finished` \| `new_message`) |
| `scope` | `global` \| `channel` \| `profile` — determines how the counter is selected and filtered |
| `target` | Scope-specific target (channel name / profile name, or `all`) |
| `counters` | JSON field storing per-scope counters (see §5) |
| `mode` | Execution mode: **agentic** (spawn agent thread) \| **action** (run predefined action from `actions.yml`) |
| `profile` | Explicit profile for the hook (overrides default) |
| `channel` | Explicit channel for the hook (overrides default) |
| `planning_mode` | `on` / `off` / None |
| `action` | (action mode only) the action key from `actions.yml` |

---

## 3. Event types (3 for now)

| Event | Fires when |
|---|---|
| `thread_started` | a thread is created |
| `thread_finished` | a thread goes to a terminal state |
| `new_message` | a new message is inserted in the `messages` table |

### 3.1 Infinite-loop protection

**Threads caused by a hook must not trigger events, and their messages must not trigger events.**

Implementation: hook-caused threads/messages carry a marker (e.g. a `hook_id`/`caused_by_hook`
flag on the thread row, propagated to messages) so the hook engine skips them when scanning
events. This prevents a hook → thread → message → hook → thread … infinite loop.

---

## 4. Scope semantics

### 4.1 `global`

- Triggers on **any** event of the chosen type (no filtering).
- Has a **single counter** (stored under the `global` key).

### 4.2 `channel`

- Can specify a **given channel (by name)** or **all channels**.
- Counter is **per channel** — a separate counter per channel the hook sees, whether the hook
  targets a single named channel or all channels.
- If the hook specifies a single channel (e.g. `channel2`), events from threads NOT in that
  channel are **ignored** by this hook.

### 4.3 `profile`

- Can specify a **given profile (by name)** or **all profiles**.
- Counter is **per profile** — a separate counter per profile, whether the hook targets a single
  named profile or all profiles.

---

## 5. Counter storage (JSON field)

The hook row stores counters in a JSON field, e.g.:

```json
{
  "global": 3,
  "channel": { "channel1": 5, "channel2": 1 },
  "profile": { "omni": 15, "another": 4 }
}
```

- The counter used is determined by the hook's **scope**.
- If scope is `channel`, only the fields inside the `channel` object are used; if the hook targets
  specific channel `channel2`, only `channel2`'s counter is incremented (events from threads not
  in `channel2` are ignored by this hook).
- **Default counter is 1** — with no JSON override, the hook triggers on every matching event.
- When the counter reaches the specified amount → trigger the hook and **reset that specific
  counter** (e.g. set `channel.channel2` back to 0, leaving the other counters untouched).

---

## 6. Execution modes

### 6.1 Agentic mode

Spawn an agent thread (like a cron agentic job) with the hook's explicit profile / channel /
planning mode.

### 6.2 Action mode

Run a predefined action defined in `actions.yml` (non-agentic, like cron direct-action mode),
selected by the hook's `action` key.

---

## 7. Reliability requirement

**Hook errors must not affect the main agent loop.** A failing hook (agent spawn failure, action
failure, DB error, etc.) must be isolated — logged, never propagated to the main thread/message
processing loop.

---

## 8. Acceptance criteria

1. DB schema for hooks (table + JSON counter field) with migration.
2. Hook engine wired into the 3 event points: thread creation, thread terminal-state transition,
   message insert.
3. Infinite-loop protection: hook-caused threads/messages are excluded from triggering events.
4. Scope resolution (global / channel by name or all / profile by name or all) with correct
   per-scope counter isolation.
5. Counter increment → trigger → reset semantics, default 1.
6. Both execution modes: agentic thread spawn AND actions.yml predefined action.
7. Explicit profile / channel / planning mode honored per hook.
8. Hook failures isolated — main agent loop unaffected.
9. Tests covering: counter increment/reset, scope filtering, infinite-loop exclusion, both
   execution modes, error isolation.
