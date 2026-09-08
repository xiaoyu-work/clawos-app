//! MCP tool surface for `cosmic-term`.
//!
//! When launched with `COS_MCP_SERVER=1`, the binary flips into a tiny
//! stdio MCP server instead of opening a terminal window. The agent
//! gets a controlled shell-execution path that goes through the same
//! capability gate as the canonical Terminal command library, with
//! audit logging and timeout enforcement built in.
//!
//! `apps/cosmic-term/app.json` is authoritative for the tool catalog and
//! manifest-derived process and filesystem grants.

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, CallContext, Tool, ToolResult};
use serde_json::{json, Value};

// ---------------------------------------------------------------------------
// term.run — capability-gated single-shot command execution
// ---------------------------------------------------------------------------

struct RunTool;

#[async_trait]
impl Tool for RunTool {
    fn name(&self) -> &'static str {
        "term.run"
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let command = match input.get("command").and_then(|v| v.as_str()) {
            Some(command) => command.to_string(),
            None => return ToolResult::error("missing command"),
        };
        if command.is_empty() || command.contains('\0') {
            return ToolResult::error("command must be nonempty without NUL");
        }
        let arguments: Vec<String> = match input.get("arguments") {
            None => Vec::new(),
            Some(Value::Array(values)) => {
                let Some(arguments) = values.iter().map(|v| {
                    v.as_str().filter(|s| !s.contains('\0')).map(str::to_string)
                }).collect::<Option<Vec<_>>>() else {
                    return ToolResult::error("arguments must contain only strings without NUL");
                };
                arguments
            }
            Some(_) => return ToolResult::error("arguments must be an array"),
        };
        let timeout = input
            .get("timeout_secs")
            .and_then(|v| v.as_u64())
            .unwrap_or(30)
            .clamp(1, 600) as u32;

        let res = tokio::task::spawn_blocking(move || {
            crate::product::command("run", json!({
                "command": command, "arguments": arguments, "timeout_secs": timeout,
            }))
        })
        .await;

        match res {
            Ok(Ok(r)) => ToolResult::text(r.to_string()),
            Ok(Err(e)) => ToolResult::error(format!("term.run: {e}")),
            Err(e) => ToolResult::error(format!("term.run join: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// term.which — capability-gated PATH lookup
// ---------------------------------------------------------------------------

struct WhichTool;

#[async_trait]
impl Tool for WhichTool {
    fn name(&self) -> &'static str {
        "term.which"
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let program = match input.get("program").and_then(|v| v.as_str()) {
            Some(s) => s.to_string(),
            None => return ToolResult::error("missing program"),
        };
        if program.is_empty() || program.contains('\0') {
            return ToolResult::error("program must be nonempty without NUL");
        }
        let res = tokio::task::spawn_blocking(move || {
            crate::product::command("which", json!({"program": program}))
        }).await;
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        match res {
            Ok(Ok(r)) => ToolResult::text(r.to_string()),
            Ok(Err(e)) => ToolResult::error(format!("term.which: {e}")),
            Err(e) => ToolResult::error(format!("term.which join: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// term.open — spawn a real interactive cosmic-term window at `cwd`
// ---------------------------------------------------------------------------

struct OpenTool;

#[async_trait]
impl Tool for OpenTool {
    fn name(&self) -> &'static str {
        "term.open"
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let cwd = match input.get("cwd") {
            None => None,
            Some(Value::String(value)) => Some(value.clone()),
            Some(_) => return ToolResult::error("cwd must be a string"),
        };
        let res = tokio::task::spawn_blocking(move || {
            crate::product::open(cwd.as_deref())
        })
        .await;
        match res {
            Ok(Ok(_)) => ToolResult::text(json!({"opened": true}).to_string()),
            Ok(Err(e)) => ToolResult::error(format!("term.open: {e}")),
            Err(e) => ToolResult::error(format!("term.open join: {e}")),
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

pub(crate) fn run() -> anyhow::Result<()> {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    rt.block_on(async {
        let mut app = App::from_environment()?;
        app.bind(Arc::new(RunTool))?;
        app.bind(Arc::new(WhichTool))?;
        app.bind(Arc::new(OpenTool))?;
        app.serve_stdio().await
    })
    .map_err(|error| anyhow::anyhow!("cosmic-term MCP server exited: {error}"))
}
