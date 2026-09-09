//! MCP controls the same native playback state through the fixed OS adapter.
//! No session-bus transport, media URL, process launch or other App is exposed.

use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, AppError, CallContext, Tool, ToolResult};
use serde_json::Value;

struct PlayerTool(&'static str);

#[async_trait]
impl Tool for PlayerTool {
    fn name(&self) -> &'static str { self.0 }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        if !input.as_object().is_some_and(|value| value.is_empty()) {
            return ToolResult::error("Media Player tools take no arguments");
        }
        let deadline = match SystemTime::now().duration_since(UNIX_EPOCH) {
            Ok(now) => (now.as_millis() as u64 + 5000).min(context.deadline_unix_ms().unwrap_or(u64::MAX)),
            Err(_) => return ToolResult::error("invalid system clock"),
        };
        let action = self.0.strip_prefix("player.").expect("fixed tool name");
        let deadline = deadline.to_string();
        let call = claw_os_sdk::cos_call_json_async_with_binary(
            "/usr/local/bin/cos", "media-player", action,
            ["__media-player", action, "--deadline", &deadline],
        );
        tokio::select! {
            biased;
            _ = context.cancelled() => ToolResult::error("Media Player call cancelled"),
            result = call => match result {
                Ok(value) => ToolResult::text(value.to_string()),
                Err(error) => ToolResult::error(error.to_string()),
            },
        }
    }
}

pub(crate) fn run() -> Result<(), Box<dyn std::error::Error>> {
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build()?;
    runtime.block_on(async {
        let mut app = App::from_environment()?;
        if app.id() != "cosmic-player" {
            return Err(AppError::Manifest("Media Player requires the cosmic-player identity".into()));
        }
        for name in ["player.play", "player.pause", "player.stop", "player.next",
            "player.previous", "player.toggle", "player.status"] {
            app.bind(Arc::new(PlayerTool(name)))?;
        }
        app.serve_stdio().await
    })?;
    Ok(())
}
