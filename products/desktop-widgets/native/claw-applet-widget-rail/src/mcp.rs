// SPDX-License-Identifier: GPL-3.0-only

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, AppError, CallContext, Tool, ToolResult};
use serde_json::{Value, json};

use crate::service::Client;

#[derive(Clone, Copy)]
enum Source { Calendar, Tasks, System }

struct Read(Source, Client);

impl Read {
    async fn read(&self) -> Result<Value, String> {
        match self.0 {
            Source::Calendar => Ok(json!({"events": self.1.calendar_today().await?})),
            Source::Tasks => Ok(json!({"tasks": self.1.tasks().await?})),
            Source::System => Ok(json!({"summary": self.1.system().await?})),
        }
    }
}

#[async_trait]
impl Tool for Read {
    fn name(&self) -> &str {
        match self.0 {
            Source::Calendar => "widget-rail.calendar",
            Source::Tasks => "widget-rail.tasks",
            Source::System => "widget-rail.system",
        }
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        if !input.as_object().is_some_and(|args| args.is_empty()) {
            return ToolResult::error("Widget Rail read tools take no arguments.");
        }
        tokio::select! {
            biased;
            _ = context.cancelled() => ToolResult::error("Widget Rail call cancelled or deadline exceeded."),
            result = self.read() => match result {
                Ok(value) => ToolResult::structured(value)
                    .unwrap_or_else(|error| ToolResult::error(error.to_string())),
                Err(error) => ToolResult::error(error),
            },
        }
    }
}

fn bind(mut app: App, client: Client) -> Result<App, AppError> {
    if app.id() != "widget-rail" {
        return Err(AppError::Manifest("Widget Rail requires the widget-rail identity".into()));
    }
    for source in [Source::Calendar, Source::Tasks, Source::System] {
        app.bind(Arc::new(Read(source, client.clone())))?;
    }
    Ok(app)
}

pub(crate) fn run() -> Result<(), Box<dyn std::error::Error>> {
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build()?;
    runtime.block_on(bind(App::from_environment()?, Client::installed())?.serve_stdio())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/mcp.rs"));
}
