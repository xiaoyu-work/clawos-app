// SPDX-License-Identifier: GPL-3.0-only

use std::io;
use std::io::Read;
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::time::Duration;

pub(crate) async fn choose(title: String) -> Result<Option<url::Url>, String> {
    let mut random = [0;16];
    std::fs::File::open("/dev/urandom").and_then(|mut source|source.read_exact(&mut random))
        .map_err(|error|error.to_string())?;
    let id = random.iter().map(|byte|format!("{byte:02x}")).collect::<String>();
    let mut action = "open";
    loop {
        let params = if action == "open" {
            serde_json::json!({"request_id":id,"title":title,"modal":true})
        } else { serde_json::json!({"request_id":id}) };
        let response = tokio::task::spawn_blocking(move || {
            claw_os_sdk::cos_call_json_with_stdin("file-picker", action,
                ["__gui-file-picker", action, "--request-stdin"], params.to_string().as_bytes())
        }).await.map_err(|error|error.to_string())?.map_err(|error|error.to_string())?;
        if response["version"]!=1 || response["request_id"]!=id {
            return Err("OS file picker returned another request's result".into());
        }
        match response["status"].as_str() {
            Some("pending") => {
                action = "status";
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            Some("cancelled") => return Ok(None),
            Some("selected") => {
                let uri = response["uri"].as_str().ok_or("OS file picker omitted its metadata URI")?;
                let uri = url::Url::parse(uri).map_err(|error|error.to_string())?;
                let path = uri.to_file_path().map_err(|_|"OS file picker returned a non-local URI")?;
                if !path.is_absolute() { return Err("OS file picker returned a relative path".into()); }
                return Ok(Some(uri));
            }
            Some("failed") => return Err(response["error"].as_str().unwrap_or("OS file picker failed").into()),
            Some("cleanup_pending") => return Err("OS file picker cleanup is unconfirmed; do not replay".into()),
            _ => return Err("OS file picker returned an invalid state".into()),
        }
    }
}

fn node(path: &Path) -> Result<Option<u64>, String> {
    if !claw_os_sdk::gui::is_gui_launch() {
        return Ok(None);
    }
    let home = std::env::var_os("COS_OWNER_HOME")
        .ok_or("managed media requires its owner path context")?;
    let home = std::fs::symlink_metadata(home).map_err(|error| error.to_string())?;
    let file = std::fs::symlink_metadata(path).map_err(|error| error.to_string())?;
    // Only the Root metadata filesystem uses selection nodes; other paths still
    // have only the sandbox's existing public-resource or private-App access.
    Ok((file.dev() == home.dev()).then_some(file.ino()))
}

pub(crate) fn read(url: &url::Url) -> Result<(), String> {
    let Ok(path) = url.to_file_path() else {
        return Ok(());
    };
    let Some(node) = node(&path)? else {
        return Ok(());
    };
    let mut reply = claw_os_sdk::gui::request_file_read(node).map_err(|error| error.to_string())?;
    loop {
        if reply.node != node {
            return Err("media read selection changed its target".into());
        }
        match reply.state.as_str() {
            "selected" => return Ok(()),
            "pending" => std::thread::sleep(Duration::from_millis(250)),
            _ => return Err(reply.reason.unwrap_or(reply.state)),
        }
        reply = claw_os_sdk::gui::file_read_status(&reply.selection_id, node)
            .map_err(|error| error.to_string())?;
    }
}

pub(crate) fn save_png(
    image: &image::DynamicImage,
    output: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let parent = output.parent().ok_or("thumbnail target has no parent")?;
    let Some(parent_node) = node(parent)? else {
        image.save_with_format(output, image::ImageFormat::Png)?;
        return Ok(());
    };
    let target_name = output
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("thumbnail target requires one UTF-8 filename")?;
    let scratch = match std::fs::symlink_metadata(output) {
        Ok(metadata) => {
            let node = metadata.ino();
            let mut reply = claw_os_sdk::gui::request_file_write(node)?;
            loop {
                if reply.node != node {
                    return Err("thumbnail write selection changed its target".into());
                }
                match reply.state.as_str() {
                    "selected" => break,
                    "pending" => std::thread::sleep(Duration::from_millis(250)),
                    _ => return Err(reply.reason.unwrap_or(reply.state).into()),
                }
                reply = claw_os_sdk::gui::file_write_status(&reply.selection_id, node)?;
            }
            let slot = claw_os_sdk::gui::reserve_file_save(&reply.selection_id, node)?;
            if slot.parent_node != parent_node {
                return Err("thumbnail write reservation changed its parent".into());
            }
            parent.join(slot.name)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let mut reply = claw_os_sdk::gui::request_file_create(parent_node, target_name)?;
            loop {
                if reply.parent_node != parent_node || reply.name != target_name {
                    return Err("thumbnail creation selection changed its target".into());
                }
                match reply.state.as_str() {
                    "selected" => break,
                    "pending" => std::thread::sleep(Duration::from_millis(250)),
                    _ => return Err(reply.reason.unwrap_or(reply.state).into()),
                }
                reply = claw_os_sdk::gui::file_create_status(&reply.selection_id, parent_node)?;
            }
            let slot = claw_os_sdk::gui::reserve_file_create(&reply.selection_id, parent_node)?;
            if slot.parent_node != parent_node || slot.target_name != target_name {
                return Err("thumbnail creation reservation changed its target".into());
            }
            parent.join(slot.name)
        }
        Err(error) => return Err(error.into()),
    };
    commit_png(image, &scratch, output, parent)?;
    Ok(())
}

fn commit_png(
    image: &image::DynamicImage,
    scratch: &Path,
    output: &Path,
    parent: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(scratch)?;
    image.write_to(&mut file, image::ImageFormat::Png)?;
    file.sync_all()?;
    drop(file);
    std::fs::rename(scratch, output)?;
    std::fs::File::open(parent)?.sync_all()?;
    Ok(())
}
