# Blog Build: Create Flask Blog from Scratch

You MUST create a complete Flask blog application at **/opt/workspace/blog/** as a Docker containerized service.

## CRITICAL RULES: Read These First

**YOU CAN LIST THE BLOG DIRECTORY EXACTLY ONCE.** After that, you already know what's there. Do not list it again. If you need to verify a file you created, read just that file.

**DO NOT WASTE ITERATIONS:**
- You have seen the directory listing. Move on to writing files immediately.
- If a previous iteration of this turn already listed /opt/workspace/blog/, you already have that result. Use it.
- Every listing of the same directory is a wasted LLM call. Your iteration budget is finite.

**Tool order of operations:**
1. `filesystem_list("/opt/workspace/blog/")`: ONCE, at the very start
2. `filesystem_write(...)` for each file you need to create
3. `compose(project_dir="/opt/workspace/blog", command="build")`
4. `compose(project_dir="/opt/workspace/blog", command="up", args="-d")`
5. Verification (curl, docker ps)

If you catch yourself calling `filesystem_list` again after already having listed the directory, STOP and call `filesystem_write` instead.

## Requirements

1. **Flask + SQLite** backend (no framework other than Flask, no SQLAlchemy: use raw sqlite3)
2. **User registration/login** (bcrypt password hashing, flask session cookies)
   - POST /api/register: email + password (reject duplicate email with 409)
   - POST /api/login: email + password, returns session cookie
   - POST /api/logout: clears session
3. **Post creation** (auth required)
   - GET /api/posts: list all posts (public)
   - POST /api/posts: create post (auth required, body: title + content)
   - GET /api/posts/<id>: single post detail (public)
4. **Comments** (auth required to post, but readable by anyone)
   - GET /api/posts/<id>/comments: list comments for a post (public)
   - POST /api/posts/<id>/comments: add comment (auth required)
5. **Docker deployment**
   - Dockerfile (python:3.11-slim, install requirements, run with gunicorn)
   - docker-compose.yml with the app service on port 8090
   - SQLite database stored in a persistent volume at /data/blog.db
6. **The app must be at /opt/workspace/blog/**

## Execution Plan

### Phase 1: Clean up existing skeleton
If /opt/workspace/blog/ exists, remove the repo/ subdirectory (it's Rust/MongoDB: not needed). Keep docker-compose.yml and .env if they exist, but be ready to replace them.

### Phase 2: Create app files
Create these files: do them ALL in as few tool calls as you can:
- `/opt/workspace/blog/app.py`: Flask application (single file, ~200+ lines)
- `/opt/workspace/blog/requirements.txt`: Flask, gunicorn, bcrypt
- `/opt/workspace/blog/templates/base.html`: Base template with nav
- `/opt/workspace/blog/templates/index.html`: Post listing
- `/opt/workspace/blog/templates/login.html`
- `/opt/workspace/blog/templates/register.html`
- `/opt/workspace/blog/templates/post.html`: Single post with comments
- `/opt/workspace/blog/Dockerfile`
- `/opt/workspace/blog/docker-compose.yml`

### Phase 3: Build and deploy
```sh
docker compose -f /opt/workspace/blog/docker-compose.yml build
docker compose -f /opt/workspace/blog/docker-compose.yml up -d
```

### Phase 4: Verify
```sh
docker compose -f /opt/workspace/blog/docker-compose.yml ps
docker compose -f /opt/workspace/blog/docker-compose.yml logs --tail 30
curl -s http://localhost:8090/api/posts | head -5
curl -s -X POST http://localhost:8090/api/register -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"test123"}' | head -5
curl -s -X POST http://localhost:8090/api/login -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"test123"}' -c /tmp/cookies.txt | head -5
curl -s -X POST http://localhost:8090/api/posts -H "Content-Type: application/json" -b /tmp/cookies.txt -d '{"title":"Test Post","content":"Hello World"}' | head -5
curl -s http://localhost:8090/api/posts | head -10
```

## PROHIBITED TOOLS
Do NOT call any of these: they are not needed for this task:
- ❌ kanban:list_kanban_tasks, kanban:* (any kanban tool)
- ❌ cron:list_cron_jobs, cron:* (any cron tool)
- ❌ search_messages, search_wiki
- ❌ plugin_manager, manage_subtasks (this is a simple plan, NOT subtask mode)
- ❌ query_database (you already have all context needed)
- ❌ generate_image, transcribe_media, memory, hindsight tools

## REQUIRED TOOLS
Only call these:
- ✅ filesystem_write: Create all project files
- ✅ filesystem_read: Read existing files when you need to check content (not list dir)
- ✅ filesystem_list: List /opt/workspace/blog/ EXACTLY ONCE, never again
- ✅ `compose`: Build and start Docker services
- ✅ terminal: For curl testing

## SELF-CHECK
After every tool call, ask yourself: "Did I just list a directory I already listed? If yes, I should be writing files instead." If the answer is yes, switch to writing.

## OUTPUT
After completing all steps, provide a summary of what was built, whether all services are running, and API test results.
