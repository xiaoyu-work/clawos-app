//! Human Store UI adapters to OS policy, snapshots and Agent activation.
//! Native Flatpak/PackageKit transactions retain their original human policies.

use std::{io, path::Path};
use cos_runtime::{ask_claw, BridgeError, policy};
use serde::Serialize;

pub fn user_message(err: &BridgeError) -> String {
    if err.is_denied() {
        format!("This action requires permission ({err}). Ask the Agent to explain the request.")
    } else {
        err.to_string()
    }
}

fn human_ui() -> Result<(), BridgeError> {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "human UI access is unavailable in MCP").into());
    }
    Ok(())
}

pub fn read_bytes(path: &Path) -> Result<Vec<u8>, BridgeError> {
    human_ui()?;
    let path = std::path::absolute(path)?;
    policy::require("fs.read", policy::Scope::path(path.to_string_lossy()))
        .map_err(io::Error::other)?;
    Ok(std::fs::read(path)?)
}

pub fn fs_rm(path: &Path) -> Result<(), BridgeError> {
    human_ui()?;
    crate::product::query("remove_data", serde_json::json!({"path": path}))?;
    Ok(())
}

#[derive(Serialize)]
struct StoreViewContext<'a> {
    view: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    page: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    app_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<&'a str>,
}

impl ask_claw::Context for StoreViewContext<'_> {
    const APP_ID: &'static str = "cosmic-store";
}

#[derive(Serialize)]
struct StoreSearchContext<'a> {
    mode: &'static str,
    query: &'a str,
}

impl ask_claw::Context for StoreSearchContext<'_> {
    const APP_ID: &'static str = "cosmic-store";
}

pub fn ask_claw_home() -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&StoreViewContext { view: "home", page: None, app_id: None, name: None })
}

pub fn ask_claw_explore(page: &str) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&StoreViewContext { view: "explore", page: Some(page), app_id: None, name: None })
}

pub fn ask_claw_app(app_id: &str, name: &str) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&StoreViewContext { view: "app", page: None, app_id: Some(app_id), name: Some(name) })
}

pub fn ask_claw_search(query: &str) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&StoreSearchContext { mode: "search", query })
}
