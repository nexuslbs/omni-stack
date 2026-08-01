# Git Tool Usage

Use this skill when working with git repositories through the MCP git tools. The git tools operate on repositories that have been cloned via `git_clone-repo`; you cannot run arbitrary shell commands, so all git operations go through these tools.

## Available Tools

| Tool | Purpose |
|------|---------|
| `git_status` | Show the current working-tree state of the repository (branch, modified/untracked files, ahead/behind info). Use this FIRST to understand where the repo stands. |
| `git_clone-repo` | Clone a repository. Provide the repo URL and a target path. Repos live under `/opt/workspace/<project>/`. |
| `git_commit-and-push` | Stage all changes (`git add -A`), commit with a message, and push to the remote `origin`. Pushes the current branch head to `HEAD:<branch>` using the configured credentials. |
| `git_create-github-repo` | Create a new GitHub repository (requires GitHub App credentials). |
| `git_run-command` | Run ANY git command: `args` is an array like `["log", "--oneline", "-10"]`, `["diff"]`, `["branch", "-a"]`, `["remote", "-v"]`, `["fetch", "origin"]`, `["reset", "--soft", "HEAD~1"]`, `["stash"]`. Use this when the focused tools above aren't specific enough (pull, diff, log, tag, rebase, etc.). Pass `"use_auth": true` for authenticated fetch/push/pull against the https origin. |

## Workflow

1. **Inspect first** — always run `git_status` before editing to see the branch and working tree.
2. **Clone if needed** — if the repo isn't present locally, `git_clone-repo` with the URL and path.
3. **Edit files** — use `filesystem_read` / `filesystem_write` to make changes (there is no git add/edit tool; changes are picked up by commit-and-push).
4. **Commit + push** — call `git_commit-and-push` with a descriptive message. It stages everything, commits, and pushes. If there is nothing new to commit it still attempts to push pending commits.
5. **Verify** — call `git_status` again to confirm the tree is clean and the branch is up to date.

## Pitfalls

- **Sandbox**: all git tools only operate inside the configured `workspace_dir` (default `/opt/workspace`) and its subdirectories. Repos outside that path are rejected — clone there first if you need to work on something elsewhere.
- `git_commit-and-push` stages ALL changes by default (including deletions and untracked files). To commit ONLY specific files, pass them via the `files` parameter — never rely on the blanket stage when the tree contains scratch files.
- `git_run-command` args must be an ARRAY (e.g. `["log", "--oneline"]`), never a shell string — no shell injection is possible. Use `use_auth: true` only when the command needs GitHub credentials (fetch/push/pull); read-only commands (log, diff, status, branch) don't need it.
- Never commit secrets, `.env` files, or build artifacts. Use `.gitignore` entries for those.
- Never commit scratch helper files (toolbox/ dirs, patch scripts). Delete them or keep them outside the repo before committing.
- Commit messages should explain what and why, not just "update".
- If a push fails because the remote has new commits, use `git_run-command` with `["fetch", "origin"]` (plus `"use_auth": true`) to inspect, then rebase/reset as appropriate.
