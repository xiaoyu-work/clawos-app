//! Private, compiled-in Files business libraries; OS Python supplies authority.

use std::io::{self, Write};
use std::process::{Command, Stdio};

use serde_json::{Value, json};

const FS: &str = include_str!("../../fs_backend.py");
const RECOLL: &str = include_str!("../../recoll_backend.py");
const DOCUMENT: &str = include_str!("../../document_backend.py");
const BRIDGE: &str = include_str!("../../product_bridge.py");

fn command() -> Command {
    let sources = serde_json::to_string(&[
        ("fs", FS), ("recoll", RECOLL), ("document", DOCUMENT),
    ]).expect("serialize embedded sources");
    let bridge = serde_json::to_string(BRIDGE).expect("serialize embedded bridge");
    let mut command = Command::new("/usr/bin/python3");
    command.args(["-I", "-c", &format!(
        "import sys,os,types,json\n\
         sys.path[:0] = ['/usr/lib/cos/python']\n\
         os.environ['COS_BIN'] = '/usr/local/bin/cos'\n\
         os.environ['CLAW_COS_BIN'] = '/usr/local/bin/cos'\n\
         request = json.load(sys.stdin)\n\
         needed = {{'document':'document', 'recoll':'recoll', 'remember':None}}.get(request['operation'], 'fs')\n\
         for name,source in {sources}:\n\
         \x20if name != needed: continue\n\
         \x20module = types.ModuleType(name)\n\
         \x20module.__file__ = '/usr/lib/cos/apps/cosmic-files/embedded.py'\n\
         \x20exec(compile(source, '<files-' + name + '>', 'exec'), module.__dict__)\n\
         \x20globals()[name] = module\n\
         exec(compile({bridge}, '<files-bridge>', 'exec'))\n"
    )]);
    command
}

pub fn call(operation: &str, arguments: Value) -> io::Result<Value> {
    let request = serde_json::to_vec(&json!({
        "operation": operation, "arguments": arguments,
    }))?;
    let mut child = command()
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn()?;
    child.stdin.take().expect("piped input").write_all(&request)?;
    let output = child.wait_with_output()?;
    let value: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        io::Error::other(format!(
            "Files business helper: {error}: {}", String::from_utf8_lossy(&output.stderr),
        ))
    })?;
    if !output.status.success() || value.get("error").is_some() {
        let kind = if value["denied"] == true {
            io::ErrorKind::PermissionDenied
        } else {
            io::ErrorKind::Other
        };
        return Err(io::Error::new(kind, value["error"].as_str().unwrap_or("Files helper failed")));
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/claw_glue/product.rs"));
}
