use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};

use super::{CaptureError, CaptureOutcome};

pub(super) async fn capture(modal: bool) -> Result<CaptureOutcome, CaptureError> {
    let id = correlation()?;
    let mut response = call("request", json!({"request_id": id, "modal": modal})).await?;
    loop {
        if let Some(outcome) = outcome(response, &id)? {
            return Ok(outcome);
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
        response = call("status", json!({"request_id": id})).await?;
    }
}

fn correlation() -> Result<String, CaptureError> {
    let mut bytes = [0; 16];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(&mut bytes))
        .map_err(|error| CaptureError::Io(format!("Capture correlation: {error}")))?;
    Ok(bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>())
}

async fn call(action: &'static str, request: Value) -> Result<Value, CaptureError> {
    tokio::task::spawn_blocking(move || call_blocking(action, request))
    .await
    .map_err(|error| CaptureError::Other(format!("Capture service worker: {error}")))?
}

fn call_blocking(action: &str, request: Value) -> Result<Value, CaptureError> {
    claw_os_sdk::cos_call_json_with_stdin(
        "capture", action, ["__gui-capture", action, "--request-stdin"], request.to_string().as_bytes(),
    ).map_err(|error| CaptureError::Portal(format!("OS Capture service: {error}")))
}

pub(super) async fn save_capture(directory: Option<PathBuf>, modal: bool) -> Result<CaptureOutcome, CaptureError> {
    tokio::task::spawn_blocking(move || save(directory, modal)).await
        .map_err(|error| CaptureError::Other(format!("Capture output worker: {error}")))?
}

fn sdk<T>(result: Result<T, claw_os_sdk::BridgeError>) -> Result<T, CaptureError> {
    result.map_err(|error| CaptureError::Other(format!("OS selected output: {error}")))
}

fn save(directory: Option<PathBuf>, modal: bool) -> Result<CaptureOutcome, CaptureError> {
    let home = std::env::var_os("COS_OWNER_HOME").map(PathBuf::from)
        .ok_or_else(|| CaptureError::Io("GUI capture requires its authenticated owner Home context".into()))?;
    let directory = directory.unwrap_or_else(|| home.join("Pictures"));
    let directory = if directory.is_absolute() { directory } else { home.join(directory) };
    let metadata = directory.metadata().map_err(|error| CaptureError::Io(format!("capture destination: {error}")))?;
    if !metadata.is_dir() { return Err(CaptureError::Io("capture destination must be an existing directory".into())); }
    let node = metadata.ino();
    let name = jiff::Zoned::now().strftime("Screenshot_%Y-%m-%d_%H-%M-%S.png").to_string();
    let mut creation = sdk(claw_os_sdk::gui::request_file_create(node, &name))?;
    while creation.state == "pending" {
        std::thread::sleep(Duration::from_millis(250));
        creation = sdk(claw_os_sdk::gui::file_create_status(&creation.selection_id, node))?;
    }
    if creation.state != "selected" {
        return Err(CaptureError::Io(format!("screenshot output selection is {}", creation.state)));
    }
    let slot = sdk(claw_os_sdk::gui::reserve_file_create(&creation.selection_id, node))?;
    let id = correlation()?;
    let mut response = call_blocking("image", json!({"request_id":id,"modal":modal}))?;
    let length = loop {
        if response["version"] != 1 || response["request_id"] != id {
            return Err(CaptureError::Other("OS Capture image correlation failed".into()));
        }
        if response["status"] == "image" {
            let length = response["length"].as_u64().ok_or_else(|| CaptureError::Other("OS Capture image length is missing".into()))?;
            if length == 0 || length > 8 * 1024 * 1024 {
                return Err(CaptureError::Io("selected GUI output supports PNGs up to 8 MiB".into()));
            }
            break length;
        }
        if let Some(outcome) = outcome(response, &id)? { return Ok(outcome); }
        std::thread::sleep(Duration::from_millis(250));
        response = call_blocking("status", json!({"request_id":id}))?;
    };
    let temporary = directory.join(&slot.name);
    let target = directory.join(&slot.target_name);
    let mut output = std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600)
        .custom_flags(libc::O_NOFOLLOW).open(&temporary)
        .map_err(|error| CaptureError::Io(format!("create selected screenshot scratch: {error}")))?;
    let mut offset = 0;
    while offset < length {
        let value = call_blocking("read_image", json!({"request_id":id,"offset":offset}))?;
        let bytes = image_chunk(value, &id, offset, length)?;
        output.write_all(&bytes).map_err(|error| CaptureError::Io(format!("write selected screenshot: {error}")))?;
        offset += bytes.len() as u64;
    }
    output.sync_all().map_err(|error| CaptureError::Io(format!("sync selected screenshot: {error}")))?;
    drop(output);
    std::fs::rename(&temporary, &target).map_err(|error| CaptureError::Io(format!("finalize selected screenshot: {error}")))?;
    let status = sdk(claw_os_sdk::gui::file_create_status(&creation.selection_id, node))?;
    if status.state != "created" {
        return Err(CaptureError::Io(format!("screenshot creation is unconfirmed: {}", status.state)));
    }
    Ok(CaptureOutcome { path: target.to_string_lossy().into_owned(), cancelled: false })
}

fn image_chunk(value: Value, id: &str, offset: u64, length: u64) -> Result<Vec<u8>, CaptureError> {
    let invalid = || CaptureError::Other("OS Capture returned an invalid bounded PNG chunk".into());
    let fields = value.as_object().ok_or_else(invalid)?;
    let array = value["bytes"].as_array().ok_or_else(invalid)?;
    if fields.len() != 5 || value["version"] != 1 || value["request_id"] != id || value["offset"] != offset
        || array.is_empty() || array.len() > 128 * 1024 || offset + array.len() as u64 > length
        || value["done"].as_bool() != Some(offset + array.len() as u64 == length)
    { return Err(invalid()); }
    array.iter().map(|value| value.as_u64().and_then(|byte| u8::try_from(byte).ok()).ok_or_else(invalid)).collect()
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
        "icon": "com.yuos.Screenshot", "expire_ms": 5000, "transient": true,
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
