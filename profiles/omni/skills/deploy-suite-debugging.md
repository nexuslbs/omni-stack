# Deploy Suite Debugging

Use this skill when running or debugging `deploy.py dev` (or `hybrid`) in
omni-deployer, when integration tests fail, or when a task requires verifying
that the full deploy suite runs green. It encodes hard-won lessons from the
Aug 15–16 2026 actions-plugin saga (8+ hours of executor loops) so the same
mistakes are not repeated.

## Rule 1: "Tool not found" is usually an ORDERING bug, not a harness bug

When a test fails because a tool "isn't registered" / "doesn't exist" (e.g.
`actions_*` tools missing at test time), the natural reaction is to blame the
test harness. That reaction is what burned 8 hours in the actions-plugin saga.

**Check registration ordering BEFORE touching the harness:**

1. What registers the tool? (plugin install, install-git, plugin enable,
   manifest scan, startup)
2. WHEN does that registration happen relative to the failing test? The classic
   trap: registration happens BEFORE `install-git`, so after the plugin is
   installed the tools are NOT yet available — tests fail with "tool not
   found" even though the plugin is correctly installed.
3. Verify the live state directly: query the plugin registry / tools API and
   confirm whether the tool is actually present at the moment the test runs.
4. Only after the ordering/registration story is fully mapped, look at the
   test harness.

**The indirect-failure trap:** a missing tool produces "tool not found", which
reads like a harness problem. There is no error message pointing at the real
cause (registration order). When you see "tool not found", your first question
must be: *what has to happen before this tool exists, and did it happen?*

## Rule 2: Test incrementally — subsets first, FULL deploy only when subsets pass

A full `deploy.py dev` run takes 30+ minutes (2 passes × 41+ groups + shared
tool tests + image rebuilds). Running the full suite to debug a single group
wastes hours per cycle. Instead:

1. **Run the failing group alone first.** Most groups are addressable
   individually (e.g. `python3 scripts/tests.py --group 37` — check the exact
   flag in omni-deployer `scripts/tests.py`).
2. **Verify the fix against that group** until it passes in isolation.
3. **Then run the next related groups** (e.g. 37 → 40 → 41) to catch
   cross-group interference.
4. **Only when the targeted groups pass, run the FULL deploy** to confirm the
   whole chain is green.

**Isolation contract:** every test must be self-contained — everything a test
needs (channels, plugins, config, fixtures) must be defined *within* that test
or its group setup, NOT created by a previous test running earlier in the
suite. If a test depends on another test having run first, running it in
isolation will fail and the failure will mislead you. When you find such a
dependency, fix the test to be self-contained (that is a real bug, not a
convenience).

## Rule 3: Reuse prior execution context — never re-derive from scratch

The agent has durable working memory (Smartness WS-1..6, landed in omniagent —
see `profiles/omni/wiki/Todo/OmniAgent-Smartness-Plan.md` and the
`memory-context-recovery` skill). Before starting (or restarting) a task:

1. **Check for a previous execution of the same task**: same task_id →
   prior threads. Use `search_thread-messages` / `search_messages` /
   `search_database` to find what was already tried, what failed, and what
   conclusions were reached.
2. **Read the thread's durable notes**: `{omni_dir}/data/threads/<id>/notes.md`
   (the agent's own durable memory) and `context-<iter>.json` dumps — they
   exist precisely so you don't re-read the same files or re-run the same
   experiments.
3. **Do not repeat a failed loop.** If a prior thread spent 30 iterations
   trying approach X, do not try X again — read what it learned and start from
   the next hypothesis.
4. **Write your own notes as you go** (`note_append`) — the thread budget
   prunes tool results; notes survive.

The 16 iteration-cap resets + 6 compactions in the saga were mostly
re-orientation: the executor kept losing state and re-reading logs to figure
out which failure it was chasing. Durable notes + prior-thread lookup are the
structural fix for that.

## Pitfalls

- Do NOT edit/weaken tests to make the suite pass — fixes must be
  sync/schema-alignment/ordering fixes; assertions stay meaningful.
- A deploy run that dies mid-tests leaves known residue in omni-stack
  (`.taskj-channels.patch`, `actions.yml`, `remote.yml`, `settings.yml`,
  wiki files) — Step 0.5 auto-restores it, do not hand-edit live config.
- deploy.py dev must stop omnidev but NEVER omnistable (the agent's own stack).
- Never inline secrets in test scripts or commands — keys go via env vars or
  DB-internal reads.
- `docker_compose exec` args get wrapped in `bash -c`; python scripts with
  single quotes must be passed via the `script` param (stdin), not args.
