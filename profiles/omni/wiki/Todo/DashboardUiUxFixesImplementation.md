# Dashboard UI/UX Fixes (8-item pass) — omni-dashboard

**Status:** IMPLEMENTED + TESTED (GROUP 49 regression) — review rework pending
**Task:** `task_18cd65247cfc4d9e` (board: omnidev, mm-kanban)
**Date:** 2026-08-20 (implementation landed in prior threads; window 1742-1744 verified it)
**Repo:** `omni-dashboard` (+ `omni-deployer` for the regression group)
**Related:** [Models-Yml](../Reference/Models-Yml.md) · [YamlApiFieldParityImplementation](./YamlApiFieldParityImplementation.md) (the 305199d refactor this pass built on)

## The 8 UI/UX items

1. **DB page 502** — server route used the old MCP tool name
2. **Custom selects in board/workflow/hook modals** — native `<select>`s styled/behaved like the rest of the dashboard
3. **Workflow option order + defaults** — `review_on_fail` first, defaults applied on create
4. **Hook trigger type** — hook trigger count input was `type="tel"` (weird spinner); made consistent
5. **Template selects** — alphabetical, all-profiles, custom select resolves from profile
6. **Red Cancel buttons** — opaque red (`var(--bg-card)`), not transparent
7. **Plugin Remove action** — Remove always visible
8. **Git box placement** — explorer git box moved to bottom

## Implementation commits (omni-dashboard, all on origin/main)

| Commit | Change |
|---|---|
| `fb9c680` | `fix(db): use search_database MCP tool name (was query_database) to fix DB page 502` — `server/routes/db.ts` now calls `search_database {sql}` (was `query_database {operation, sql}`) |
| `d56d046` | `fix(workflows): option text/order/defaults (3a-3e) — review_on_fail first, defaults on create` |
| `b0e2bc6` | `fix(kanban): board modal fields use custom selects (channel/profile/workflow/plan/template/priority) with empty options` |
| `73fdf62` | `fix(hooks): trigger count tel, template custom select resolves from profile (4a-4d)` — `src/lib/hooks-detail.ts` |
| `8e85376` | `fix(ui): template selects alphabetical all-profiles, red opaque cancel, plugin Remove always, explorer git box to bottom` — touches `src/lib/plugin-import.ts`, `src/lib/plugin-ui.ts`, `src/pages/explorer.ts` |
| `295a669` | `fix(ui): complete 8-item UI/UX pass` (the umbrella commit; accidentally included scratch push scripts) |
| `731f909` | `chore(hygiene): gitignore + remove scratch push scripts accidentally committed in 295a669` |
| `877a9e7` | `chore(hygiene): remove leftover .task-push.sh scratch script` |

Custom-select helpers: `enhanceSelect` / `enhanceSelectElement` live in
`src/lib/dropdown.ts`; consumers include `src/pages/kanban.ts`
(`wireBoardControls`), `src/lib/kanban-boards.ts`, `src/lib/hooks-detail.ts`.

## Testing (omni-deployer GROUP 49)

- `7e49bb8` `test(dashboard): GROUP 49 — omni-dashboard UI/UX fixes regression tests`
- GROUP 49 is a **static source-check** group (reads the TSX files from disk and
  asserts on select wiring, option ordering, modal opacity
  `background:var(--bg-card,#1e1e2e)`, etc.) — no live browser needed.

## Workflow history (window 1732-1744, mm-kanban)

- **Executor thread 1742**: found the 8-item pass was ALREADY fully implemented
  and pushed to origin/main by prior threads; re-ran `npm ci && npm run build &&
  npm run lint` and the test suite in a node:22-alpine toolbox
  (`/opt/workspace/.dash-build-compose.yml`, project `dash-build`); clean tree,
  build/lint pass; pre-existing `OmniDashboard API` subtest fails without a live
  server (not a regression).
- **Tester thread 1743**: added GROUP 49 (commit `7e49bb8`) and ran it PASS.
- **Reviewer thread 1744**: verified origin/main @ `877a9e7`, clean trees in both
  repos; findings recorded GOOD for the DB 502 + workflows items; ended the
  thread FAILED with `workflow_step: running` — task flipped review → running
  for executor rework (the rework outcome lives in threads ≥ 1745, OUTSIDE this
  maintenance window; not tracked here).

## Hygiene lesson (recurring)

Dashboards tasks keep accidentally committing scratch push scripts (`.task-push.sh`,
`.tmp_patch_*.py`): `.gitignore` now covers them, but reviewers should grep for
`ghp_|x-access-token|PRIVATE KEY|sk-...` and leftover `*.sh` before approving.
