// SPDX-License-Identifier: GPL-3.0-only
//! One OS service client shared by Applications UI and authenticated MCP.
use serde_json::{Value, json};

pub async fn call(request: Value) -> Result<Value, String> {
    tokio::task::spawn_blocking(move || {
        claw_os_sdk::cos_call_json_with_binary(
            "/usr/local/bin/cos",
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

pub async fn decide(id: String, approve: bool) -> Result<Value, String> {
    if std::env::var_os("COS_MCP_SERVER").is_some() {
        return Err("MCP cannot invoke trusted approval".into());
    }
    if !valid_request_id(&id) {
        return Err("invalid approval request id".into());
    }
    let mut command = tokio::process::Command::new("/usr/bin/pkexec");
    command.args([
        "/usr/local/bin/claw-approval-helper",
        "--id",
        &id,
        "--decision",
        if approve { "approve" } else { "deny" },
        "--duration",
        "forever",
    ]);
    command.kill_on_drop(true);
    command.stdin(std::process::Stdio::null());
    let output = tokio::time::timeout(std::time::Duration::from_secs(120), command.output())
        .await
        .map_err(|_| "Trusted confirmation timed out; refresh to check the decision".to_string())?
        .map_err(|error| format!("Cannot start trusted approval helper: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "Trusted confirmation declined or unavailable: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Invalid approval response: {error}"))
}

fn valid_request_id(id: &str) -> bool {
    id.starts_with("ap-")
        && id.len() <= 128
        && id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

pub fn request(action: &str, app: &str, permission: &str) -> Value {
    json!({"action":action, "app_id":app, "permission_id":permission,
        "reason":"Restore this declared App permission, subject to the existing OS launch and capability ceilings."})
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/permissions.rs"
    ));
}
