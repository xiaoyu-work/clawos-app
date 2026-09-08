//! MCP tool surface for the kernel agent.
//!
//! When spawned with `COS_MCP_SERVER=1`, `cosmic-screenshot` flips
//! into a tiny MCP stdio server that exposes one tool —
//! `screenshot.capture` — backed by the same non-interactive OS service
//! as the CLI. Interactive destination/clipboard selection remains a human
//! portal action, never a way to escape the MCP output-directory grant.

use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, AppError, CallContext, Tool, ToolResult};
use serde_json::{Value, json};

use crate::noninteractive;

fn options(input: Value) -> Result<(PathBuf, bool), String> {
    let input = input
        .as_object()
        .ok_or("capture arguments must be an object")?;
    if input
        .keys()
        .any(|key| !matches!(key.as_str(), "interactive" | "modal" | "save_dir"))
    {
        return Err("unknown capture argument".into());
    }
    let boolean = |name: &str, default: bool| match input.get(name) {
        None => Ok(default),
        Some(Value::Bool(value)) => Ok(*value),
        _ => Err(format!("{name} must be a boolean")),
    };
    if boolean("interactive", false)? {
        return Err("interactive capture is human-only; use the native portal UI".into());
    }
    let modal = boolean("modal", true)?;
    let path = input
        .get("save_dir")
        .and_then(Value::as_str)
        .ok_or("App Host must supply the owner's resolved save_dir")?;
    if path.is_empty()
        || path.len() > 4096
        || path.contains('\0')
        || !std::path::Path::new(path).is_absolute()
    {
        return Err("save_dir must be an owner-resolved absolute path without NUL".into());
    }
    Ok((PathBuf::from(path), modal))
}

pub(crate) struct CaptureTool;

#[async_trait]
impl Tool for CaptureTool {
    fn name(&self) -> &'static str {
        "screenshot.capture"
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let (directory, modal) = match options(input) {
            Ok(options) => options,
            Err(error) => return ToolResult::error(error),
        };

        let result = noninteractive(directory, modal, false).await;
        match result {
            Ok(outcome) if outcome.cancelled => ToolResult::text(
                json!({"cancelled": true, "path": null}).to_string(),
            ),
            Ok(outcome) => ToolResult::text(
                json!({
                    "cancelled": false,
                    "path": if outcome.path.is_empty() { Value::Null } else { Value::String(outcome.path) }
                })
                .to_string(),
            ),
            Err(err) => ToolResult::error(format!("screenshot capture failed: {err}")),
        }
    }
}

pub(crate) async fn run() -> Result<(), AppError> {
    let mut app = App::from_environment()?;
    if app.id() != "cosmic-screenshot" {
        return Err(AppError::Manifest(
            "Capture requires the cosmic-screenshot identity".into(),
        ));
    }
    app.bind(Arc::new(CaptureTool))?;
    app.serve_stdio().await
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/mcp.rs"));
}
