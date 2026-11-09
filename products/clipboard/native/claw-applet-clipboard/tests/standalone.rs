use std::{
    fs::File,
    io::{BufRead, BufReader, Read, Write},
    process::{Command, Stdio},
};

#[test]
fn actual_standalone_elf_runs_without_shell_or_desktop_transports() {
    let binary = env!("CARGO_BIN_EXE_claw-applet-clipboard");
    let mut magic = [0_u8; 4];
    File::open(binary).unwrap().read_exact(&mut magic).unwrap();
    assert_eq!(&magic, b"\x7fELF");
    let result = Command::new(binary)
        .arg("--version")
        .env_clear()
        .output()
        .unwrap();
    assert!(result.status.success(), "{:?}", result.stderr);
    assert_eq!(
        String::from_utf8(result.stdout).unwrap(),
        format!("claw-applet-clipboard {}\n", env!("CARGO_PKG_VERSION"))
    );
}

#[test]
fn actual_native_mcp_is_manifest_bound_and_precedes_gui_and_version_modes() {
    let binary = env!("CARGO_BIN_EXE_claw-applet-clipboard");
    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../products/clipboard/apps/panel-clipboard/app.json");
    // Prepared native builds retain the source manifest as a declared asset.
    let manifest = if manifest.exists() {
        manifest
    } else {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("app.json")
    };
    let mut process = Command::new(binary)
        .arg("--version")
        .env_clear()
        .env("COS_MCP_SERVER", "1")
        .env("COS_APP_MANIFEST", &manifest)
        .env("COS_APP_ID", "panel-clipboard")
        .env("COS_SESSION", "synthetic-session")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = process.stdin.take().unwrap();
    let mut output = BufReader::new(process.stdout.take().unwrap());
    let mut call = |value: serde_json::Value| {
        writeln!(input, "{value}").unwrap();
        input.flush().unwrap();
        let mut line = String::new();
        output.read_line(&mut line).unwrap();
        serde_json::from_str::<serde_json::Value>(&line).unwrap()
    };
    let initialized = call(
        serde_json::json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"clipboard-fixture","version":"1"}}}),
    );
    assert_eq!(
        initialized["result"]["serverInfo"]["name"],
        "panel-clipboard"
    );
    let listed =
        call(serde_json::json!({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}));
    let names = listed["result"]["tools"]
        .as_array()
        .unwrap()
        .iter()
        .map(|tool| tool["name"].as_str().unwrap())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(
        names,
        [
            "history.clear",
            "history.list",
            "history.remove",
            "history.restore"
        ]
        .into_iter()
        .collect()
    );
    let invalid = call(
        serde_json::json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
        "name":"history.clear","arguments":{"confirm":false},"_meta":{"claw-os.dev/call-context":{
            "wire_version":1,"call_id":"clipboard-invalid","trace_id":"clipboard-fixture",
            "session_id":"synthetic-metadata-not-broker-authority",
            "caller":{"kind":"system-agent","id":"synthetic-fixture","owner_uid":1000}}}}}),
    );
    assert!(invalid.get("error").is_some() || invalid["result"]["isError"] == true);
    drop(call);
    drop(input);
    assert!(process.wait().unwrap().success());
}
