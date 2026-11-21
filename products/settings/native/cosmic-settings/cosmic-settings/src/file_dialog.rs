// SPDX-License-Identifier: GPL-3.0-only
//! The OS chooser returns references only. Content access is a separate service.

use serde::Deserialize;
use serde_json::{Value, json};
use std::sync::atomic::{AtomicU64, Ordering};
use url::Url;

static REQUEST: AtomicU64 = AtomicU64::new(0);

struct Cancel {
    id: String,
    armed: bool,
}

impl Drop for Cancel {
    fn drop(&mut self) {
        if self.armed {
            if let Ok(runtime) = tokio::runtime::Handle::try_current() {
                let id = self.id.clone();
                runtime.spawn(async move {
                    if let Err(error) = call("cancel", json!({"request_id":id})).await {
                        tracing::warn!(%error, "OS chooser cancellation is not confirmed");
                    }
                });
            }
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u8,
    request_id: String,
    status: String,
    #[serde(default)]
    uri: Option<String>,
    #[serde(default)]
    error: Option<String>,
}

enum Progress {
    Pending,
    Cancelled,
    Selected(Url),
}

fn decode(id: &str, value: Value) -> Result<Progress, String> {
    let response: Reply = serde_json::from_value(value).map_err(|error| {
        cosmic_settings_provider_client::refused(format!("invalid OS chooser response: {error}"))
    })?;
    if response.version != 1 || response.request_id != id {
        return Err(cosmic_settings_provider_client::refused(
            "OS chooser returned a different request",
        ));
    }
    match (response.status.as_str(), response.uri, response.error) {
        ("pending", None, None) => Ok(Progress::Pending),
        ("cancelled", None, None) => Ok(Progress::Cancelled),
        ("selected", Some(uri), None) => {
            if uri.len() > 4096 {
                return Err(cosmic_settings_provider_client::refused(
                    "OS chooser URI exceeded its bound",
                ));
            }
            let uri = Url::parse(&uri)
                .map_err(|_| cosmic_settings_provider_client::refused("invalid OS chooser URI"))?;
            if uri.scheme() != "file"
                || !matches!(uri.host_str(), None | Some("localhost"))
                || uri.query().is_some()
                || uri.fragment().is_some()
                || uri.to_file_path().is_err()
            {
                return Err(cosmic_settings_provider_client::refused(
                    "OS chooser did not return a local file reference",
                ));
            }
            Ok(Progress::Selected(uri))
        }
        ("failed" | "cleanup_pending", None, error) => Err(
            cosmic_settings_provider_client::refused(error.unwrap_or_else(|| {
                "OS chooser retirement is not confirmed; close Settings before retrying".into()
            })),
        ),
        _ => Err(cosmic_settings_provider_client::refused(
            "OS chooser outcome is not confirmed",
        )),
    }
}

async fn call(action: &str, request: Value) -> Result<Value, String> {
    let input = serde_json::to_vec(&request).map_err(cosmic_settings_provider_client::refused)?;
    claw_os_sdk::cos_call_json_async_with_stdin_binary(
        "/usr/local/bin/yu",
        "file-picker",
        action,
        ["__gui-file-picker", action, "--request-stdin"],
        &input,
    )
    .await
    .map_err(cosmic_settings_provider_client::refused)
}

pub async fn open_file(title: String, modal: bool) -> Result<Option<Url>, String> {
    choose(title, modal, "file", None, None).await
}

pub async fn open_theme(title: String, modal: bool) -> Result<Option<Url>, String> {
    choose(title, modal, "file", None, Some("ron")).await
}

pub async fn open_folder(title: String, modal: bool) -> Result<Option<Url>, String> {
    choose(title, modal, "folder", None, None).await
}

pub async fn save_file(title: String, modal: bool, name: String) -> Result<Option<Url>, String> {
    if name.is_empty()
        || name.len() > 255
        || matches!(name.as_str(), "." | "..")
        || name.contains(['/', '\\'])
        || name.chars().any(char::is_control)
    {
        return Err(cosmic_settings_provider_client::refused(
            "save chooser requires one literal filename",
        ));
    }
    choose(title, modal, "save", Some(name), Some("ron")).await
}

async fn choose(
    title: String,
    modal: bool,
    mode: &str,
    name: Option<String>,
    filter: Option<&str>,
) -> Result<Option<Url>, String> {
    if title.len() > 256 || title.chars().any(char::is_control) {
        return Err(cosmic_settings_provider_client::refused(
            "file chooser title exceeds its contract",
        ));
    }
    let counter = REQUEST
        .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
            value.checked_add(1)
        })
        .map_err(|_| {
            cosmic_settings_provider_client::refused("restart Settings before another file choice")
        })?;
    let id = format!("{:016x}{counter:016x}", u64::from(std::process::id()));
    let mut cancel = Cancel {
        id: id.clone(),
        armed: true,
    };
    let mut request = json!({"request_id":id,"title":title,"modal":modal,"mode":mode});
    if let Some(name) = name {
        request["name"] = json!(name);
    }
    if let Some(filter) = filter {
        request["filter"] = json!(filter);
    }
    let mut response = call("open", request).await?;
    loop {
        match decode(&id, response)? {
            Progress::Cancelled => {
                cancel.armed = false;
                return Ok(None);
            }
            Progress::Selected(uri) => {
                cancel.armed = false;
                return Ok(Some(uri));
            }
            Progress::Pending => {}
        }
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
        response = call("status", json!({"request_id":id})).await?;
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/test/unit/file_dialog.rs"
    ));
}
