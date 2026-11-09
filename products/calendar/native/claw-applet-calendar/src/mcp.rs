// SPDX-License-Identifier: GPL-3.0-only

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, AppError, CallContext, Tool, ToolResult};
use jiff::civil::Date;
use serde_json::{Value, json};

use crate::service::Client;

struct Day(Client);

fn date(input: &Value) -> Result<Date, String> {
    let text = input["date"].as_str().ok_or("date must be YYYY-MM-DD")?;
    let day: Date = text.parse().map_err(|_| "date must be a valid YYYY-MM-DD date")?;
    if day.to_string() != text {
        return Err("date must be YYYY-MM-DD".into());
    }
    Ok(day)
}

#[async_trait]
impl Tool for Day {
    fn name(&self) -> &str { "panel-calendar.day" }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let day = match date(&input) {
            Ok(day) => day,
            Err(error) => return ToolResult::error(error),
        };
        tokio::select! {
            biased;
            _ = context.cancelled() => ToolResult::error("Calendar call cancelled or deadline exceeded."),
            result = self.0.calendar_day(day) => match result {
                Ok(events) => ToolResult::structured(json!({"date": day.to_string(), "events": events}))
                    .unwrap_or_else(|error| ToolResult::error(error.to_string())),
                Err(error) => ToolResult::error(error),
            },
        }
    }
}

fn bind(mut app: App, client: Client) -> Result<App, AppError> {
    if app.id() != "panel-calendar" {
        return Err(AppError::Manifest("Calendar panel requires the panel-calendar identity".into()));
    }
    app.bind(Arc::new(Day(client)))?;
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
