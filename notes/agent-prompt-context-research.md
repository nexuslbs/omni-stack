# Agent Prompt & Context Research — Fixing Tool-Choice Drift

## Problem Statement

When a kanban task is dispatched (e.g. "Build a blog project"), OmniAgent keeps calling `list_kanban_tasks`, `list_cron_jobs`, and `filesystem_list` instead of executing the actual task with `compose` and `filesystem_write`. This wastes iterations (25+ in one case) and frustrates the user.

## Root Cause Analysis

The execution prompt for a kanban task is assembled as (in order):

```
ChatMessage::system(system_prompt)           # identity + tool rules + DB schema
ChatMessage::system(subtask_section)          # active subtasks (if any)
ChatMessage::system(template_section)         # task template (build-blog.md or workspace-development.md)
ChatMessage::system("=== Additional Context ===" + context_messages)  # recent thread msgs + summary + skills + retrieval
ChatMessage::system("=== Generated Plan ===" + plan)  # plan (if planning phase ran)
ChatMessage::user(cause_msg.content)          # "Execute kanban task: Build a blog..."
+ ALL tools (kanban, cron, compose, filesystem, etc.)
```

**Key issues working together:**

| Factor | Impact |
|--------|--------|
| **All tools always available** | kanban/cron tools listed alongside build tools — model sees them as valid info-gathering tools |
| **Context pulls irrelevant past messages** | Recent thread messages, channel summary, retrieved content — all irrelevant for a fresh autonomous task but present in the prompt, priming kanban/cron associations |
| **Template is just another system message** | No structural distinction from other context — gets blended into the noise |
| **No per-task tool restrictions** | A "build blog" task has the same toolset as a "check cron jobs" task |
| **Model-specific behavior** | deepseek-v4-flash may have higher affinity for "information retrieval" patterns (kanban/cron) vs "execution" patterns (compose) |
| **Tool definition descriptions** | `list_kanban_tasks` description makes it sound like useful context gathering |

---

## Alternative Approaches

### Approach A: Per-Task Tool Filtering (Restricted Toolset)

Add `allowed_tools` to template metadata. When a kanban task uses template X, only tools that X needs are exposed.

**Implementation:**
```yaml
# In template frontmatter or template content header
allowed_tools:
  - filesystem_write
  - filesystem_read  
  - compose
blocked_tools:
  - list_kanban_tasks
  - list_cron_jobs
```

The executor reads template metadata and filters `prof.allowed_tools` before sending to the LLM. If the template blocks kanban/cron, those tools are simply not in the tool definitions sent to the model.

**Pros:** Hard constraint — model physically cannot call blocked tools. No prompt engineering can override this.
**Cons:** Requires template metadata format. Could break if a complex task legitimately needs kanban. Need a migration for existing templates.

---

### Approach B: Dynamic Profile/Template Tool Binding

Each template can optionally specify a "profile" or "tool preset" that defines which tools to enable. When a kanban task is created with template X, the thread stores `tool_preset: "build"` as metadata. The executor resolves this to a tool subset.

**Implementation:**
```rust
enum ToolPreset {
    Default,   // all tools
    Build,     // filesystem + compose only
    Research,  // search + fetch + query_database only
    Admin,     // kanban + cron only
}
```

**Pros:** Clean separation of concerns. The tool profile is a first-class concept.
**Cons:** More moving parts. Tool preset resolution adds complexity to the profile model.

---

### Approach C: Two-Phase Context Assembly

Split the context builder into two independent streams:

1. **Task context** — for autonomous tasks (kanban dispatcher, cron jobs). Contains: template instructions, skills directly matching the task, NO conversation history, NO channel summaries, NO retrieved past messages.

2. **Conversation context** — for chat/thread interactions. Contains: recent messages, summaries, retrieval.

Kanban tasks with a template get **only** task context. Implement as a `context_mode: "task" | "conversation"` flag set based on `msg_type == "kanban"` and whether a template is present.

