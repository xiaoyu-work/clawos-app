use super::*;
use claw_os_sdk::mcp::{Frame, InMemoryTransport, Transport, in_memory_pair};
use std::{fs, os::unix::fs::PermissionsExt, path::PathBuf, sync::atomic::{AtomicUsize, Ordering}};

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let root = PathBuf::from("test-fixtures").join(format!("widgets-{}-{}",
            std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir_all(&root).unwrap();
        let root = root.canonicalize().unwrap();
        fs::write(root.join("cos"), r#"#!/usr/bin/python3
import json, sys
from pathlib import Path
root = Path(__file__).parent
control = json.loads((root / "response.json").read_text())
assert sys.argv[1] == "--wire=1", sys.argv
args = sys.argv[2:]
if args[:2] == ["__calendar", "day"]:
    assert len(args) == 5
    source = "calendar"
elif args == ["__observe", "tasks"]:
    source = "tasks"
elif args == ["__observe", "resources"]:
    source = "system"
else:
    raise AssertionError("No App calls, mutations, models or other OS commands")
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps({"source": source, "args": args}) + "\n")
if source == control.get("deny"):
    print(json.dumps({"wire_version": 1, "ok": False, "error": "synthetic " + source + " denied",
        "code": "PERMISSION_DENIED"}))
    sys.exit(1)
print(json.dumps({"wire_version": 1, "ok": True, "data": control[source]}))
"#).unwrap();
        fs::set_permissions(root.join("cos"), fs::Permissions::from_mode(0o700)).unwrap();
        Self(root)
    }

    fn respond(&self, deny: Option<&str>) {
        fs::write(self.0.join("response.json"), json!({
            "deny": deny,
            "calendar": {"events": [{"id": "event", "title": "Synthetic review",
                "start": "2032-02-29T09:00:00Z", "end": null, "location": "Fixture room"}]},
            "tasks": {"tasks": [{"id": "task", "purpose": "Synthetic task", "status": "running",
                "created_at": "2032-02-29T08:00:00Z"}]},
            "system": {"summary": {"cpu_percent": null,
                "memory": {"used_mb": 10, "total_mb": 20},
                "storage": {"used_mb": 30, "total_mb": 100},
                "network_down_bps": null, "network_up_bps": null, "fallback": false}}
        }).to_string()).unwrap();
    }

    fn replace(&self, source: &str, data: Value) {
        let path = self.0.join("response.json");
        let mut control: Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        control[source] = data;
        fs::write(path, control.to_string()).unwrap();
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

async fn request(client: &InMemoryTransport, id: u64, source: &str, arguments: Value, deadline: Option<u64>) -> Value {
    let mut context = json!({
        "wire_version": 1, "call_id": format!("widgets-{id}"), "trace_id": "synthetic-trace",
        "session_id": "synthetic-session",
        "caller": {"kind": "system-agent", "id": "synthetic-agent", "owner_uid": 1000}
    });
    if let Some(deadline) = deadline {
        context["deadline_unix_ms"] = json!(deadline);
    }
    client.send(json!({
        "jsonrpc": "2.0", "id": id, "method": "tools/call",
        "params": {"name": format!("widget-rail.{source}"), "arguments": arguments,
            "_meta": {"claw-os.dev/call-context": context}
        }
    }).to_string()).await.unwrap();
    let frame = tokio::time::timeout(std::time::Duration::from_secs(5), client.recv())
        .await.unwrap().unwrap().unwrap();
    let Frame::Message(frame) = frame else { panic!("expected MCP message") };
    serde_json::from_str(&frame).unwrap()
}

#[tokio::test]
async fn each_declared_source_uses_only_its_read_command_and_keeps_failures_independent() {
    let fixture = Fixture::new();
    fixture.respond(None);
    let app = App::from_manifest(concat!(env!("CARGO_MANIFEST_DIR"), "/app.json")).unwrap();
    let (client, server) = in_memory_pair();
    let serving = tokio::spawn(bind(app, fixture.client()).unwrap().serve(server));
    let calendar = request(&client, 1, "calendar", json!({}), None).await;
    assert_eq!(calendar["result"]["isError"], false, "{calendar}");
    assert_eq!(calendar["result"]["structuredContent"]["events"][0]["id"], "event");
    let tasks = request(&client, 2, "tasks", json!({}), None).await;
    let task = &tasks["result"]["structuredContent"]["tasks"][0];
    assert_eq!(task["purpose"], "Synthetic task");
    assert!(task.get("lease").is_none(), "private task metadata is not a presentation result");
    let system = request(&client, 3, "system", json!({}), None).await;
    let summary = &system["result"]["structuredContent"]["summary"];
    assert_eq!(summary["memory"]["used_mb"], 10);
    assert_eq!(summary["storage"]["total_mb"], 100);
    assert!(summary["cpu_percent"].is_null());
    assert!(summary["network_down_bps"].is_null());
    assert!(summary["network_up_bps"].is_null());
    assert_eq!(summary["fallback"], false, "preserve the OS fallback flag");
    assert_eq!(fixture.calls(), 3);

    let sampled = json!({"cpu_percent": 42.5, "memory": {"used_mb": 11, "total_mb": 20},
        "storage": null, "network_down_bps": 123, "network_up_bps": 456, "fallback": true});
    fixture.replace("system", json!({"summary": sampled}));
    let system = request(&client, 4, "system", json!({}), None).await;
    assert_eq!(system["result"]["structuredContent"]["summary"], sampled);
    fixture.replace("system", json!({"memory": {"used_mb": 10, "total_mb": 20}}));
    assert_eq!(request(&client, 5, "system", json!({}), None).await["result"]["isError"], true,
        "the observer must return the typed summary wrapper");

    let invalid = request(&client, 6, "tasks", json!({"start": true}), None).await;
    assert_eq!(invalid["result"]["isError"], true, "{invalid}");
    assert_eq!(request(&client, 7, "tasks", json!({}), Some(1)).await["result"]["isError"], true);
    assert_eq!(fixture.calls(), 5);
    fixture.respond(Some("tasks"));
    let denied = request(&client, 8, "tasks", json!({}), None).await;
    assert_eq!(denied["result"]["isError"], true);
    assert!(denied["result"]["content"][0]["text"].as_str().unwrap().contains("denied"));
    assert_eq!(request(&client, 9, "calendar", json!({}), None).await["result"]["isError"], false);
    assert_eq!(request(&client, 10, "system", json!({}), None).await["result"]["isError"], false);
    fixture.respond(Some("system"));
    assert_eq!(request(&client, 11, "system", json!({}), None).await["result"]["isError"], true);
    assert_eq!(request(&client, 12, "tasks", json!({}), None).await["result"]["isError"], false);
    drop(client);
    serving.await.unwrap().unwrap();
}

#[test]
fn another_manifest_identity_cannot_bind_the_widget_service() {
    let fixture = Fixture::new();
    let mut manifest: Value = serde_json::from_str(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/app.json"))).unwrap();
    manifest["id"] = json!("panel-calendar");
    fs::write(fixture.0.join("other.json"), manifest.to_string()).unwrap();
    assert!(matches!(bind(App::from_manifest(fixture.0.join("other.json")).unwrap(), fixture.client()),
        Err(AppError::Manifest(_))));
}
