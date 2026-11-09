use std::{fs::File, io::{Read, Write}, process::{Command, Stdio}};

#[test]
fn actual_standalone_elf_runs_without_shell_or_desktop_transports() {
    let binary = env!("CARGO_BIN_EXE_claw-applet-widget-rail");
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
        format!("claw-applet-widget-rail {}\n", env!("CARGO_PKG_VERSION"))
    );
}

#[test]
fn actual_binary_dispatches_only_manifest_read_tools_before_gui_initialization() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_claw-applet-widget-rail"))
        .arg("--version")
        .env_clear()
        .env("COS_MCP_SERVER", "1")
        .env("COS_APP_MANIFEST", concat!(env!("CARGO_MANIFEST_DIR"), "/app.json"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().unwrap();
    child.stdin.take().unwrap().write_all(concat!(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"fixture\",\"version\":\"1\"}}}\n",
        "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\",\"params\":{}}\n"
    ).as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success(), "{:?}", output.stderr);
    let responses: Vec<serde_json::Value> = String::from_utf8(output.stdout).unwrap().lines()
        .map(|line| serde_json::from_str(line).unwrap()).collect();
    let listed = responses.iter().find(|value| value["id"] == 2).unwrap();
    let names: Vec<_> = listed["result"]["tools"].as_array().unwrap().iter()
        .map(|tool| tool["name"].as_str().unwrap()).collect();
    assert_eq!(names, ["widget-rail.calendar", "widget-rail.tasks", "widget-rail.system"]);
}
