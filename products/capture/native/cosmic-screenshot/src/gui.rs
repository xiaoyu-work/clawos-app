use std::io::Read;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};

use super::{CaptureError, CaptureOutcome};

pub(super) async fn capture(modal: bool) -> Result<CaptureOutcome, CaptureError> {
    let mut bytes = [0; 16];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(&mut bytes))
        .map_err(|error| CaptureError::Io(format!("Capture correlation: {error}")))?;
    let id = bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut response = call("request", json!({"request_id": id, "modal": modal})).await?;
    loop {
        if let Some(outcome) = outcome(response, &id)? {
            return Ok(outcome);
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
        response = call("status", json!({"request_id": id})).await?;
    }
}

async fn call(action: &'static str, request: Value) -> Result<Value, CaptureError> {
    tokio::task::spawn_blocking(move || {
        claw_os_sdk::cos_call_json_with_stdin(
            "capture",
            action,
            ["__gui-capture", action, "--request-stdin"],
            request.to_string().as_bytes(),
        )
    })
    .await
    .map_err(|error| CaptureError::Other(format!("Capture service worker: {error}")))?
    .map_err(|error| CaptureError::Portal(format!("OS Capture service: {error}")))
}

fn outcome(value: Value, id: &str) -> Result<Option<CaptureOutcome>, CaptureError> {
    let invalid = || CaptureError::Other("OS Capture returned an invalid correlated status".into());
    let object = value.as_object().ok_or_else(invalid)?;
    if value["version"] != 1 || value["request_id"] != id {
        return Err(invalid());
    }
    let status = value["status"].as_str().ok_or_else(invalid)?;
    let extra = match status {
        "saved" => Some("path"),
        "failed" => Some("error"),
        _ => None,
    };
    if object.len() != 3 + usize::from(extra.is_some())
        || object.keys().any(|key| {
            !matches!(key.as_str(), "version" | "request_id" | "status")
                && Some(key.as_str()) != extra
        })
    {
        return Err(invalid());
    }
    match status {
        "pending" | "cancelling" => Ok(None),
        "clipboard" | "cancelled" => Ok(Some(CaptureOutcome {
            path: String::new(),
            cancelled: status == "cancelled",
        })),
        "saved" => {
            let path = value["path"].as_str().ok_or_else(invalid)?;
            if path.len() > 4096
                || !std::path::Path::new(path).is_absolute()
                || path.chars().any(char::is_control)
            {
                return Err(invalid());
            }
            // Metadata only: never open, move or infer a grant from this path.
            Ok(Some(CaptureOutcome {
                path: path.into(),
                cancelled: false,
            }))
        }
        "failed" => {
            let error = value["error"].as_str().ok_or_else(invalid)?;
            if error.len() > 2048 || error.chars().any(char::is_control) {
                return Err(invalid());
            }
            Err(CaptureError::Portal(error.into()))
        }
        "cleanup_pending" => Err(CaptureError::Portal(
            "OS Capture cleanup is unconfirmed; Root retains this window's custody".into(),
        )),
        _ => Err(invalid()),
    }
}

pub(super) async fn notify(
    app_name: String,
    summary: String,
    body: String,
) -> Result<(), CaptureError> {
    let until = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| CaptureError::Other(format!("notification clock: {error}")))?
        .as_millis()
        .checked_add(5000)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or_else(|| CaptureError::Other("notification deadline overflow".into()))?
        .to_string();
    let request = json!({
        "action": "post", "app_name": app_name, "summary": summary, "body": body,
        "icon": "com.clawos.Screenshot", "expire_ms": 5000, "transient": true,
    });
    tokio::task::spawn_blocking(move || {
        claw_os_sdk::cos_call_json_with_stdin(
            "notification",
            "post",
            [
                "__notifications",
                "request",
                "--request-stdin",
                "--deadline",
                &until,
            ],
            request.to_string().as_bytes(),
        )
    })
    .await
    .map_err(|error| CaptureError::Other(format!("notification worker: {error}")))?
    .map_err(|error| CaptureError::Other(format!("OS notification service: {error}")))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/gui.rs"));
}
