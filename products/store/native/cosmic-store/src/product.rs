//! Compiled-in Store queries and fixed OS desktop activation.

use std::io::{self, Write};
use std::process::{Command, Stdio};
use serde_json::{Value, json};

const BACKEND: &str = include_str!("../catalog_backend.py");
const BRIDGE: &str = include_str!("../product_bridge.py");

pub fn query(operation: &str, arguments: Value) -> io::Result<Value> {
    let backend = serde_json::to_string(BACKEND)?;
    let bridge = serde_json::to_string(BRIDGE)?;
    let mut child = Command::new("/usr/bin/python3")
        .args(["-I", "-c", &format!(
            "import sys,os,json,types\n\
             sys.path[:0] = ['/usr/lib/cos/python', '/usr/lib/cos/apps']\n\
             os.environ['COS_BIN'] = '/usr/local/bin/cos'\n\
             os.environ['CLAW_COS_BIN'] = '/usr/local/bin/cos'\n\
             backend = types.ModuleType('store_catalog')\n\
             backend.__file__ = '/usr/lib/cos/apps/cosmic-store/embedded.py'\n\
             exec(compile({backend}, '<store-catalog>', 'exec'), backend.__dict__)\n\
             exec(compile({bridge}, '<store-bridge>', 'exec'))\n"
        )])
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn()?;
    let request = serde_json::to_vec(&json!({"operation": operation, "arguments": arguments}))?;
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
        io::Error::other(format!("Store helper: {error}: {}", String::from_utf8_lossy(&output.stderr)))
    })?;
    if !output.status.success() {
        return Err(io::Error::other(value["error"].as_str().unwrap_or("Store helper failed")));
    }
    written?;
    Ok(value)
}

pub fn open(name: Option<&str>) -> Result<(), cos_runtime::BridgeError> {
    let mut args = vec![
        "__desktop".to_string(), "launch".into(), "--app-id".into(), "com.clawos.Store".into(),
    ];
    if let Some(name) = name {
        if !valid_package_name(name) {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid package name").into());
        }
        args.extend(["--uri".into(), format!("apt://{name}")]);
    }
    let value = claw_os_sdk::cos_call_json("desktop", "launch", args)?;
    if value["launched"] != true || value["app_id"] != "com.clawos.Store"
        || value["launcher"] != "/usr/bin/cosmic-store"
    {
        return Err(cos_runtime::BridgeError::Decode {
            app: "desktop".into(), verb: "launch".into(),
            message: "provider did not confirm native Store launch".into(),
        });
    }
    Ok(())
}

pub fn valid_package_name(name: &str) -> bool {
    name.len() <= 255 && regex::Regex::new(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$")
        .expect("static package pattern").is_match(name)
}

#[cfg(test)]
mod tests {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/product.rs"));
}
