// SPDX-License-Identifier: MPL-2.0

use serde_json::Value;
use std::sync::{Mutex, OnceLock};

static FAILURE: OnceLock<Mutex<Option<String>>> = OnceLock::new();

pub fn failure() -> Option<String> {
    FAILURE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap()
        .clone()
}

pub fn refused(error: impl std::fmt::Display) -> String {
    let message = error.to_string();
    *FAILURE.get_or_init(|| Mutex::new(None)).lock().unwrap() = Some(message.clone());
    message
}

fn arguments(service: &str, action: &str, options: Vec<String>) -> Vec<String> {
    let mut args = vec![format!("__{service}"), action.into()];
    args.extend(options);
    args
}

fn confirmed(value: Value) -> Result<Value, String> {
    if value.get("post_state_error").is_some() {
        return Err(refused(
            "The OS admitted the change but could not confirm its final state. Refresh before retrying; no fallback or rollback was attempted.",
        ));
    }
    Ok(value)
}

pub fn call(service: &str, action: &str, options: Vec<String>) -> Result<Value, String> {
    confirmed(
        claw_os_sdk::cos_call_json_with_binary(
            "/usr/local/bin/cos",
            "settings",
            service,
            arguments(service, action, options),
        )
        .map_err(refused)?,
    )
}

pub async fn call_async(
    service: &str,
    action: &str,
    options: Vec<String>,
) -> Result<Value, String> {
    confirmed(
        claw_os_sdk::cos_call_json_async_with_binary(
            "/usr/local/bin/cos",
            "settings",
            service,
            arguments(service, action, options),
        )
        .await
        .map_err(refused)?,
    )
}