**Implementation:**
```rust
// In executor.rs, after computing context_messages:
if template_section.is_some() && msg_type == "kanban" {
    // Use TASK context mode — no conversation cruft
    context_messages = build_task_context(...).await;
    // task context = template + skills only
} else {
    context_messages = build_conversation_context(...).await;
    // conversation context = recent msgs + summary + retrieval + skills
}
```

**Pros:** Radically reduces prompt noise for autonomous tasks. Templates become the dominant signal.
**Cons:** Two context paths to maintain. Risk of missing relevant context if task genuinely needs past data.

---

### Approach D: Prompt Position Shuffle — Template Before Everything

Move the template from position 3 (after system prompt & subtasks) to position 1 (right after the system prompt, before ALL context). Make it the first "instruction" the model sees after the system identity.

**Implementation:**
```rust
let mut messages = vec![
    ChatMessage::system(&system_prompt),
];
// Template and subtasks BEFORE any context
if let Some(ref template_section) = template_section {
    messages.push(ChatMessage::system(template_section));
}
if let Some(ref subtask_section) = subtask_section {
    messages.push(ChatMessage::system(subtask_section));
}
// THEN context (recent messages, summary, skills, etc.)
if !context_messages.is_empty() {
    messages.push(ChatMessage::system(/* context */));
}
// Plan and user message last
```

**Pros:** Trivial change. Template instructions are the highest-priority "instruction" block after the system prompt.
**Cons:** Subtle — models may still be swayed by the volume of context that follows.

---

### Approach E: Instruction-Only Planning Phase (No Context)

When a template exists, the planning phase should not receive the full context (recent messages, summaries, etc.). It only needs: system prompt + template + task content.

**Implementation:**
```rust
if template_section.is_some() {
    planning_messages = vec![
        ChatMessage::system(&planning_prompt),
        ChatMessage::system(template_section),
        ChatMessage::user(&cause_msg.content),
    ];
}
```

**Pros:** The plan focuses purely on the template's instructions.
**Cons:** Plan may miss subtle details that context would provide.

---

### Approach F: Subtask Pre-Decomposition with Hard Steps

When a template like `build-blog.md` defines explicit steps, parse them into subtasks at creation time. Each subtask step contains the exact tool call to make. The agent's system prompt says "Your subtasks define exactly what to do. Follow them literally."

**Implementation:**
```rust
// In template format, support typed steps:
## Step 1: Build images
tool: compose
params: { project_dir: "/opt/workspace/blog", command: "build" }

## Step 2: Start services
tool: compose
params: { project_dir: "/opt/workspace/blog", command: "up", args: "-d" }
```

Each subtask in the database stores the tool name and params. The executor can auto-execute subtasks that are "tool steps" without LLM involvement.

**Pros:** Eliminates LLM tool-choice entirely for explicit steps. Works like a deterministic script.
**Cons:** Template format becomes more complex. Not flexible for tasks that require LLM reasoning.

---

### Approach G: Explicit Negative Prompting — "Don't Use These Tools"

Add a dedicated "PROHIBITED TOOLS" section to the system prompt template block that lists tools the model should not call for this task.

**Implementation:**
```
## PROHIBITED TOOLS FOR THIS TASK
Do NOT call these tools — they will waste iterations:
- list_kanban_tasks
- list_cron_jobs
- create_kanban_task
- create_cron_job
- update_kanban_task
- update_cron_job
- delete_kanban_task
- delete_cron_job
- add_kanban_dependency
- remove_kanban_dependency
- plugin_manager

## REQUIRED TOOLS FOR THIS TASK
Use these tools:
- filesystem_read: Read project files
- filesystem_write: Write/update project files
- compose: Build, start, exec, and manage Docker services
```

**Pros:** Direct. No code changes needed — works with existing template format.
**Cons:** Models can still call prohibited tools despite instructions. Prompt injection / "ignore previous instructions" risk. Increases prompt size.

---

### Approach H: Tool Name Priority in the Registry

Change how tools are ordered in `to_openai_tools()`. Put "execution" tools first (filesystem, compose) and "management" tools last (kanban, cron). Some models show position bias — they try the first tools listed.

