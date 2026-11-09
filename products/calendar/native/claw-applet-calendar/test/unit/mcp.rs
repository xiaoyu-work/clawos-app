use super::*;
use claw_os_sdk::mcp::{Frame, InMemoryTransport, Transport, in_memory_pair};
use std::{fs, os::unix::fs::PermissionsExt, path::PathBuf, sync::atomic::{AtomicUsize, Ordering}};

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let root = PathBuf::from("test-fixtures").join(format!("calendar-{}-{}",
            std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir_all(&root).unwrap();
        let root = root.canonicalize().unwrap();
        fs::write(root.join("cos"), r#"#!/usr/bin/python3
import json, sys
from pathlib import Path
root = Path(__file__).parent
control = json.loads((root / "response.json").read_text())
assert sys.argv[1:] == ["--wire=1", "__calendar", "day", "2032", "2", "29"], sys.argv
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps(sys.argv[1:]) + "\n")
print(json.dumps(control["response"]))
sys.exit(control["status"])
"#).unwrap();
        fs::set_permissions(root.join("cos"), fs::Permissions::from_mode(0o700)).unwrap();
        Self(root)
    }

    fn respond(&self, data: Value) {
        fs::write(self.0.join("response.json"), json!({
            "response": {"wire_version": 1, "ok": true, "data": data}, "status": 0,
        }).to_string()).unwrap();
    }

    fn deny(&self) {
        fs::write(self.0.join("response.json"), json!({
            "response": {"wire_version": 1, "ok": false, "error": "synthetic Calendar access denied",
                "code": "PERMISSION_DENIED"}, "status": 1,
        }).to_string()).unwrap();
    }

    fn client(&self) -> Client { Client::with_binary(self.0.join("cos")) }

    fn calls(&self) -> usize {
        fs::read_to_string(self.0.join("calls.jsonl")).unwrap_or_default().lines().count()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
        let _ = fs::remove_dir("test-fixtures");
    }
}

async fn request(client: &InMemoryTransport, id: u64, date: &str, deadline: Option<u64>) -> Value {
    let mut context = json!({
        "wire_version": 1, "call_id": format!("calendar-{id}"), "trace_id": "synthetic-trace",
        "session_id": "synthetic-session",
        "caller": {"kind": "system-agent", "id": "synthetic-agent", "owner_uid": 1000}
    });
    if let Some(deadline) = deadline {
        context["deadline_unix_ms"] = json!(deadline);
    }
    client.send(json!({
        "jsonrpc": "2.0", "id": id, "method": "tools/call",
        "params": {"name": "panel-calendar.day", "arguments": {"date": date},
            "_meta": {"claw-os.dev/call-context": context}
        }
    }).to_string()).await.unwrap();
    let frame = tokio::time::timeout(std::time::Duration::from_secs(5), client.recv())
        .await.unwrap().unwrap().unwrap();
    let Frame::Message(frame) = frame else { panic!("expected MCP message") };
    serde_json::from_str(&frame).unwrap()
}

#[tokio::test]
async fn declared_day_uses_calendar_wire_and_preserves_denial_and_invalid_data() {
    let fixture = Fixture::new();
    fixture.respond(json!({"events": [{
        "id": "event-1", "title": "Synthetic review", "start": "2032-02-29T09:00:00Z",
        "end": null, "location": "Fixture room"
    }]}));
    let app = App::from_manifest(concat!(env!("CARGO_MANIFEST_DIR"), "/app.json")).unwrap();
    let (client, server) = in_memory_pair();
    let serving = tokio::spawn(bind(app, fixture.client()).unwrap().serve(server));
    let value = request(&client, 1, "2032-02-29", None).await;
    assert_eq!(value["result"]["isError"], false, "{value}");
    assert_eq!(value["result"]["structuredContent"]["date"], "2032-02-29");
    assert_eq!(value["result"]["structuredContent"]["events"][0]["location"], "Fixture room");
    assert_eq!(fixture.calls(), 1);

    for (id, day) in [(2, "2031-02-29"), (3, "2032-02-29T09:00:00Z")] {
        assert_eq!(request(&client, id, day, None).await["result"]["isError"], true);
    }
    assert_eq!(request(&client, 4, "2032-02-29", Some(1)).await["result"]["isError"], true);
    assert_eq!(fixture.calls(), 1, "invalid and expired calls must not reach a service");

    fixture.deny();
    let denied = request(&client, 5, "2032-02-29", None).await;
    assert_eq!(denied["result"]["isError"], true);
    assert!(denied["result"]["content"][0]["text"].as_str().unwrap().contains("denied"));
    fixture.respond(json!({"events": [{"id": "missing-required-fields"}]}));
    assert_eq!(request(&client, 6, "2032-02-29", None).await["result"]["isError"], true);
    fixture.respond(json!({"events": []}));
    assert_eq!(request(&client, 7, "2032-02-29", None).await["result"]["structuredContent"]["events"], json!([]));
    drop(client);
    serving.await.unwrap().unwrap();
}

#[test]
fn another_manifest_identity_cannot_bind_the_panel_service() {
    let fixture = Fixture::new();
    let mut manifest: Value = serde_json::from_str(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/app.json"))).unwrap();
    manifest["id"] = json!("calendar");
    fs::write(fixture.0.join("other.json"), manifest.to_string()).unwrap();
    assert!(matches!(bind(App::from_manifest(fixture.0.join("other.json")).unwrap(), fixture.client()),
        Err(AppError::Manifest(_))));
}
