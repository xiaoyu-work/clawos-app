// SPDX-License-Identifier: GPL-3.0-only

use std::sync::Arc;

use async_trait::async_trait;
use claw_os_sdk::mcp::{App, AppError, CallContext, Tool, ToolResult};
use serde::Deserialize;
use serde_json::Value;

use crate::service::{self, HistoryAction};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Item {
    identity: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Clear {
    confirm: bool,
}

pub(crate) fn arguments(
    name: &str,
    input: Value,
) -> Result<(HistoryAction, Option<String>, bool), String> {
    match name {
        "history.list" if input.as_object().is_some_and(|value| value.is_empty()) => {
            Ok((HistoryAction::List, None, false))
        }
        "history.restore" | "history.remove" => {
            let item: Item = serde_json::from_value(input)
                .map_err(|_| "history requires exactly one item identity")?;
            if !service::valid_identity(&item.identity) {
                return Err("invalid clipboard history identity".into());
            }
            Ok((
                if name == "history.restore" {
                    HistoryAction::Restore
                } else {
                    HistoryAction::Remove
                },
                Some(item.identity),
                false,
            ))
        }
        "history.clear" => {
            let clear: Clear = serde_json::from_value(input)
                .map_err(|_| "history clear requires explicit confirmation")?;
            if !clear.confirm {
                return Err("history clear requires confirm=true".into());
            }
            Ok((HistoryAction::Clear, None, true))
        }
        _ => Err("invalid clipboard history operation or arguments".into()),
    }
}

struct HistoryTool(&'static str);

#[async_trait]
impl Tool for HistoryTool {
    fn name(&self) -> &'static str {
        self.0
    }

    async fn handle(&self, input: Value, context: CallContext) -> ToolResult {
        if let Err(error) = context.check_cancelled() {
            return ToolResult::error(error.to_string());
        }
        let (action, identity, confirm) = match arguments(self.0, input) {
            Ok(value) => value,
            Err(error) => return ToolResult::error(error),
        };
        tokio::select! {
            biased;
            _ = context.cancelled() => ToolResult::error("clipboard history call cancelled; inspect state before retrying"),
            result = service::history(action, identity.as_deref(), confirm, context.deadline_unix_ms()) => match result {
                Ok(value) => ToolResult::text(value.to_string()),
                Err(error) => ToolResult::error(error),
            },
        }
    }
}

pub(crate) fn run() -> Result<(), Box<dyn std::error::Error>> {
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?
        .block_on(async {
            let mut app = App::from_environment()?;
            if app.id() != "panel-clipboard" {
                return Err(AppError::Manifest(
                    "Clipboard History requires its panel-clipboard manifest".into(),
                ));
            }
            for name in [
                "history.list",
                "history.restore",
                "history.remove",
                "history.clear",
            ] {
                app.bind(Arc::new(HistoryTool(name)))?;
            }
            app.serve_stdio().await
        })?;
    Ok(())
}
