# Blog Markdown Implementation — Stateful Guided Execution

## DO NOT EXPLORE — THIS IS THE CURRENT STATE

- **Blog project:** `/opt/workspace/blog/` (NOT `/opt/workspace/omni-workspace/blog/`)
- **Markdown support:** ✅ **ALREADY IMPLEMENTED** in the code. Do NOT add markdown libraries or modify `app.py`.
- **Blog container:** `blog-blog-1` runs OLD code — needs updated `app.py` deployed.
- **No git/curl in container:** Use host tools (git, fetch) instead.

## EXACT STEPS — MINIMAL EXPLORATION

Step 1: Read the task body carefully — it describes exact remaining work.

Step 2: Use host tools (git, fetch, filesystem) — NOT commands inside the container.

Step 3: Rebuild the blog container with updated app.py, then publish the research post.

## CORRECT COMPOSE PARAMETERS
- `project_dir` (string, REQUIRED) — directory with docker-compose.yml
- `command` (string, REQUIRED) — compose verb (build, up -d, ps, exec, ...)
- `service` (string, REQUIRED for exec) — container name
- `args` (string) — command string for exec. Auto-wrapped in sh -c — write naturally.
- `script` (string) — Python code piped to python3 stdin
- `timeout` (number) — override timeout in seconds

## DEAD ENDS TO AVOID
- Do NOT install packages in blog container — add to Dockerfile instead
- Do NOT explore /opt/workspace/blog/repo/ — that's a different project
- Do NOT explore the workspace — you have all info above