**Implementation:**
```rust
// Sort tools: execution first, management last
fn sort_tools(tools: Vec<McpToolEntry>) -> Vec<McpToolEntry> {
    let priority = |name: &str| -> u8 {
        match name {
            n if n.starts_with("filesystem") => 0,
            n if n.starts_with("docker") => 1,
            n if n.starts_with("query_") => 2,
            n if n.starts_with("kanban") | n.starts_with("cron") => 10,
            _ => 5,
        }
    };
    // ... sort
}
```

**Pros:** Zero semantic change. Leverages position bias in favor of execution tools.
**Cons:** Weak signal — models that don't have position bias won't be affected.

---

### Approach I: `enabled_toolsets` in Cron/Task Configuration

Similar to what's already available in the Hermes cronjob tool's `enabled_toolsets` parameter. Extend the thread/kanban task model to support `enabled_toolsets`, which restricts which tool groups are exposed during execution.

**Implementation:**
```yaml
# Task metadata or template frontmatter
enabled_toolsets: ["terminal", "file"]
```

The MCP registry's `to_openai_tools` filters by toolset. Toolsets map to tool name patterns:
- `build` → filesystem_*, compose
- `manage` → kanban_*, cron_*
- `data` → query_database, search_*

**Pros:** Concept already proven in Hermes cron. Hard guarantee.
**Cons:** Needs tool-to-toolset mapping. Toolset concept doesn't exist in omniagent yet.

---

### Approach J: Task-Template-Locked Execution Mode

When a task has a template, switch to **locked execution mode**:
1. The template content is the PRIMARY instruction source
2. All context blocks except skills are dropped
3. The plan phase receives only template + task content
4. A post-system-prompt "Constraints" block lists allowed/blocked tools
5. The user message is prepended with the template content (not just appended)

**Implementation:**
```rust
if template_section.is_some() && msg_type == "kanban" {
    // Locked execution mode
    // 1. Drop conversation context
    context_messages = String::new();
    // 2. Modify user message to include template
    cause_msg.content = format!("{}\n\n## Task\n{}", template_section, cause_msg.content);
    // 3. Add tool constraints block
    constraints = "ALLOWED: filesystem_read, filesystem_write, compose\nBLOCKED: all other tools";
    messages.push(ChatMessage::system(constraints));
}
```

**Pros:** Comprehensive approach addressing multiple root causes simultaneously.
**Cons:** Most invasive change. More testing needed.

---

## Recommended Testing Methodology

For each approach, test in isolation:

1. **Create a test kanban task** with `template: "build-blog"` and body matching the blog build description
2. **Run the dispatcher** and capture the agent's first 5 tool calls
3. **Verify:** No kanban/cron tools called, direct progression through build steps
4. **Score:** # iterations until successful completion, # unnecessary tool calls
5. **Baseline:** Current code (25+ iterations, many wasted calls)

Test matrix:

| Approach | Code Change | Effort | Expected Impact | Risk |
|----------|-------------|--------|-----------------|------|
| A (tool filtering) | executor.rs + template metadata | Medium | High (hard block) | Low |
| B (tool presets) | profile/mod.rs + template | Medium-High | High | Medium |
| C (task context) | context_builder.rs | Medium | High | Medium |
| D (position shuffle) | executor.rs | Low | Medium | Low |
| E (plan-only template) | executor.rs | Low | Medium | Low |
| F (hard subtasks) | scheduler.rs + template parser | High | Very High | High |
| G (negative prompt) | template files only | None | Low-Medium | None |
| H (tool ordering) | mcp/mod.rs | Low | Low | Low |
| I (toolsets) | profile/mod.rs + mcp/mod.rs | Medium-High | High | Medium |
| J (locked mode) | executor.rs + context_builder.rs | Medium | High | Medium |

---

## Recommended Initial Plan

### Phase 1 (Quick Wins — implement together)
- **H** — Reorder tool definitions (execution tools first)
- **D** — Move template to position 1 in message stack
- **E** — Clean planning phase for template-backed tasks
- **G** — Add prohibited/required tool lists to template files

