# Blog Build — Direct Instructions

You MUST execute these exact steps in order. Do NOT add extra steps. Do NOT explore. Do NOT search. Do NOT list directories more than once.

## Step 1: Read the blog files
```
filesystem_read(path="/opt/workspace/blog/docker-compose.yml")
filesystem_read(path="/opt/workspace/blog/repo/backend/Cargo.toml")
filesystem_read(path="/opt/workspace/blog/repo/frontend/package.json")
```

## Step 2: Build the Docker images
```
docker_compose(project_dir="/opt/workspace/blog", command="build")
```
If build fails, fix the reported error in the source files, then rebuild.

## Step 3: Start services
```
docker_compose(project_dir="/opt/workspace/blog", command="up", args="-d")
```

## Step 4: Check the logs
```
docker_compose(project_dir="/opt/workspace/blog", command="logs", args="-n 50")
```

## Step 5: Verify the API works
```
docker_compose(project_dir="/opt/workspace/blog", command="exec", service="app", args="curl -s http://localhost:8080/api/posts || wget -qO- http://localhost:8080/api/posts || echo 'check logs for api port'")
```

## CRITICAL: Do NOT call these tools unless an error requires fixing files
- ❌ kanban:list_kanban_tasks — skip entirely
- ❌ search_messages — skip entirely  
- ❌ filesystem_list on /app — skip entirely
- ❌ list_cron_jobs — skip entirely
- ❌ all cron tools (create, delete, update, list) — skip entirely
- ✅ docker_compose — USE THIS
- ✅ filesystem_write — USE TO FIX BUILD ERRORS
- ✅ filesystem_read — USE TO READ FILES

## PROHIBITED TOOLS FOR THIS TASK
Do NOT call these tools — they waste iterations and are not needed for building:
- list_kanban_tasks, create_kanban_task, update_kanban_task, delete_kanban_task
- add_kanban_dependency, remove_kanban_dependency
- list_cron_jobs, create_cron_job, delete_cron_job, update_cron_job
- plugin_manager
- search_messages, search_wiki (the context provided is sufficient)

## REQUIRED TOOLS FOR THIS TASK
Only these tools are needed:
- filesystem_read — Read project files (docker-compose.yml, Cargo.toml, package.json)
- filesystem_write — Write/update project files when build errors need fixing
- docker_compose — Build, start, exec, and manage Docker services (build, up -d, exec, logs, ps, down)

## Report
After all steps, output a summary of what was built, whether services are running, and any errors.
