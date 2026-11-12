// SPDX-License-Identifier: GPL-3.0-only
//
// Thin sync adapter over `claw-os-sdk` for cosmic-edit.
//
// Each function turns a `BridgeError` into a plain `io::Error` so call
// sites can keep their `match … { Ok / Err(io::Error) }` shape. A
// kernel "denied" decision surfaces as `io::ErrorKind::PermissionDenied`;
// only OS-owned consent can authorize a retry.
//
// AI helpers (`summarize` / `explain` / `rewrite`) live in the [`ai`]
// submodule. They are `async` and return `Result<_, String>` because
// the MCP server and any future UI surface want a flat
// human-presentable error, not an `io::Error`.

pub mod ai;

use std::io;
use std::path::Path;

use cos_runtime::{BridgeError, ask_claw, desktop, filesystem};
use serde::Serialize;

#[derive(Clone, Debug, Hash, PartialEq, Eq)]
pub enum FileSelection {
    Existing(String, u64),
    Create(String, u64),
}

fn map_err(err: BridgeError) -> io::Error {
    let kind = if err.is_denied() {
        io::ErrorKind::PermissionDenied
    } else {
        io::ErrorKind::Other
    };
    io::Error::new(kind, err.to_string())
}

fn path_str(path: &Path) -> io::Result<&str> {
    path.to_str().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "path is not valid UTF-8 (claw-os-sdk requires UTF-8 paths)",
        )
    })
}

/// User-intent file read (reload tab from disk after an external change).
/// Managed GUI reads remain behind the selected native FUSE resource.
///
/// Hot-path reads (syntax highlighting, project tree population, etc.)
/// MUST keep using `std::fs` directly — those happen on every keystroke
/// and routing each one through a subprocess would tank the editor.
pub fn read_to_string(path: &Path) -> io::Result<String> {
    if claw_os_sdk::gui::is_gui_launch()
        && std::env::var("COS_MCP_SERVER").as_deref() != Ok("1")
    {
        return std::fs::read_to_string(path);
    }
    let p = path_str(path)?;
    filesystem::read(p).map(|r| r.content).map_err(map_err)
}

/// User-intent file save.
///
/// A denied save leaves the buffer unsaved; no privileged fallback is used.
pub fn write_text(path: &Path, contents: &str, selection: Option<&FileSelection>) -> io::Result<()> {
    if claw_os_sdk::gui::is_gui_launch()
        && std::env::var("COS_MCP_SERVER").as_deref() != Ok("1")
    {
        use std::io::Write;
        use std::os::unix::fs::MetadataExt;

        let selection = selection.ok_or_else(|| io::Error::new(
            io::ErrorKind::PermissionDenied, "this file needs a separate protected write selection",
        ))?;
        let (parent_node, name) = match selection {
            FileSelection::Existing(id, node) => {
                let reserved = claw_os_sdk::gui::reserve_file_save(id, *node).map_err(map_err)?;
                (reserved.parent_node, reserved.name)
            }
            FileSelection::Create(id, node) => {
                let reserved = claw_os_sdk::gui::reserve_file_create(id, *node).map_err(map_err)?;
                if path.file_name().and_then(|name| name.to_str()) != Some(reserved.target_name.as_str()) {
                    return Err(io::Error::new(io::ErrorKind::InvalidData, "creation reservation has another target"));
                }
                (reserved.parent_node, reserved.name)
            }
        };
        let parent = path.parent().ok_or_else(|| io::Error::new(
            io::ErrorKind::InvalidInput, "save target has no parent",
        ))?;
        if std::fs::symlink_metadata(parent)?.ino() != parent_node {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "save reservation has another parent"));
        }
        let scratch = parent.join(name);
        let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(&scratch)?;
        file.write_all(contents.as_bytes())?;
        file.sync_all()?;
        drop(file);
        std::fs::rename(scratch, path)?;
        std::fs::File::open(parent)?.sync_all()?;
        return Ok(());
    }
    let p = path_str(path)?;
    filesystem::write(p, contents).map(|_| ()).map_err(map_err)
}

/// Open another editor through the fixed OS desktop target.
pub fn new_window() -> io::Result<()> {
    desktop::open_editor(None).map_err(map_err)
}

#[derive(Serialize)]
struct EditContext<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    file: Option<&'a str>,
}

impl ask_claw::Context for EditContext<'_> {
    const APP_ID: &'static str = "cosmic-edit";
}

/// Open Ask Claw with the optional active document path.
pub fn ask_claw_overlay(file: Option<&Path>) -> Result<(), ask_claw::LaunchError> {
    let file = file.and_then(Path::to_str);
    ask_claw::launch(&EditContext { file })
}
