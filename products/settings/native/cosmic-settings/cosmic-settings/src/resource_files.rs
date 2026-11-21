// SPDX-License-Identifier: GPL-3.0-only
//! Exact file authority remains in the OS, independently of chooser metadata.

use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;

async fn call(action: &str, request: Value) -> Result<Value, String> {
    let input = serde_json::to_vec(&request).map_err(cosmic_settings_provider_client::refused)?;
    claw_os_sdk::cos_call_json_async_with_stdin_binary(
        "/usr/local/bin/yu",
        "filesystem",
        action,
        ["__filesystem", action, "--request-stdin"],
        &input,
    )
    .await
    .map_err(cosmic_settings_provider_client::refused)
}

fn path(path: &Path) -> Result<&str, String> {
    path.to_str()
        .filter(|value| path.is_absolute() && !value.contains('\0'))
        .ok_or_else(|| {
            cosmic_settings_provider_client::refused("resource path must be absolute UTF-8")
        })
}

pub async fn read_text(source: &Path) -> Result<String, String> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Read {
        path: String,
        content: String,
    }
    let source = path(source)?;
    let value = call("read", json!({"action":"read","path":source})).await?;
    let result: Read =
        serde_json::from_value(value).map_err(cosmic_settings_provider_client::refused)?;
    if result.path != source {
        return Err(cosmic_settings_provider_client::refused(
            "OS file read returned a different resource",
        ));
    }
    Ok(result.content)
}

pub async fn write_text(target: &Path, content: &str) -> Result<(), String> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Written {
        path: String,
        bytes: u64,
    }
    let target = path(target)?;
    let value = call(
        "write",
        json!({"action":"write","path":target,"content":content}),
    )
    .await?;
    let result: Written =
        serde_json::from_value(value).map_err(cosmic_settings_provider_client::refused)?;
    if result.path != target || usize::try_from(result.bytes).ok() != Some(content.len()) {
        return Err(cosmic_settings_provider_client::refused(
            "OS file write did not confirm the requested resource and bytes",
        ));
    }
    Ok(())
}
