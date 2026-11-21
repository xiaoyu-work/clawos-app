// SPDX-License-Identifier: GPL-3.0-only
//! One OS service client shared by Applications UI and authenticated MCP.
use serde_json::{Value, json};

pub async fn call(request: Value) -> Result<Value, String> {
    tokio::task::spawn_blocking(move || {
        claw_os_sdk::cos_call_json_with_binary(
            "/usr/local/bin/yu",
            "permissions",
            "manage",
            vec!["__app-permissions".into(), request.to_string()],
        )
        .map_err(|error| {
            format!("App permission service: {error}. Update the OS service and refresh Settings.")
        })
    })
    .await
    .map_err(|error| error.to_string())?
}

pub fn choice(allow: bool, app: &str, permission: &str, revision: &str) -> Value {
    json!({
        "action": if allow { "allow" } else { "deny" },
        "app_id": app, "permission_id": permission, "revision": revision,
    })
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/permissions.rs"
    ));
}