### Phase 2 (Structural Changes)
- **J** — Implement locked execution mode for template-backed tasks
- **C** — Split context assembly into task vs conversation modes

### Phase 3 (Hard Guarantees)
- **A** — Per-task tool filtering (hard block at the registry level)
- **I** — Toolset concept for tasks

---

## Key Files to Modify

| File | Change |
|------|--------|
| `/opt/workspace/omniagent/src/agent/executor.rs` | Message ordering, template injection, context assembly logic |
| `/opt/workspace/omniagent/src/context_builder.rs` | Task vs conversation context modes |
| `/opt/workspace/omniagent/src/mcp/mod.rs` | Tool ordering in `to_openai_tools()` |
| `/opt/workspace/omniagent/src/prompt_builder.rs` | Template-aware prompt building |
| `/opt/workspace/omni-stack/profiles/default/templates/build-blog.md` | Tool constraints in template |
| `/opt/workspace/omni-stack/profiles/default/skills/workspace-development.md` | Tool constraints in skill |

---

## Debug Log — Experiment Results (June 26, 2026)

### Attempt 1: kanban task auto_subtasks, CONDENSE_KEEP_TURNS=0

**Settings:**
- MAX_ITERATIONS_COMPLEX_PLAN=10 (from .env) → agent hit iteration cap
- PLANNING_MODE=auto_subtasks (kanban got auto_subtasks via channel override + resolve_max_plan)
- CONDENSE_KEEP_TURNS=0 → ALL tool results compacted after 1 turn
- STATE_BLOCK_UPDATE_INTERVAL=1 → condensation check every turn
- channel test-cli planning_mode=auto_subtasks

**Result:** Agent created 6 subtasks but then fell into filesystem_list("/opt/workspace/blog") loop — called it 10+ times without writing any files.

**Root cause of loop:** CONDENSE_KEEP_TURNS=0 means all tool results are stripped on the next LLM call. The agent "forgets" it already listed the directory and lists again. The compressed metadata block doesn't convey "you already listed this" effectively.

**Fixes applied:**
1. MAX_ITERATIONS_COMPLEX_PLAN removed from .env — defaults to code default (600)
2. Removed MAX_ITERATIONS_COMPLEX_PLAN from /opt/data/.env (Hermes env) — was 60
3. CONDENSE_KEEP_TURNS=0 → 2 (keep last 2 full tool→result cycles)
4. STATE_BLOCK_UPDATE_INTERVAL=1 → 3 (check every 3 turns, less aggressive)
5. channel test-cli planning_mode='' (cleared — kanban uses global resolve_max_plan)
6. PLANNING_MODE set to auto_plan (via settings API, persisted in .env)
7. Removed legacy omniagent/.env file (compose is in omni-stack)

### Settings verification (after fixes):
- MAX_ITERATIONS_NO_PLAN: 30 (code default)
- MAX_ITERATIONS_SIMPLE_PLAN: 120 (code default)
- MAX_ITERATIONS_COMPLEX_PLAN: 600 (code default, no env override)
- PLANNING_MODE: auto_plan

### Env file situation (important!)
There are TWO .env files:
1. `/opt/workspace/omni-stack/.env` — read by docker compose `env_file: .env` at container start. Has CONDENSE_KEEP_TURNS, STATE_BLOCK_UPDATE_INTERVAL, PLANNING_MODE
2. `/opt/data/.env` (Hermes env) — mounted as `/opt/data/.env` IN the container, OVERRIDES the stack's .env. The settings API reads/writes THIS file.

The settings API writes to Hermes .env + calls set_var(). But when container restarts, compose loads the STACK .env, NOT the Hermes .env. So settings changes only survive restart if also in the stack .env.

**Fix applied:** Added PLANNING_MODE=auto_plan to both files via settings API (writes Hermes) and direct edit (stack .env).

### Attempt 2: pending — kanban task with auto_plan, CONDENSE_KEEP_TURNS=2
