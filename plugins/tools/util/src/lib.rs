//! Shared MCP server framework - JSON-RPC stdio protocol, types, and helpers.
//!
//! Provides the runtime loop and type definitions needed by any stdio-based
//! MCP server.  Each server binary:
//!
//! 1. Defines its tools in `handle_tools_list()`
//! 2. Dispatches tool calls via `handle_tools_call()`
//! 3. Calls `run_server(server_info, handlers)` to start the loop
//!
//! ## Concurrency model
//!
//! Tools/call requests are dispatched to independent tokio tasks so that
//! long-running tools (e.g. docker compose) do not block other requests.
//! Responses are multiplexed over the single stdout stream using the
//! JSON-RPC request id - the MCP client matches responses to requests.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::Mutex;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// MCP protocol version (2025-03-26 is the current stable).
pub const MCP_PROTOCOL_VERSION: &str = "2025-03-26";

// ---------------------------------------------------------------------------
// JSON-RPC types
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    #[serde(default)]
    pub id: Option<u64>,
    pub method: String,
    #[serde(default)]
    pub params: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct JsonRpcSuccess {
    pub jsonrpc: String,
    pub id: u64,
    pub result: Value,
}

#[derive(Debug, Serialize)]
pub struct JsonRpcErrorResponse {
    pub jsonrpc: String,
    pub id: u64,
    pub error: JsonRpcError,
}

