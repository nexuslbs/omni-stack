# Compose MCP Exec Bug — Root Cause & Fix

## Date: 2026-06-27

## 1. The Problem

The omniagent (Kanban wiki task, thread 71) kept hitting two errors when trying to run commands inside Wiki.js:

1. **Exit 127 even for `echo hello`** — "command not found"
2. **"Forbidden characters in command argument"** — complex shell syntax rejected

## 2. Root Cause: Double Service Name

The `build_compose_command()` in `plugins/mcp/docker-compose/src/main.rs` at **line 89-97** parses the `command` field:

```rust
let parts: Vec<&str> = command.split_whitespace().collect();
cmd.arg(verb);            // line 90 - "exec"

for part in &parts[1..] {  // line 92 - validates flags
    if contains_forbidden_chars(part) {
        anyhow::bail!("Forbidden characters in command argument: '{}'", part);
    }
    cmd.arg(part);
}
```

When the LLM sends:
```json
{ "command": "exec -T wiki", "service": "wiki", "args": "echo hello" }
```

**What happens:**
- `parts[1..]` = `["-T", "wiki"]` → these are added as raw docker args
- Then line 109: `cmd.arg(service_name)` → adds `"wiki"` AGAIN

**Resulting command:**
```
docker compose exec -T wiki wiki sh -c echo hello
```

The `wiki` service name appears **twice** — once from the `command` field's `parts[1..]`, once from `service_name`. Docker Compose interprets the first `wiki` as the service name (correct) and the second `wiki` as the command to run inside, which fails with exit 127.

## 3. The "Forbidden Characters" Issue

When the LLM puts complex shell syntax in the `command` field:
```json
{ "command": "exec -T wiki sh -c 'cat > /tmp/file << EOF'", ... }
```

`parts[1..]` = `["-T", "wiki", "sh", "-c", "'cat", ">", "/tmp/file", "<<", "EOF'"]`

Characters like `>`, `<` hit `contains_forbidden_chars()` → bail.

**Note: The `args` parameter is NOT checked for forbidden chars** (lines 110-118 pass it raw to `sh -c`). The bug is that the LLM puts the command in the `command` field instead of the `args` field.

## 4. Code Path for `exec` + `args` (lines 99-120)

```
if verb == "exec" || verb == "run" {
    if service_name.is_empty() {
        bail!("'service' is required for '{}' command", verb);
    }
    if verb == "exec" && !raw_script.is_empty() {
        // Script path: pipe via stdin
        cmd.arg("-T");
        cmd.arg(service_name);
        cmd.arg("python3");
    } else {
        cmd.arg(service_name);                            // <-- adds service
        if !exec_args.is_empty() {
            cmd.arg("sh"); cmd.arg("-c"); cmd.arg(exec_args); // <-- no validation
        }
    }
}
```

## 5. Fix

### Fix the tool (omni-stack repo, `plugins/mcp/docker-compose/src/main.rs`)

In `build_compose_command()`, **before adding parts[1..] as raw args**, check if verb is `exec`/`run` and strip the first word of parts[1..] if it matches `service_name`:

```rust
// After line 90: cmd.arg(verb);
// Before line 92 (the for loop):

let mut extra_parts: Vec<&str> = parts[1..].to_vec();

if (verb == "exec" || verb == "run") && !service_name.is_empty() {
    // Strip duplicate service name if LLM included it in the command field
    if extra_parts.first() == Some(&service_name.as_str()) {
        extra_parts.remove(0);
    }
}

for part in &extra_parts {
    if contains_forbidden_chars(part) {
        anyhow::bail!("Forbidden characters in command argument: '{}'", part);
    }
    cmd.arg(part);
}
```

### Fix the tool description (lines 280-292)

Make it crystal clear:
> "For `exec`/`run`: use `command` = just the verb (e.g. `\"exec\"`), `service` = container name, `args` = command to run inside. Do NOT put the service name or full command in the `command` field."

### Fix the `args` handling for the `cd` / port issue

The existing `sh -c` wrapping (lines 116-118) is correct. But there's a subtle issue: if `parts[1..]` includes `-T` (no TTY), it goes before the service. The current code at line 103 already handles `-T` for the script path, but the exec_args path at line 108-119 does NOT add `-T`. This means the exec_args path might hang on commands that produce output to a TTY.

**Fix**: Add `-T` to the exec_args path too:
```rust
} else {
    cmd.arg("-T");  // no TTY -- prevents hangs
    cmd.arg(service_name);
    if !exec_args.is_empty() {
        cmd.arg("sh");
        cmd.arg("-c");
        cmd.arg(exec_args);
    }
}
```

## 6. Build & Deploy

```bash
cd /opt/workspace/omni-stack/plugins/mcp/docker-compose
cargo build --release
sudo cp target/release/mcp-server-docker-compose /opt/workspace/omniagent/target/release/
sudo chown hermes:hermes /opt/workspace/omniagent/target/release/mcp-server-docker-compose
cd /opt/workspace/omni-stack && docker compose restart omniagent
```

## 7. Verification

Deploy a test wiki:
```json
{
  "command": "exec",
  "service": "wiki",
  "project_dir": "/opt/workspace/wiki",
  "args": "echo hello"
}
```

Should return `hello` not exit 127.
