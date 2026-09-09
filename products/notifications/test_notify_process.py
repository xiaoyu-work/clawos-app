"""Installed Python MCP/SDK transport fixture; the real provider is tested in OS."""

import json
import os
from pathlib import Path
import selectors
import subprocess
import time

import claw_os_sdk

from test_support import authenticated_mcp_params, load_local_module

ROOT = Path(__file__).resolve().parents[2]
ID = "notif-" + "b" * 32

# Canned wire responses, not an OS provider or notification state implementation.
CLI = r'''#!/usr/bin/python3
import json, os, pathlib, sys, time
assert os.environ["COS_SESSION"] == "authenticated-worker-session"
assert "DBUS_SESSION_BUS_ADDRESS" not in os.environ
assert "CLAW_COS_BIN" not in os.environ
assert not pathlib.Path("/run/user").exists()
assert not pathlib.Path("/run/cos/clawd.sock").exists()
assert not pathlib.Path("/var/lib/cos").exists()
args = sys.argv[1:]
assert args[:5] == ["--wire=1", "__notifications", "request", "--request-stdin", "--deadline"]
assert len(args) == 6 and int(args[5]) > time.time() * 1000
request = json.load(sys.stdin)
with open("/signals/calls", "a") as trace:
    trace.write(json.dumps(request) + "\n")
assert set(request) == ({"action", "message", "urgent"} if request["action"] == "send" else {"action", "limit"})
if request.get("message") == "fixture-hang":
    time.sleep(30)
if request.get("message") in ("fixture-denied", "fixture-unavailable"):
    code = "not_authorized" if request["message"] == "fixture-denied" else "unavailable"
    print(json.dumps({"wire_version":1,"ok":False,"code":code,"error":"Fixture refusal"}))
    sys.exit(1)
row = {"id":"notif-" + "b"*32,"message":"Fixture OS row","urgent":False,"timestamp":"2026-01-01T00:00:00"}
if request["action"] == "send":
    row.update(message=request["message"], urgent=request["urgent"])
    result = row
else:
    assert request["action"] == "list"
    result = {"notifications":[dict(row,read=False,state="unread")],"total":101}
print(json.dumps({"wire_version":1,"ok":True,"data":result}))
'''


def response(process, ident):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(10), "installed Notify MCP timed out"
        line = process.stdout.readline()
        assert line, process.stderr.read().decode()
    result = json.loads(line)
    assert result["id"] == ident, result
    return result


def write(process, ident, method, params):
    message = {"jsonrpc": "2.0", "method": method, "params": params}
    if ident is not None:
        message["id"] = ident
    process.stdin.write(json.dumps(message).encode() + b"\n")
    process.stdin.flush()


def test_installed_notify_mcp_sdk_errors_cancellation_and_untouched_history(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "notify_process_stage")
    assert stage.stage("notifications", tmp_path / "installed", ["notify"]) == ["notify"]
    app = tmp_path / "installed/usr/lib/cos/apps/notify"
    data = tmp_path / "data"
    data.mkdir()
    history = data / "notifications.json"
    old = b'[{arbitrary old JSON, never read or replayed'
    history.write_bytes(old)
    history.chmod(0o400)
    before = history.stat()
    signals = tmp_path / "signals"
    signals.mkdir()
    cli = tmp_path / "cos-fixture"
    cli.write_text(CLI)
    cli.chmod(0o755)
    sdk = Path(claw_os_sdk.__file__).parent.parent
    command = [
        "bwrap", "--die-with-parent", "--unshare-all", "--clearenv",
        "--ro-bind", "/usr/bin", "/usr/bin", "--ro-bind", "/usr/lib", "/usr/lib",
        "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
        "--dir", "/usr/local/bin", "--proc", "/proc", "--dev", "/dev",
        "--ro-bind", str(cli), "/usr/local/bin/cos",
        "--ro-bind", str(app), "/app", "--ro-bind", str(sdk), "/sdk",
        "--bind", str(data), "/state", "--bind", str(signals), "/signals",
        "--setenv", "COS_APP_MANIFEST", "/app/app.json",
        "--setenv", "COS_APP_ID", "notify",
        "--setenv", "COS_SESSION", "authenticated-worker-session",
        "--setenv", "COS_DATA_DIR", "/state",
        "--setenv", "PYTHONPATH", "/sdk", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "HOME", "/state", "--setenv", "TMPDIR", "/state",
        "--chdir", "/app", "--", "/usr/bin/python3", "/app/server.py",
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def call(ident, tool, arguments):
        params = authenticated_mcp_params({"name": tool, "arguments": arguments}, call_id=f"call-{ident}")
        params["_meta"]["claw-os.dev/call-context"]["session_id"] = "forged-metadata-not-authority"
        write(process, ident, "tools/call", params)
        return response(process, ident)

    def count():
        path = signals / "calls"
        return len(path.read_text().splitlines()) if path.exists() else 0

    try:
        write(process, 1, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "notify-process-fixture", "version": "1"},
        })
        assert response(process, 1)["result"]["serverInfo"]["name"] == "notify"
        write(process, None, "notifications/initialized", {})
        sent = call(2, "notify.send", {"message": "New <b>text</b>", "urgent": True})["result"]
        assert sent.get("isError", False) is False
        assert sent["structuredContent"] == {
            "id": ID, "message": "New <b>text</b>", "urgent": True, "timestamp": "2026-01-01T00:00:00",
        }
        listed = call(3, "notify.list", {"limit": 1})["result"]["structuredContent"]
        assert listed["total"] == 101
        assert listed["notifications"][0]["read"] is False
        assert len(listed["notifications"]) == 1
        valid_count = count()
        for ident, tool, args in [
            (4, "notify.send", {"message": "Hi", "source": "app:cosmic-notifications"}),
            (5, "notify.list", {"limit": True}), (6, "notify.send", {"message": ""}),
        ]:
            assert call(ident, tool, args)["result"]["isError"] is True
        assert count() == valid_count
        for ident, message, code in [
            (7, "fixture-denied", "not_authorized"), (8, "fixture-unavailable", "unavailable"),
        ]:
            result = call(ident, "notify.send", {"message": message})["result"]
            assert result["isError"] is True
            assert result["structuredContent"]["code"] == code
        write(process, 9, "tools/call", authenticated_mcp_params({
            "name": "notify.send", "arguments": {"message": "fixture-hang"},
        }, call_id="cancel-fixture"))
        deadline = time.monotonic() + 5
        while count() < 5 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert count() == 5
        write(process, None, "notifications/cancelled", {"requestId": 9, "reason": "fixture"})
        start = time.monotonic()
        assert call(10, "notify.list", {})["result"]["structuredContent"]["total"] == 101
        assert time.monotonic() - start < 2, "cancelled CLI blocked the App service"
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    after = history.stat()
    for field in ("st_ino", "st_uid", "st_gid", "st_mode", "st_mtime_ns", "st_atime_ns", "st_size"):
        assert getattr(before, field) == getattr(after, field), field
    assert list(data.iterdir()) == [history]
    assert history.read_bytes() == old
