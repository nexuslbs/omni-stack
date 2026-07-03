# Knowledge Pipeline

**IMPORTANT: Use YOUR current thread_id for manage_subtasks calls.** Do NOT reuse thread_ids from previous runs or examples. Your thread_id is the one that was created for THIS cron execution.

## Steps (Execute In Order)

### Step A: Create Subtasks
Call `manage_subtasks` with THIS thread's actual ID (not from examples or previous runs) for all 6 steps. Give them priority 6→1.

### Step B: Channel Summarization
Query channels + summaries. Verify each active channel has at least one summary.

### Step C: Wiki/Skill Update
Query completed threads (last 7 days, status='completed', cause IN user/kanban/cron). Group by profile. Scan top 10 threads per profile for: user corrections, pitfalls, decisions, successful approaches. Update wiki files. Max 3 wiki + 1 skill update per run.

### Step D: Wiki Relevance Indexing
Run tool: `actions_relevance_indexer`

### Step E: Skill Relevance Indexing
Run tool: `actions_skill_indexer` (or compute scores manually from recency + ref count)

### Step F: Hindsight Population
Run tool: `actions_hindsight_populator`. If hindsight unavailable → cancel step.

### Step G: Hindsight Consolidation
If hindsight enabled, POST to `http://omniagent-hindsight:8888/v1/default/banks/omniagent/consolidate`. If not enabled → cancel step.

## After All Steps
Call `manage_subtasks(thread_id=THIS_ID, action="list")` to verify. Write a final message summarizing which steps succeeded/failed/skipped.
