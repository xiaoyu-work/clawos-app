// SPDX-License-Identifier: GPL-3.0-only

use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Copy)]
pub(crate) enum HistoryAction {
    List,
    Restore,
    Remove,
    Clear,
}

impl HistoryAction {
    pub(crate) fn command(self) -> &'static str {
        match self {
            Self::List => "history-list",
            Self::Restore => "history-restore",
            Self::Remove => "history-remove",
            Self::Clear => "history-clear",
        }
    }
}

pub(crate) fn valid_identity(value: &str) -> bool {
    value.len() == 44
        && value.ends_with('=')
        && value[..43]
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/'))
}

pub(crate) async fn history(
    action: HistoryAction,
    identity: Option<&str>,
    confirm: bool,
    deadline: Option<u64>,
) -> Result<Value, String> {
    request("/usr/local/bin/cos", action, identity, confirm, deadline).await
}

async fn request(
    binary: impl AsRef<std::path::Path>,
    action: HistoryAction,
    identity: Option<&str>,
    confirm: bool,
    deadline: Option<u64>,
) -> Result<Value, String> {
    match action {
        HistoryAction::List if identity.is_none() && !confirm => {}
        HistoryAction::Clear if identity.is_none() && confirm => {}
        HistoryAction::Restore | HistoryAction::Remove
            if !confirm && identity.is_some_and(valid_identity) => {}
        _ => return Err("invalid clipboard history arguments".into()),
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "invalid system clock")?
        .as_millis() as u64;
    let deadline = deadline.unwrap_or(u64::MAX).min(now + 2000);
    if deadline <= now {
        return Err("clipboard history deadline expired".into());
    }
    let mut args = vec![
        "__clipboard".to_string(),
        action.command().to_string(),
        "--deadline".to_string(),
        deadline.to_string(),
    ];
    if let Some(identity) = identity {
        args.extend(["--identity".into(), identity.into()]);
    }
    if confirm {
        args.push("--confirm".into());
    }
    claw_os_sdk::cos_call_json_async_with_binary(
        binary.as_ref(),
        "clipboard",
        action.command(),
        args,
    )
    .await
    .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/service.rs"));
}
