//! mcp-server-docker-compose — standalone MCP server for docker compose commands.
//! Communicates via stdio JSON-RPC (MCP protocol).
//!
//! Tools: docker_compose

use anyhow::Result;
use mcp_server_util::*;
use serde_json::Value;
use std::path::Path;
use std::time::Duration;

/// Allowed compose subcommands. Everything else will be rejected.
const ALLOWED_VERBS: &[&str] = &[
    "up", "down", "ps", "logs", "build", "restart", "stop", "exec", "run", "pull",
];

/// Characters forbidden in non-exec/run arguments (compose verb, service name, flags).
const FORBIDDEN_CHARS: &[char] = &['|', ';', '&', '`', '$', '>', '<', '?', '[', ']', '{', '}', '!', '~'];

/// Validate that a string contains no forbidden shell-metacharacters.
fn contains_forbidden_chars(s: &str) -> bool {
    s.chars().any(|c| FORBIDDEN_CHARS.contains(&c))
}

/// Validate that a project directory is under the allowed workspace.
fn validate_workspace_path(project_dir: &str, workspace_dir: &str) -> Result<()> {
    if project_dir.is_empty() {
        return Ok(());
    }
    let resolved = Path::new(project_dir)
        .canonicalize()
        .map_err(|e| anyhow::anyhow!("Invalid project directory '{}': {}", project_dir, e))?;
    let workspace = Path::new(workspace_dir)
        .canonicalize()
        .unwrap_or_else(|_| Path::new(workspace_dir).to_path_buf());
    if !resolved.starts_with(&workspace) {
        anyhow::bail!(
            "Project directory must be under {}, got: {}",
            workspace_dir,
            project_dir
        );
    }
    if !resolved.is_dir() {
        anyhow::bail!("Project directory does not exist: {}", resolved.display());
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Tool: docker_compose
// ---------------------------------------------------------------------------

fn handle_compose(args: &Value) -> Result<(String, bool)> {
    let workspace_dir = std::env::var("WORKSPACE_DIR")
        .unwrap_or_else(|_| "/opt/workspace".to_string());

    let command = args["command"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing 'command' argument"))?
        .to_string();

    let project_dir = args["project_dir"].as_str().unwrap_or("").to_string();
    let service_name = args["service"].as_str().unwrap_or("");
    let exec_args = args["args"].as_str().unwrap_or("");

    // Validate project_dir
    if contains_forbidden_chars(&project_dir) {
        anyhow::bail!("Forbidden characters in project_dir argument");
    }
    if !project_dir.is_empty() {
        validate_workspace_path(&project_dir, &workspace_dir)?;
    }

    // Validate the compose verb is in the allowed list
    let verb = command.split_whitespace().next().unwrap_or("");
    if verb.is_empty() || !ALLOWED_VERBS.contains(&verb) {
        anyhow::bail!(
            "Unrecognized compose command '{}'. Allowed: {}",
            verb,
            ALLOWED_VERBS.join(", ")
        );
    }

    // Build the docker compose command
    let mut cmd = std::process::Command::new("docker");
    cmd.arg("compose");

    if !project_dir.is_empty() {
        cmd.current_dir(&project_dir);
    }

    // Add the compose subcommand (verb + flags from `command`)
    // Only validate non-exec/run parts for forbidden chars
    let parts: Vec<&str> = command.split_whitespace().collect();
    cmd.arg(verb);

    // Add any flags/args that were part of the `command` string (e.g. "-d" in "up -d")
    for part in &parts[1..] {
        if contains_forbidden_chars(part) {
            anyhow::bail!("Forbidden characters in command argument: '{}'", part);
        }
        cmd.arg(part);
    }

    // For exec and run: add service + args (unrestricted — they run inside the container)
    // std::process::Command passes args directly to the child process via execve,
    // so there is NO shell interpretation regardless of special characters.
    if verb == "exec" || verb == "run" {
        if service_name.is_empty() {
            anyhow::bail!("'service' is required for '{}' command", verb);
        }
        cmd.arg(service_name);

        // Args run inside the container — no character restrictions.
        // std::process::Command passes them directly via execve, no shell involved.
        if !exec_args.is_empty() {
            // Split the exec args so each word is a separate argv element.
            // This mirrors how `docker compose exec` expects them: as separate
            // arguments, not a single quoted string. Each element is passed
            // directly to execve inside the container.
            for arg in exec_args.split_whitespace() {
                cmd.arg(arg);
            }
        }
    }

    let timeout_secs = if command.starts_with("build") { 600u64 } else { 300u64 };

    // Use std::process::Command + mpsc for timeout
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let result = cmd.output();
        let _ = tx.send(result);
    });

    match rx.recv_timeout(Duration::from_secs(timeout_secs)) {
        Ok(Ok(output)) => {
            let stdout = String::from_utf8_lossy(&output.stdout).to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).to_string();
            let rc = output.status.code().unwrap_or(-1);

            if rc != 0 {
                let msg = if stderr.is_empty() {
                    format!("docker compose command failed (exit {}):\n{}", rc, stdout)
                } else {
                    format!("docker compose command failed (exit {}):\n{}", rc, stderr)
                };
                return Ok((msg, true));
            }

            let content = if stdout.is_empty() {
                format!("docker compose {}: ok", command)
            } else {
                // Truncate
                let max_chars: usize = 50_000;
                if stdout.len() > max_chars {
                    format!(
                        "```\n{}\n```\n\n[... truncated from {} to ~{} chars]",
                        &stdout[..max_chars],
                        stdout.len(),
                        max_chars
                    )
                } else {
                    format!("```\n{}\n```", stdout)
                }
            };

            Ok((content, false))
        }
        Ok(Err(e)) => Ok((format!("docker command failed: {}", e), true)),
        Err(_) => Ok((format!("docker command timed out after {}s", timeout_secs), true)),
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() -> Result<()> {
    let compose_handler: ToolHandler = Box::new(|args: &Value| handle_compose(args));

    let tools = vec![McpToolEntry {
        def: McpToolDef {
            name: "docker_compose".to_string(),
            description:
                "Run docker compose commands. \
                 Use 'project_dir' for the directory with docker-compose.yml. \
                 Use 'command' for the compose verb + flags (e.g. 'up -d', 'ps', 'logs --tail=50'). \
                 For exec/run: use 'service' (container name) and 'args' (command to run inside container). \
                 Args for exec/run have NO character restrictions — they run inside the container via Docker, \
                 not through a shell. Multiple commands work (e.g. args='sh -c \"cargo build && cargo test\"')."
                    .to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "Directory containing docker-compose.yml"
                    },
                    "command": {
                        "type": "string",
                        "description": "Compose subcommand and flags (e.g. 'up -d', 'ps', 'build', 'logs --tail=50')"
                    },
                    "service": {
                        "type": "string",
                        "description": "Service/container name (required for exec and run commands)"
                    },
                    "args": {
                        "type": "string",
                        "description": "Command to run inside the container (for exec/run). NO character restrictions — runs via Docker exec, not a shell. Examples: 'cargo build', 'npm test', 'sh -c \"cmd1 && cmd2\"'"
                    }
                },
                "required": ["project_dir", "command"]
            }),
        },
        handler: compose_handler,
    }];

    let server_info = ServerInfo {
        name: "mcp-server-docker-compose".to_string(),
        version: "0.1.0".to_string(),
    };

    run_server(server_info, tools).await
}
