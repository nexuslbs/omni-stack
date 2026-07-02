     1|# OmniAgent
     2|
     3|Next-generation agent system built with Rust, PostgreSQL + pgvector, and MCP tool support.
     4|
     5|## Features
     6|
     7|| **Hindsight Memory** | Persistent cross-session memory via omniagent-hindsight, with automatic population from new messages and semantic recall in context assembly |
     8|| **Hindsight Populator** | Background action (deactivated by default) that retains messages into hindsight every 15 minutes. Activate via `UPDATE cron_jobs SET active = true WHERE id = 'hindsight_populator'` |
     9|
    10|### 🧠 Context Builder & Grounding
    11|- **Priority-ranked prompt assembly** (`ContextBuilder`) — NeverTrim (system, MEMORY.md, subtasks) → High (thread messages) → Normal (tool defs) → Low (retrieved content)
    12|- **Token budgeting** — per-block character caps, lowest-priority blocks dropped when over budget
    13|- **Grounding policy** — embedded in every system prompt: prefer evidence, state uncertainty, cite references
    14|- **Evidence metadata** — `messages.metadata` captures context diagnostics (`context.selected_message_ids`, `block_counts`, `dropped_blocks`, `total_chars`) and grounding flags
    15|
    16|### 🔍 Hybrid Retrieval
    17|- **4-tier retrieval** controlled by profile `retrieval_aggressiveness` (0-3):
    18|  - Level 1: ILIKE text search in messages + wiki text search (walkdir)
    19|  - Level 2+: pgvector semantic search (`<=>` cosine similarity on message embeddings) + Qdrant vector search on wiki content
    20|- **Query classifier** — heuristic (Greeting/Command/FollowUp/Factual/ExternalQuery) gates whether retrieval runs
    21|- Re-ranking with recency and same-thread boosts
    22|
    23|### 💾 Memory Promotion
    24|- **3 MCP tools** (`promote_to_memory`, `list_memories`, `review_memories`)
    25|- YAML frontmatter with `confidence`, `source_message_ids`, `source_tool_outputs`, `created_at`, `expires_at`, `last_verified_at`
    26|- 30-day default expiry with review workflow
    27|
    28|### 🔄 Dynamic Enum Refresh (`refresh_url`)
    29|
    30|Provider plugins can define a `refresh_url` on `enum` type `config_schema` fields to dynamically fetch model options from an external API at runtime, rather than relying on a static `allowed_values` list.
    31|
    32|**How it works:**
    33|
    34|1. **Plugin definition** — a `ConfigSchemaField` with `type: "enum"` and a `refresh_url` pointing to an OpenAI-compatible `/v1/models` endpoint:
    35|   ```json
    36|   { "key": "default_model", "label": "Default Model", "type": "enum", "refresh_url": "https://api.deepseek.com/v1/models" }
    37|   ```
    38|
    39|2. **On-demand refresh** — `POST /api/plugins/{name}/refresh-models` fetches models from the URL, parses `{data: [{id: "model-name"}, ...]}` responses, and updates an in-memory cache.
    40|
    41|3. **In-memory cache** — `DYNAMIC_ENUM_CACHE` (Mutex\<HashMap\<String, DynamicEnumEntry\>\>) with a 5-minute TTL. Cache is checked when enriching plugin data for API responses (`enrich_plugin()`).
    42|
    43|4. **API key resolution** — for authenticated endpoints, the key is resolved as `{PLUGIN_NAME}_API_KEY` → `LLM_API_KEY` environment variable, sent as a `Bearer` token.
    44|
    45|5. **Graceful fallback** — if the fetch fails, existing `allowed_values` are preserved (either hardcoded fallbacks in `plugin.json` or the previous cache entry).
    46|
    47|**Currently used by:**
    48|- **deepseek** — `refresh_url: "https://api.deepseek.com/v1/models"` with static fallback `["deepseek-v4-flash", "deepseek-v3", "deepseek-r1"]`
    49|- **opencode-go** — `refresh_url: "https://opencode.ai/zen/go/v1/models"` (no static fallback)
    50|
    51|### 🔌 MCP External Servers
    52|- **stdio transport** — spawn subprocesses, JSON-RPC 2.0 over stdin/stdout
    53|- **HTTP transport** — connect to remote MCP servers via HTTP POST
    54|- **Circuit breaker** — automatic disable after N consecutive failures
    55|- **Dynamic tool registry** — external tools auto-merge with built-in tools at startup
    56|- Configured via `MCP_SERVERS_CONFIG` env var or `<data_dir>/config/mcp-servers.json`
    57|
    58|### 📋 Thread Subtasks
    59|
    60|Thread subtasks enable the LLM to decompose a complex request into trackable sub-items. Subtasks are stored in the `thread_subtasks` table and managed via the `manage_subtasks` MCP tool.
    61|
    62|**Tool: `manage_subtasks`**
    63|- Actions: `add`, `list`, `update`, `delete`, `get_counts`
    64|- Each subtask has: `id`, `thread_id`, `description`, `status` (pending/completed/cancelled), `priority`
    65|- Returns structured JSON with `current_subtask`, counts per status, and full subtask list
    66|
    67|**Current Subtask Logic:**
    68|- The first pending subtask (ordered by `priority DESC`, `created_at ASC`) is the "current" subtask
    69|- When all subtasks are completed/cancelled, `current_subtask` is `null`
    70|- This drives the prompt injection — only the current subtask is prominently displayed
    71|
    72|**Prompt Injection:**
    73|- When subtasks exist, a `[Thread Subtasks]` section is injected into the system prompt (NeverTrim tier)
    74|- Shows current subtask with status emoji, and remaining subtask count
    75|- Only injected when there are active (non-cancelled) subtasks — empty threads see no section
    76|
    77|**Override Pattern:**
    78|- To redefine a thread's subtasks, delete all existing ones (`action: delete` for each) then add new ones
    79|- Bulk updates supported via SQL-level operations (e.g., mark all as completed)
    80|
    81|### Requirements
    82|
    83|- Docker & Docker Compose
    84|- An LLM API key (OpenCode Go, OpenAI, Anthropic, or DeepSeek)
    85|
    86|### Setup
    87|
    88|1. Clone the repo:
    89|   ```bash
    90|   git clone https://github.com/nexuslbs/omniagent.git
    91|   cd omniagent
    92|   ```
    93|
    94|2. Copy the environment template and configure:
    95|   ```bash
    96|   cp .env.example .env
    97|   ```
    98|   Edit `.env` and set at minimum:
    99|   - `LLM_API_KEY` — your LLM provider API key
   100|   - `DATABASE_URL` — PostgreSQL connection string (default: `postgres://omniagent:***@postgres:5432/omniagent`)
   101|
   102|3. Start the stack:
   103|   ```bash
   104|   docker compose up -d
   105|   ```
   106|
   107|This starts:
   108|- **PostgreSQL 16 + pgvector** — message storage with vector embeddings
   109|- **Qdrant** — vector similarity search (optional, for semantic search)
   110|- **OmniAgent** — the agent itself, on port 8080
   111|
   112|### Verify
   113|
   114|```bash
   115|curl http://localhost:8080/health
   116|# → ok
   117|```
   118|
   119|## Channels
   120|
   121|Channels represent communication endpoints. Each channel has its own state, profile, and model configuration. The agent processes messages **sequentially within a channel** but **in parallel across channels**.
   122|
   123|### Channel Fields
   124|
   125|| Field | Description |
   126||-------|-------------|
   127|| `name` | Human-readable channel name |
   128|| `platform` | Platform identifier (e.g., `telegram`, `api`, `cron`) |
   129|| `external_id` | Platform-specific address (chat ID, channel name, etc.) |
   130|| `resource_identifier` | Canonical resource address — used in (platform, resource_identifier) unique constraint |
   131|| `current_profile` | Profile to use for message processing |
   132|| `current_provider` | Provider override (overrides profile) |
   133|| `current_model` | Model override (overrides profile) |
   134|| `closed` | Boolean (default `false`). A closed channel retains history but **won't process new messages** |
   135|| `readonly` | Boolean (default `false`). Protects the channel from deletion |
   136|
   137|### Creating a Channel
   138|
   139|```sql
   140|INSERT INTO channels (name, platform, external_id, resource_identifier, cause, current_profile)
   141|VALUES ('my-channel', 'api', 'my-channel-1', 'my-channel-1', 'user', 'default');
   142|```
   143|
   144|Each channel can set a custom profile, provider, and model:
   145|```sql
   146|UPDATE channels SET current_profile = 'research', current_provider = 'anthropic', current_model = 'claude-sonnet-4' WHERE id = 1;
   147|```
   148|
   149|### Cron Channel
   150|
   151|Every OmniAgent instance has a default cron channel (platform='cron', name='cron-default') created automatically. This channel is used as the fallback destination for cron jobs and kanban tasks that don't specify a channel. It is marked as `readonly=true` to prevent accidental deletion.
   152|
   153|### Readonly Channels
   154|
   155|Channels can be marked as `readonly` (e.g., the default cron channel) to protect them from deletion:
   156|```sql
   157|ALTER TABLE channels ADD COLUMN readonly BOOLEAN NOT NULL DEFAULT false;
   158|```
   159|
   160|### Closed Channels
   161|
   162|Channels can be marked as `closed` (boolean, default `false`). A closed channel:
   163|- Retains all message history
   164|- Does **not** process new messages (they remain pending)
   165|- Can be reopened by setting `closed = false`
   166|
   167|```sql
   168|ALTER TABLE channels ADD COLUMN closed BOOLEAN NOT NULL DEFAULT false;
   169|```
   170|
   171|### Channel Subscriptions
   172|
   173|The `channel_subscriptions` table enables cross-platform listening:
   174|
   175|| Field | Description |
   176||-------|-------------|
   177|| `channel_id` | The channel that receives updates |
   178|| `subscriber_platform` | Platform of the subscriber |
   179|| `subscriber_resource` | Resource identifier of the subscriber |
   180|
   181|A Telegram channel can subscribe to another channel's summaries — when a summary is generated, it's forwarded to the subscriber. The unique constraint is `(channel_id, subscriber_platform, subscriber_resource)`.
   182|
   183|```sql
   184|INSERT INTO channel_subscriptions (channel_id, subscriber_platform, subscriber_resource)
   185|VALUES (1, 'telegram', 'my-telegram-chat');
   186|```
   187|
   188|## Profiles
   189|
   190|Profiles bundle model configuration, provider, and allowed tools. A `default` profile is created on first startup.
   191|
   192|Profile fields:
   193|- **provider** — LLM provider (e.g., `opencode-go`, `openai`, `anthropic`, `deepseek`)
   194|- **model** — LLM model name (e.g., `deepseek-v4-flash`, `claude-sonnet-4`)
   195|- **allowed_tools** — which MCP tools the agent can use
   196|
   197|### Creating a Profile
   198|
   199|```sql
   200|INSERT INTO profiles (name, provider, model, allowed_tools)
   201|VALUES (
   202|  'research',
   203|  'anthropic',
   204|  'claude-sonnet-4',
   205|  '["filesystem_read", "filesystem_write", "fetch", "search_messages", "search_wiki"]'
   206|);
   207|```
   208|
   209|### Profile vs Channel Priority
   210|
   211|The effective model and provider are resolved as:
   212|1. **Message** `profile` (highest) — set per-message for cron/kanban tasks
   213|2. **Channel** `current_profile` / `current_model` / `current_provider`
   214|3. **Profile** `model` / `provider`
   215|4. Environment defaults
   216|5. Built-in fallbacks
   217|
   218|If neither the channel nor the profile specifies a model, the prompt will fail with an error.
   219|
   220|## Execution Model
   221|
   222|### Sequential Per Channel, Parallel Across Channels
   223|
   224|The agent runs a **supervisor loop** that:
   225|1. Lists all channels from the database
   226|2. Spawns a dedicated `channel_handler` task for each channel that isn't already running
   227|3. Each `channel_handler` independently polls its channel for pending messages
   228|4. Within a channel, messages are processed one at a time (FIFO order)
   229|5. Across channels, processing happens in parallel
   230|
   231|```
   232|┌─────────────────────────────────────────────────┐
   233|│  Supervisor Loop (every 5 sec)                   │
   234|│                                                   │
   235|│  ├── Channel A ── handler ── msg₁ ── msg₂ ── ... │
   236|│  ├── Channel B ── handler ── msg₁ ── msg₂ ── ... │
   237|│  ├── Channel C ── handler ── msg₁ ── msg₂ ── ... │
   238|│  └── cron/kanban ── handler ── msg₁ ── msg₂ ... │
   239|└─────────────────────────────────────────────────┘
   240|```
   241|
   242|### Message Lifecycle
   243|
   244|```
   245|User inserts a message (status = pending)
   246|  │
   247|  ▼
   248|Agent picks it up, marks as processing
   249|  │
   250|  ├─ LLM responds with text → saved as msg_type='message'
   251|  ├─ LLM includes reasoning → saved as msg_type='reasoning' (separate row)
   252|  ├─ LLM plans next step → saved as msg_type='plan'
   253|  ├─ LLM calls tools in parallel → saved as msg_type='multi-tool'
   254|  └─ LLM calls tools → tool executed, result fed back, loop continues
   255|  │
   256|  ▼
   257|Prompt marked as completed, processing_time_ms and token_usage set
   258|```
   259|
   260|### Message Types
   261|
   262|| `msg_type` | Description |
   263||------------|-------------|
   264|| `message` | Standard user or assistant message |
   265|| `cron` | Cron-triggered message |
   266|| `kanban` | Kanban-triggered message |
   267|| `tool` | Tool invocation |
   268|| `tool_result` | Tool execution result |
   269|| `reasoning` | LLM reasoning/thinking content |
   270|| `summary` | Thread summary |
   271|| `plan` | LLM planning or reasoning step |
   272|| `multi-tool` | Parallel tool calls from the LLM |
   273|| `error` | Processing error (see `msg_subtype` for error codes) |
   274|
   275|### Error Subtypes
   276|
   277|| `msg_subtype` | Description |
   278||---------------|-------------|
   279|| `no-profile` | Profile field is empty |
   280|| `no-provider` | Provider field is empty |
   281|| `no-model` | Model field is empty |
   282|| `invalid-profile` | Profile does not exist in the registry |
   283|
   284|### Per-Message Timing and Token Usage
   285|
   286|Each message stores its own timing and token data:
   287|
   288|- **`processing_time_ms`**: Wall-clock time spent processing this message (stored per-message, not thread-level)
   289|- **`token_usage`**: JSONB object with:
   290|  - `prompt_tokens` — tokens in the prompt
   291|  - `completion_tokens` — tokens in the completion
   292|  - `cached_tokens` — tokens served from cache (if supported by provider)
   293|  - `reasoning_tokens` — tokens used for reasoning/thinking (if supported)
   294|
   295|```json
   296|{
   297|  "prompt_tokens": 1523,
   298|  "completion_tokens": 412,
   299|  "cached_tokens": 0,
   300|  "reasoning_tokens": 89
   301|}
   302|```
   303|
   304|### Startup Cleanup
   305|
   306|On startup, the agent runs `skip_on_startup()` which marks all messages with status `pending` or `processing` as `skipped`. This prevents messages from being stuck indefinitely after a container restart.
   307|
   308|### Profile Resolution at Message Time
   309|
   310|When a message is created (seq-0), the `provider` and `model` fields are **stamped** on the message using this resolution chain:
   311|
   312|1. **Message** `profile` field (highest priority) — set per-message for cron/kanban tasks
   313|2. **Channel** `current_provider` / `current_model` / `current_profile`
   314|3. **Profile** `provider` / `model` (if set in the profile)
   315|4. **Environment variable** `LLM_PROVIDER` (model comes from provider plugin's `default_model`)
   316|5. **Built-in defaults** `opencode-go` / `deepseek-v4-flash`
   317|
   318|This happens at creation time for:
   319|- **User messages**: provider/model are stamped when the message is inserted
   320|- **Cron jobs**: provider/model are resolved and stamped by the cron scheduler
   321|- **Kanban tasks**: when a task is moved to 'ready' status, provider/model are resolved and stamped
   322|
   323|### Provider/Model Validation at Execution Time
   324|
   325|When the agent picks up a pending message for processing, it **validates** the stamped fields before calling the LLM:
   326|
   327|1. `profile` must be non-empty → fails with `msg_type='error'`, `msg_subtype='no-profile'`
   328|2. Profile must exist in the registry → fails with `msg_subtype='invalid-profile'`
   329|3. `provider` must be set and non-empty → fails with `msg_subtype='no-provider'`
   330|4. `model` must be set and non-empty → fails with `msg_subtype='no-model'`
   331|
   332|If validation fails, an error message is inserted into the thread and the original message is marked as `failed`. The agent uses **only** the stamped values — no fallback chain is run during execution.
   333|
   334|For **cron jobs**: profile comes from the cron job's `profile` field, or the channel's `current_profile` if NULL
   335|For **kanban tasks**: profile comes from the task's `profile` field, or the channel's `current_profile` if NULL
   336|For **user messages**: profile comes from the channel's `current_profile` at message creation time
   337|
   338|## Cron Jobs
   339|
   340|Cron jobs are scheduled tasks that execute on a recurring schedule. Each job can target a specific channel and profile.
   341|
   342|### Creating a Cron Job
   343|
   344|```sql
   345|-- Via MCP tool (recommended)
   346|-- Use the create_cron_job tool with optional channel_id and profile params
   347|
   348|-- Or directly in SQL:
   349|INSERT INTO cron_jobs (id, name, display_name, schedule, prompt, channel_id, profile)
   350|VALUES ('cron_abc123', 'hourly-report', 'Hourly Report', '0 * * * *', 'Generate the hourly report', 1, 'research');
   351|```
   352|
   353|### Fields
   354|
   355|| Field | Description |
   356||-------|-------------|
   357|| `channel_id` | Channel to fire in (NULL = default cron channel) |
   358|| `profile` | Profile to use (NULL = channel's current_profile) |
   359|| `schedule` | 5-field Linux cron expression (min hour day month weekday) — the scheduler internally prepends `0` (second=0) for the `cron` crate |
   360|| `prompt` | The message content to execute |
   361|| `mode` | Execution mode: `agentic` (default), `direct`, or `action` |
   362|| `direct_task_type` | Task type for `direct` mode (e.g., `kanban_dispatcher`) |
   363|| `action_id` | Action ID for `action` mode — references the `actions` table |
   364|| `enabled` | Whether the job is active |
   365|| `active` | Whether the job is currently claimed by a scheduler |
   366|
   367|### Execution Modes
   368|
   369|- **`agentic`** (default): Normal cron agent execution — the prompt is sent to the LLM for processing, with full tool access and reasoning. When `template` is set, the template content is injected as a "Task Template" block before the prompt.
   370|- **`action`**: Executes a registered action from the `actions` table (user-defined or built-in). The action's MCP tool is called with its saved parameters. No LLM call is made — the action runs as a direct Rust function or MCP tool invocation. Optional `silent` mode suppresses thread creation on success (only creates error threads).
   371|
   372|### Cron Planning Mode
   373|
   374|Cron jobs support the same planning modes as channels, selectable from the dashboard UI:
   375|
   376|| Value | Resolution | Use Case |
   377||-------|-----------|----------|
   378|| Empty (Default) | Complexity-based classification | Simple prompts don't waste tokens on planning |
   379|| `prompt_only` | No planning or subtasks | Scripted prompts that don't need decomposition |
   380|| `auto_plan` | Single planning step | Moderate prompts needing one planning pass |
   381|| `auto_subtasks` | Full subtask decomposition | Complex multi-step pipelines (e.g., Knowledge Pipeline) |
   382|
   383|Cron planning mode has **highest priority** in the resolution chain: cron job → channel → kanban → default.
   384|
   385|The planning mode is resolved at thread creation time via `resolve_thread_planning_mode_with_content()` and stamped on `threads.planning_mode`. For backward compatibility, the `max_plan` value is still accepted and resolves to the maximum plan mode enabled globally.
   386|
   387|### Knowledge Pipeline
   388|
   389|The Knowledge Pipeline is a periodic maintenance cron that runs 6 steps:
   390|
   391|1. **Per-channel summarization** — cross-thread summaries for channels with enough new completed threads
   392|2. **Wiki/skill update from messages** — groups completed threads by profile, extracts durable knowledge, updates wiki pages and skills
   393|3. **Wiki relevance indexing** — scores wiki files by recency and reference count, updates `relevant-index.md`
   394|4. **Skill relevance indexing** — same scoring for skill files, writes `relevant-skills-index.md`
   395|5. **Hindsight population** — batch-retains new messages into omniagent-hindsight (skipped if disabled)
   396|6. **Hindsight consolidation** — triggers the consolidation pipeline (skipped if disabled)
   397|
   398|**Setup:** Run the `Setup Knowledge Pipeline` action (built-in, idempotent). Creates a cron job with:
   399|- Schedule: `0 */6 * * *` (every 6 hours, configurable)
   400|- Mode: `agentic`
   401|- Planning mode: `max_plan` (enables subtask decomposition)
   402|- Instruction file: `knowledge-pipeline.md` (templates in `profiles/<name>/templates/`)
   403|
   404|The template is loaded from `<data_dir>/profiles/default/templates/knowledge-pipeline.md` and injected as a task template into the agent's prompt. Sub-task mode (`auto_subtasks`) ensures each step is tracked; errors on individual steps don't abort the entire pipeline (use the `error` subtask status).
   405|
   406|### Scheduler
   407|
   408|The cron scheduler runs as a background tokio task, polling every 30 seconds. When a job is due:
   409|1. The job is atomically claimed (with stale-lock detection after 10 minutes)
   410|2. The target channel is resolved (job's channel_id or default cron channel)
   411|3. The profile is resolved (job's profile or channel's current_profile)
   412|4. A pending seq-0 system message is inserted with `msg_type='cron'`
   413|5. The message's `profile` field is set to the resolved profile
   414|6. The job's timestamps are updated
   415|
   416|Concurrency is enforced at the DB level: `UPDATE ... WHERE NOT running` ensures only one scheduler instance fires each job.
   417|
   418|## Kanban Tasks
   419|
   420|Kanban tasks provide a structured workflow. Tasks can be assigned to channels and when moved to 'ready' status, they trigger execution.
   421|
   422|### Creating a Kanban Task
   423|
   424|```sql
   425|-- Via MCP tool (recommended)
   426|-- Use the create_kanban_task tool with optional channel_id and profile params
   427|
   428|-- Or directly in SQL:
   429|INSERT INTO kanban_tasks (id, title, body, status, channel_id, profile)
   430|VALUES ('task_abc123', 'Research topic', 'Find latest papers on...', 'todo', 1, 'research');
   431|```
   432|
   433|### Task Lifecycle
   434|
   435|1. Task is created (typically in `backlog` or `todo` status)
   436|2. Task is updated to `ready` status
   437|3. The system automatically creates a pending seq-0 message in the task's channel
   438|4. The agent picks up the message and processes it
   439|5. After completion, the task can be moved to `review` or `done`
   440|
   441|### Statuses
   442|
   443|| Status | Description |
   444||--------|-------------|
   445|| `backlog` | Not yet prioritized |
   446|| `todo` | Ready to be worked on |
   447|| `ready` | Triggers execution (creates a pending message) |
   448|| `running` | Currently being executed |
   449|| `review` | Waiting for review/approval |
   450|| `done` | Completed |
   451|| `blocked` | Blocked by something |
   452|
   453|### Kanban Dispatcher
   454|
   455|When a cron job is configured with `mode='direct'` and `direct_task_type='kanban_dispatcher'`, it acts as a **kanban dispatcher**. On each tick:
   456|
   457|1. Queries all kanban tasks with `status = 'todo'`
   458|2. Orders them by `priority` (ascending, lower = higher priority), then by `position`
   459|3. Moves the first eligible task to `ready` status
   460|4. The task's `body` becomes the prompt for execution
   461|5. The task's `profile` field (or channel's current_profile) is used for resolution
   462|
   463|This enables periodic task processing without human intervention — a cron job can drip-feed todo items into the agent's queue.
   464|
   465|### Channel and Profile Assignment
   466|
   467|Each kanban task can specify:
   468|- `channel_id`: Which channel to execute in (NULL = default cron channel)
   469|- `profile`: Which profile to use (NULL = channel's current_profile at execution time)
   470|
   471|When a task is updated to `ready` status, the system:
   472|1. Resolves the target channel (task's channel_id or default cron channel)
   473|2. Resolves the profile (task's profile or channel's current_profile)
   474|3. Creates a pending seq-0 message with `msg_type='kanban'` and `msg_subtype=<task_id>`
   475|4. The agent processes the message like any other pending message
   476|
   477|## Memory Management
   478|
   479|Memory files are loaded from the profile's memory directory and included in context assembly during the **NeverTrim** priority tier.
   480|
   481|### Location
   482|
   483|```
   484|$OMNI_DIR/profiles/<name>/memories/
   485|  MEMORY.md      # Core memory file
   486|  SOUL.md        # Identity/persona file
   487|```
   488|
   489|### Environment Variables
   490|
   491|| Variable | Default | Description |
   492||----------|---------|-------------|
   493|| `MEMORY_MAX_CHARS` | `5000` | Maximum characters in MEMORY.md |
   494|| `USER_MAX_CHARS` | `1000` | Maximum characters for user-specific memory |
   495|| `PLANNING_MODE` | `auto_plan` | Global planning mode: `prompt_only`, `auto_plan`, `auto_subtasks`, or `always` |
   496|| `PLANNING_COMPLEXITY_SIMPLE_MAX_CHARS` | `60` | Max chars for "simple" (greeting) classification |
   497|| `PLANNING_COMPLEXITY_STANDARD_MAX_CHARS` | `200` | Max chars for "standard" classification — above this triggers complex planning |
   498|| `PLANNING_COMPLEXITY_KEYWORDS` | (built-in list) | Comma-separated keywords that trigger complex planning |
   499|
   500|## Planning Mode
   501

## Mattermost Setup

OmniAgent can interact with [Mattermost](https://mattermost.com/) channels — receive user messages, send agent responses, and support message deletion for thread management.

### Prerequisites

You need a running Mattermost instance. The recommended setup uses a separate `docker-compose.mm.yml` (available in `scripts/` or the hermes-repo's `services/` directory).

### Mattermost Credentials (3 Accounts)

The system uses **3 Mattermost user accounts**, configured in your `.env` file:

| Env Variable | Purpose | Default Username |
|---|---|---|
| `MATTERMOST_ADMIN_USER` / `MATTERMOST_ADMIN_PASSWORD` | Admin account for system configuration | `admin` / `AdminPass123!` |
| `MATTERMOST_TEST_USER` / `MATTERMOST_TEST_PASSWORD` | Test user for development | `testuser` / `TestPass123!` |
| `MATTERMOST_BOT_USER` / `MATTERMOST_BOT_PASSWORD` | Bot account for agent messages | `omniagent` / `BotPass123!` |

The **bot account** is the one OmniAgent uses to send and receive messages via the Mattermost API.  
The **admin account** is used by the setup script to configure the system.  
The **test user** is a regular human user for testing.

### Initial Setup

Run the setup script to create all 3 users, register the bot, generate its access token, and create a default team/channel:

```bash
# From the omni-stack root directory
python3 scripts/mm-setup.py
```

This script:
1. Waits for Mattermost to become ready
2. Logs in as the admin user (creates one if the system is fresh)
3. **If the admin user already exists but the password in `.env` (`MM_USER_PASSWORD`) doesn't match**, the script auto-resets it using `mmctl --local user change-password` to match the configured value
4. Enables bot account creation and user access tokens
5. Creates the test user (if not exists)
6. Creates the bot user account (if not exists)
7. Registers the bot account and generates a personal access token
8. Saves the token to `MATTERMOST_ACCESS_TOKEN` in `.env`
9. Creates a `test-team` with a `test` channel
10. Adds all 3 users to the channel
#### Running on a Fresh Mattermost

On first run, Mattermost has no users. The setup script creates the first user (which becomes a system admin automatically). Run the script again if any steps fail on first attempt.

### platforms.yml Configuration

The Mattermost platform plugin is configured in `platforms.yml`:

```yaml
platforms:
  mattermost:
    enabled: true
    builtin: false
    config:
      connection_mode: websocket
      bot_username: $env:MATTERMOST_BOT_USER
```

The `bot_username` references the `MATTERMOST_BOT_USER` env var via the `$env:` prefix. This tells the plugin which Mattermost username to identify as (it filters out the bot's own messages from inbound processing).

Other Mattermost env vars used by the plugin (set in `.env`):

| Variable | Description |
|---|---|
| `MATTERMOST_SERVER_URL` | Internal URL (`http://mattermost:8065`) |
| `MATTERMOST_SITE_URL` | Public/external URL for the Mattermost instance |
| `MATTERMOST_ACCESS_TOKEN` | Bot's personal access token (generated by setup script) |
| `MATTERMOST_BOT_USERNAME` | Bot username (must match `MATTERMOST_BOT_USER`) |
| `MATTERMOST_CONNECTION_MODE` | `websocket` (real-time) or `polling` |

### Accessing Mattermost

Open your browser at the Mattermost URL (default: `http://localhost:8065`).

- **Admin**: Log in with `MATTERMOST_ADMIN_USER` / `MATTERMOST_ADMIN_PASSWORD`
- **Test user**: Log in with `MATTERMOST_TEST_USER` / `MATTERMOST_TEST_PASSWORD`

### Creating a Channel and Associating with OmniAgent

1. **In Mattermost UI** (logged in as admin):
   - Create a channel (e.g. `my-channel`)
   - Add the bot user (`omniagent`) and test user as members

2. **Find the channel ID**:
   ```bash
   curl -s -H "Authorization: Bearer $MATTERMOST_ACCESS_TOKEN" \
     $MATTERMOST_SERVER_URL/api/v4/channels \
     | python3 -c "import sys,json; [print(f'{c["name"]}: {c["id"]}') for c in json.load(sys.stdin)]"
   ```

3. **Create an OmniAgent channel** — insert into the channels table:
   ```sql
   INSERT INTO channels (name, platform, external_id, resource_identifier, cause, current_profile)
   VALUES ('my-mm-channel', 'mattermost', '<channel_id>', '<channel_id>', 'user', 'default');
   ```

### Testing Message Flow

1. **Send a message** from Mattermost to OmniAgent:
   - Log in as the test user
   - Post a message in the channel (e.g. "Hello!")
   - OmniAgent should pick it up and respond

2. **Delete a message to stop a thread**:
   - While the agent is processing a message, delete the user's message in Mattermost
   - OmniAgent detects the deletion and marks the thread as stopped (skipped)

3. **Stop all processing in a channel**:
   ```bash
   curl -X POST http://localhost:8080/stop/<channel_id>
   ```
   Where `<channel_id>` is the OmniAgent channel ID (integer, from the `channels` table).

4. **Resume processing**:
   ```bash
   curl http://localhost:8080/resume/<channel_id>
   ```

### Configuring Mattermost Channels via Dashboard

The OmniAgent Dashboard (available at `http://localhost:12346`) provides UI for:

- **Channel management**: View, create, and configure channels
- **Profile assignment**: Set which profile a Mattermost channel uses
- **Provider/model overrides**: Override the LLM provider per channel
- **Planning mode**: Set the planning behavior per channel
- **Channel status**: Close, reopen, or mark channels as readonly

The Dashboard also shows real-time message processing status per channel.

### Bot Account for Agent Messages

The bot account (`MATTERMOST_BOT_USER`) is used by the Mattermost platform plugin to:

- **Send messages**: Agent responses are delivered through the bot
- **Receive messages**: Inbound messages from users are polled or received via WebSocket
- **Filter self-messages**: Messages from the bot are ignored (prevents loops)
- **React**: The bot can add emoji reactions to messages

The personal access token (`MATTERMOST_ACCESS_TOKEN`) is generated by `scripts/mm-setup.py` and stored in `.env`. The mattermost plugin reads it from the environment and uses it for all API calls.

|