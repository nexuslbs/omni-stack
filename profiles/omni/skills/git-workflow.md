# Git Tool Usage

Use this skill when working with git repositories through the MCP git tools. The git tools operate on repositories that have been cloned via `git_clone-repo`; you cannot run arbitrary shell commands, so all git operations go through these tools.

## Available Tools

| Tool | Purpose |
|------|---------|
| `git_status` | Show the current working-tree state of the repository (branch, modified/untracked files, ahead/behind info). Use this FIRST to understand where the repo stands. |
| `git_clone-repo` | Clone a repository. Provide the repo URL and a target path. Repos live under `/opt/workspace/<project>/`. |
| `git_commit-and-push` | Stage all changes (`git add -A`), commit with a message, and push to the remote `origin`. Pushes the current branch head to `HEAD:<branch>` using the configured credentials. |
| `git_create-github-repo` | Create a new GitHub repository (requires GitHub App credentials). |

## Workflow

1. **Inspect first** — always run `git_status` before editing to see the branch and working tree.
2. **Clone if needed** — if the repo isn't present locally, `git_clone-repo` with the URL and path.
3. **Edit files** — use `filesystem_read` / `filesystem_write` to make changes (there is no git add/edit tool; changes are picked up by commit-and-push).
4. **Commit + push** — call `git_commit-and-push` with a descriptive message. It stages everything, commits, and pushes. If there is nothing new to commit it still attempts to push pending commits.
5. **Verify** — call `git_status` again to confirm the tree is clean and the branch is up to date.

## Pitfalls

- There is **no `git pull` tool** — `git_clone-repo` is the way to get a fresh copy. If the repo already exists locally, `git_commit-and-push` will push local commits; conflicts with remote changes surface as push errors.
- There is **no `git diff` tool** — to review changes, use `filesystem_read` on the files you modified.
- `git_commit-and-push` stages ALL changes (including deletions and untracked files). Be intentional about what you edit in the workspace.
- Never commit secrets, `.env` files, or build artifacts. Use `.gitignore` entries for those.
- Commit messages should explain what and why, not just "update".
