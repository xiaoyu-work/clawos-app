//! Terminal's compiled-in command library and controlled OS service adapters.

use std::io::{self, Write};
use std::path::Path;
use std::process::{Command, Stdio};

use serde_json::{Value, json};

const BACKEND: &str = include_str!("../exec_backend.py");
const BRIDGE: &str = include_str!("../product_bridge.py");

pub fn command(operation: &str, arguments: Value) -> io::Result<Value> {
    let backend = serde_json::to_string(BACKEND)?;
    let bridge = serde_json::to_string(BRIDGE)?;
    let mut child = Command::new("/usr/bin/python3")
        .args(["-I", "-c", &format!(
            "import sys,os,json,types\n\
             sys.path[:0] = ['/usr/lib/cos/python', '/usr/lib/cos/apps']\n\
             os.environ['COS_BIN'] = '/usr/local/bin/cos'\n\
             os.environ['CLAW_COS_BIN'] = '/usr/local/bin/cos'\n\
             backend = types.ModuleType('terminal_commands')\n\
             backend.__file__ = '/usr/lib/cos/apps/cosmic-term/embedded.py'\n\
             exec(compile({backend}, '<terminal-commands>', 'exec'), backend.__dict__)\n\
             exec(compile({bridge}, '<terminal-bridge>', 'exec'))\n"
        )])
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn()?;
    let request = serde_json::to_vec(&json!({
        "operation": operation, "arguments": arguments,
    }))?;
    let input = child.stdin.take().expect("piped input");
    let (output, written) = std::thread::scope(|scope| {
        let writer = scope.spawn(move || {
            let mut input = input;
            input.write_all(&request)
        });
        let output = child.wait_with_output();
        let written = writer.join().unwrap_or_else(|_| Err(io::Error::other("input writer panicked")));
        (output, written)
    });
    let output = output?;
    let value: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        io::Error::other(format!("Terminal helper: {error}: {}", String::from_utf8_lossy(&output.stderr)))
    })?;
    if !output.status.success() {
        return Err(io::Error::other(value["error"].as_str().unwrap_or("Terminal helper failed")));
    }
    written?;
    Ok(value)
}

pub fn open(cwd: Option<&str>) -> Result<(), cos_runtime::BridgeError> {
    let mut args = vec![
        "__desktop".to_string(), "launch".into(), "--app-id".into(), "com.clawos.Term".into(),
    ];
    if let Some(cwd) = cwd {
        if cwd.is_empty() || cwd.contains('\0') || !Path::new(cwd).is_absolute() {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "cwd must be an absolute path").into());
        }
        let trimmed = cwd.trim_end_matches('/');
        let uri = url::Url::from_file_path(if trimmed.is_empty() { "/" } else { trimmed }).map_err(|_| {
            io::Error::new(io::ErrorKind::InvalidInput, "invalid working directory")
        })?;
        args.extend(["--uri".into(), uri.to_string()]);
    }
    let value = claw_os_sdk::cos_call_json("desktop", "launch", args)?;
    if value["launched"] != true || value["app_id"] != "com.clawos.Term"
        || value["launcher"] != "/usr/bin/cosmic-term"
    {
        return Err(cos_runtime::BridgeError::Decode {
            app: "desktop".into(), verb: "launch".into(),
            message: "provider did not confirm native Terminal launch".into(),
        });
    }
    Ok(())
}

/// Human UI state writes retain policy checks and broker-owned snapshots.
pub mod files {
    use super::*;

    fn ui_only() -> io::Result<()> {
        if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
            return Err(io::Error::new(io::ErrorKind::PermissionDenied, "UI writes are unavailable in MCP"));
        }

        Ok(())
    }

    pub fn mkdir(path: impl AsRef<str>) -> Result<(), cos_runtime::BridgeError> {
        ui_only()?;
        let path = std::path::absolute(path.as_ref())?;
        cos_runtime::policy::require(
            "fs.write", cos_runtime::policy::Scope::path(path.to_string_lossy()),
        ).map_err(io::Error::other)?;
        std::fs::create_dir_all(path)?;
        Ok(())
    }

    pub fn write(path: impl AsRef<str>, content: &str) -> Result<(), cos_runtime::BridgeError> {
        ui_only()?;
        let path = path.as_ref();
        let parent = Path::new(path).parent().filter(|parent| !parent.as_os_str().is_empty());
        if let Some(parent) = parent {
            if !parent.exists() {
                mkdir(parent.to_string_lossy())?;
            }
        }
        cos_runtime::filesystem::write(path, content).map(|_| ())
    }
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/product.rs"));
}