#[derive(Debug, Serialize)]
pub struct JsonRpcError {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

// ---------------------------------------------------------------------------
// MCP Initialize types
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
pub struct InitializeResult {
    #[serde(rename = "protocolVersion")]
    pub protocol_version: String,
    pub capabilities: ServerCapabilities,
    #[serde(rename = "serverInfo")]
    pub server_info: Implementation,
}

#[derive(Debug, Serialize)]
pub struct ServerCapabilities {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<ToolCapabilities>,
}

#[derive(Debug, Serialize)]
pub struct ToolCapabilities {
    #[serde(rename = "listChanged")]
    pub list_changed: bool,
}

#[derive(Debug, Serialize)]
pub struct Implementation {
    pub name: String,
    pub version: String,
}

// ---------------------------------------------------------------------------
// MCP tools/list types
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
pub struct ListToolsResult {
    pub tools: Vec<McpToolDef>,
}

#[derive(Debug, Clone, Serialize)]
pub struct McpToolDef {
    pub name: String,
    pub description: String,
    #[serde(rename = "inputSchema")]
    pub input_schema: Value,
}

// ---------------------------------------------------------------------------
// MCP tools/call types
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct CallToolParams {
    pub name: String,
    #[serde(default)]
    pub arguments: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct CallToolResult {
    pub content: Vec<ToolContent>,
    #[serde(default, rename = "isError")]
    pub is_error: bool,
}

#[derive(Debug, Serialize)]
#[serde(tag = "type")]
pub enum ToolContent {
    #[serde(rename = "text")]
    Text { text: String },
}

// ---------------------------------------------------------------------------
// Async handler type
// ---------------------------------------------------------------------------

/// Async handler function type - receives owned tool arguments,
/// returns result text + error flag as a future.
pub type AsyncToolHandler =
    Box<dyn Fn(Value) -> Pin<Box<dyn Future<Output = Result<(String, bool)>> + Send>>
        + Send
        + Sync>;

/// A registered tool definition + async handler.
pub struct McpToolEntry {
    pub def: McpToolDef,
    pub handler: AsyncToolHandler,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async fn send_error<W: AsyncWriteExt + Unpin>(
    writer: &mut tokio::io::BufWriter<W>,
    req_id: u64,
    code: i64,
    message: impl Into<String>,
) -> Result<()> {
    let response = JsonRpcErrorResponse {
        jsonrpc: "2.0".to_string(),
        id: req_id,
        error: JsonRpcError {
            code,
            message: message.into(),
            data: None,
        },
    };

    let json = serde_json::to_string(&response)?;
    writer.write_all(json.as_bytes()).await?;
    writer.write_all(b"\n").await?;
    writer.flush().await?;
    Ok(())
}

/// Shared writer so multiple tokio tasks can write to stdout safely.
type SharedWriter = Arc<Mutex<tokio::io::BufWriter<tokio::io::Stdout>>>;

fn make_writer() -> SharedWriter {
    Arc::new(Mutex::new(tokio::io::BufWriter::new(tokio::io::stdout())))
}

async fn send_success(writer: &SharedWriter, req_id: u64, result: Value) -> Result<()> {
    let response = JsonRpcSuccess {
        jsonrpc: "2.0".to_string(),
        id: req_id,
        result,
    };
    let json = serde_json::to_string(&response)?;
    let mut w = writer.lock().await;
    w.write_all(json.as_bytes()).await?;
    w.write_all(b"\n").await?;
    w.flush().await?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Server loop
// ---------------------------------------------------------------------------

/// Run the MCP stdio event loop with concurrent tool execution.
///
/// `server_info`: identity reported in initialize response.
/// `tools`: list of (tool_def, handler) pairs.
///
/// Tools/call requests are dispatched to independent tokio tasks so that
/// long-running tools do not block other requests.
pub async fn run_server(
    server_info: ServerInfo,
    tools: Vec<McpToolEntry>,
) -> Result<()> {
    // Initialize tracing - log to stderr
    let _ = tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| format!("info").into()),
        )
        .with_writer(std::io::stderr)
        .try_init();

    tracing::info!("{} MCP server starting", server_info.name);

    let index: Arc<HashMap<String, McpToolEntry>> =
        Arc::new(tools.into_iter().map(|t| (t.def.name.clone(), t)).collect());

    let stdin = tokio::io::stdin();
    let reader = BufReader::new(stdin);
    let mut lines = reader.lines();

    let writer = make_writer();
    let mut initialized = false;

    while let Some(line) = lines.next_line().await? {
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }

        let request: JsonRpcRequest = match serde_json::from_str(&line) {
            Ok(req) => req,
            Err(e) => {
                tracing::error!("Failed to parse JSON-RPC: {e}");
                continue;
            }
        };

        let req_id = request.id;
        let method = request.method.as_str();

        match method {
            "initialize" => {
                if let Some(id) = req_id {
                    handle_initialize(&writer, id, &server_info).await?;
                    initialized = true;
                }
            }
            "notifications/initialized" => {
                tracing::info!("Client initialized notification received");
            }
            "tools/list" => {
                if !initialized {
                    send_error(
                        &mut *writer.lock().await,
                        req_id.unwrap_or(0),
                        -32000,
                        "Server not initialized",
                    )
                    .await?;
                    continue;
                }
                if let Some(id) = req_id {
                    handle_tools_list(&writer, id, &index).await?;
                }
            }
            "tools/call" => {
                if !initialized {
                    send_error(
                        &mut *writer.lock().await,
                        req_id.unwrap_or(0),
                        -32000,
                        "Server not initialized",
                    )
                    .await?;
                    continue;
                }
                if let Some(id) = req_id {
                    let params = request.params.unwrap_or_default();
                    let call_params: CallToolParams =
                        match serde_json::from_value(params) {
                            Ok(p) => p,
                            Err(e) => {
                                send_error(
                                    &mut *writer.lock().await,
                                    id,
                                    -32602,
                                    format!("Invalid tools/call params: {e}"),
                                )
                                .await?;
                                continue;
                            }
                        };

                    let index_clone = index.clone();
                    let writer_clone = writer.clone();

                    // Spawn each tool call as an independent task so
                    // long-running tools don't block other requests.
                    tokio::spawn(async move {
                        if let Err(e) = handle_tools_call_concurrent(
                            &writer_clone,
                            id,
                            &call_params,
                            &index_clone,
                        )
                        .await
                        {
                            tracing::error!(
                                "tools/call '{}' failed: {e}",
                                call_params.name
                            );
                        }
                    });
                }
            }
            _ => {
                tracing::warn!("Unknown method: {method}");
                if let Some(id) = req_id {
                    send_error(
                        &mut *writer.lock().await,
                        id,
                        -32601,
                        format!("Method not found: {method}"),
                    )
                    .await?;
                }
            }
        }
    }

    tracing::info!(
        "{} MCP server shutting down (stdin closed)",
        server_info.name
    );
    Ok(())
}

// ---------------------------------------------------------------------------
// Initial handler implementations (synchronous, writer is Arc<Mutex<>>)
// ---------------------------------------------------------------------------

async fn handle_initialize(
    writer: &SharedWriter,
    req_id: u64,
    server_info: &ServerInfo,
) -> Result<()> {
    let result = InitializeResult {
        protocol_version: MCP_PROTOCOL_VERSION.to_string(),
        capabilities: ServerCapabilities {
            tools: Some(ToolCapabilities { list_changed: false }),
        },
        server_info: Implementation {
            name: server_info.name.clone(),
            version: server_info.version.clone(),
        },
    };
    send_success(writer, req_id, serde_json::to_value(result)?).await?;
    tracing::info!("Initialized: {} v{}", server_info.name, server_info.version);
    Ok(())
}

async fn handle_tools_list(
    writer: &SharedWriter,
    req_id: u64,
    index: &Arc<HashMap<String, McpToolEntry>>,
) -> Result<()> {
    let defs: Vec<McpToolDef> =
        index.values().map(|t| t.def.clone()).collect();
    let result = ListToolsResult { tools: defs };
    send_success(writer, req_id, serde_json::to_value(result)?).await?;
    tracing::info!("tools/list returned {} tool(s)", index.len());
    Ok(())
}

/// Run a single tool call handler asynchronously and write the response.
async fn handle_tools_call_concurrent(
    writer: &SharedWriter,
    req_id: u64,
    params: &CallToolParams,
    index: &Arc<HashMap<String, McpToolEntry>>,
) -> Result<()> {
    tracing::info!("tools/call: name='{}'", params.name);

    let entry = match index.get(&params.name) {
        Some(e) => e,
        None => {
            send_error(
                &mut *writer.lock().await,
                req_id,
                -32602,
                format!("Unknown tool: {}", params.name),
            )
            .await?;
            return Ok(());
        }
    };

    let args = params
        .arguments
        .clone()
        .unwrap_or(serde_json::Value::Null);

    let (text, is_error) = match (entry.handler)(args).await {
        Ok(result) => result,
        Err(e) => {
            send_error(
                &mut *writer.lock().await,
                req_id,
                -32603,
                format!("Handler error: {e}"),
            )
            .await?;
            return Ok(());
        }
    };

    let result = CallToolResult {
        content: vec![ToolContent::Text { text }],
        is_error,
    };

    send_success(writer, req_id, serde_json::to_value(result)?).await?;
    tracing::info!(
        "tools/call '{}' completed (is_error={})",
        params.name,
        is_error
    );
    Ok(())
}

// ---------------------------------------------------------------------------
// Server info
// ---------------------------------------------------------------------------

/// Server identity.
#[derive(Debug, Clone)]
pub struct ServerInfo {
    pub name: String,
    pub version: String,
}
