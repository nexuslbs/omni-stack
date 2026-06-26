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
- ✅ docker_compose — USE THIS
- ✅ filesystem_write — USE TO FIX BUILD ERRORS
- ✅ filesystem_read — USE TO READ FILES

## Report
After all steps, output a summary of what was built, whether services are running, and any errors.
