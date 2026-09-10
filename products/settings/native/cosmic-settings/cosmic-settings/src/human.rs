//! Compiled-in human Settings adapter; imports only installed OS libraries.

use std::io::{self, Write};
use std::process::{Command, Stdio};
use serde_json::{Value, json};

pub fn query(operation: &str, arguments: Value) -> io::Result<Value> {
    if std::env::var("COS_MCP_SERVER").as_deref() == Ok("1") {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "human Settings access is unavailable in MCP"));
    }
    let bridge = serde_json::to_string(include_str!("../../human_bridge.py"))?;
    let mut child = Command::new("/usr/bin/python3")
        .args(["-I", "-c", &format!(
            "import sys,os,json\n\
             sys.path[:0] = ['/usr/lib/cos/python']\n\
             os.environ['COS_BIN'] = '/usr/local/bin/cos'\n\
             os.environ['CLAW_COS_BIN'] = '/usr/local/bin/cos'\n\
             exec(compile({bridge}, '<settings-human>', 'exec'))\n"
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
        io::Error::other(format!("Settings helper: {error}: {}", String::from_utf8_lossy(&output.stderr)))
    })?;
    if !output.status.success() {
        let kind = if value["denied"] == true { io::ErrorKind::PermissionDenied } else { io::ErrorKind::Other };
        return Err(io::Error::new(kind, value["error"].as_str().unwrap_or("Settings helper failed")));
    }
    written?;
    Ok(value)
}
