//! UI mutations share Files business logic and OS policy/snapshot services.

pub mod ai;
pub(crate) mod product;

use std::io;
use std::path::Path;

use cos_runtime::ask_claw;
use serde::Serialize;
use serde_json::json;

fn path_str(path: &Path) -> io::Result<&str> {
    path.to_str().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidInput, "file path must be UTF-8")
    })
}

pub fn write_bytes(path: &Path, content: &[u8]) -> io::Result<()> {
    product::call("write_bytes", json!({"path": path_str(path)?, "content": content})).map(|_| ())
}

pub fn write_text(path: &Path, content: &str) -> io::Result<()> {
    product::call("write", json!({"path": path_str(path)?, "content": content})).map(|_| ())
}

pub fn mkdir_all(path: &Path) -> io::Result<()> {
    product::call("mkdir", json!({"path": path_str(path)?})).map(|_| ())
}

pub fn remove(path: &Path) -> io::Result<()> {
    product::call("rm", json!({"path": path_str(path)?})).map(|_| ())
}

/// Activate only this product's fixed desktop target, never an App operation.
pub fn reveal(path: &Path) -> Result<String, String> {
    let path = std::fs::canonicalize(path).map_err(|error| error.to_string())?;
    let uri = url::Url::from_file_path(&path).map_err(|_| "invalid local path")?;
    let value = claw_os_sdk::cos_call_json("desktop", "launch", [
        "__desktop", "launch", "--app-id", "com.clawos.Files", "--uri", uri.as_str(),
    ]).map_err(|error| error.to_string())?;
    if value["launched"] != true || value["app_id"] != "com.clawos.Files"
        || value["launcher"] != "/usr/bin/gtk4-launch"
    {
        return Err("desktop provider did not confirm the Files target".into());
    }
    value["directory"].as_str().map(str::to_string)
        .ok_or_else(|| "desktop provider did not report the revealed directory".into())
}

#[derive(Serialize)]
struct FilesContext<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    cwd: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    selection: Option<&'a str>,
}

impl ask_claw::Context for FilesContext<'_> {
    const APP_ID: &'static str = "cosmic-files";
}

pub fn ask_claw(cwd: Option<&str>, selection: Option<&str>) -> Result<(), ask_claw::LaunchError> {
    ask_claw::launch(&FilesContext { cwd, selection })
}
