from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from claw_os_sdk import kernel
from test_support import authenticated_mcp_params, load_local_module


APP = Path(__file__).parent
PRODUCT = APP.parents[1]
ROOT = PRODUCT.parents[1]
SENT = {"id": "notif-" + "a" * 32, "message": "New", "urgent": False, "timestamp": "2026-01-01T00:00:00"}


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(APP))
    monkeypatch.setenv("COS_APP_MANIFEST", str(APP / "app.json"))
    client = load_local_module(APP / "client.py", "client", clear_modules=("client", "main"))
    main = load_local_module(APP / "main.py", "main")
    server = load_local_module(APP / "server.py", "notify_test_server")
    responses = []
    monkeypatch.setattr(server.app, "_send_result", lambda ident, value: responses.append({"result": value}))
    monkeypatch.setattr(server.app, "_send_error",
                        lambda ident, code, message, data=None: responses.append({"error": {"code": code, "message": message}}))

    def call(tool, args, *, context=None, authenticated=True):
        params = {"name": tool, "arguments": args}
        if authenticated:
            params = authenticated_mcp_params(params)
            if context:
                params["_meta"]["claw-os.dev/call-context"].update(context)
        server.app._handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}))
        return responses.pop()

    return SimpleNamespace(client=client, main=main, server=server, call=call)


def test_manifest_preserves_aliases_bindings_scopes_and_declares_the_history_change():
    manifest = json.loads((APP / "app.json").read_text())
    assert (manifest["id"], manifest["version"], manifest["runtime"]) == ("notify", "0.2.0", "python")
    assert "operations" not in manifest
    assert manifest["mcp"]["entry"] == "server.py"
    assert manifest["mcp"]["access"] == {"system_agent": True}
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"notify.send", "notify.list"}
    for tool, verb in [("notify.send", "ui.notify"), ("notify.list", "data.inbox.read")]:
        assert tools[tool]["needs"] == [{
            "verb": verb, "scope": {"kind": "wild"}, "why": tools[tool]["needs"][0]["why"],
        }]
        assert tools[tool]["needs"][0]["why"]["en"]
        assert "JSON" in tools[tool]["summary"]["en"]
    send_args = {arg["name"]: arg for arg in tools["notify.send"]["args"]}
    assert send_args["message"]["binding"] == "positional"
    assert send_args["urgent"]["binding"] == "flag"
    assert send_args["urgent"]["default"] is False
    assert tools["notify.list"]["args"][0]["binding"] == "flag"
    assert tools["notify.list"]["args"][0]["default"] == 20


@pytest.mark.parametrize("tool,args,intent", [
    ("notify.send", {"message": "New"}, {"action": "send", "message": "New", "urgent": False}),
    ("notify.send", {"message": "界\n\r\t🌍", "urgent": True},
     {"action": "send", "message": "界\n\r\t🌍", "urgent": True}),
    ("notify.send", {"message": "😀" * 4000}, {"action": "send", "message": "😀" * 4000, "urgent": False}),
    ("notify.list", {}, {"action": "list", "limit": 20}),
    ("notify.list", {"limit": 1}, {"action": "list", "limit": 1}),
    ("notify.list", {"limit": 100}, {"action": "list", "limit": 100}),
])
def test_actual_manifest_dispatch_uses_fixed_sdk_transport_not_caller_metadata(
    modules, monkeypatch, tool, args, intent,
):
    transport = Mock(return_value=SENT)
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    deadline = time.time_ns() // 1_000_000 + 1000
    before = dict(os.environ)
    response = modules.call(tool, args, context={
        "deadline_unix_ms": deadline, "session_id": "not-authority", "task_id": "not-authority",
        "caller": {"kind": "system-agent", "id": "untrusted-label", "owner_uid": 12345},
    })
    assert response["result"]["structuredContent"] == SENT
    assert response["result"].get("isError", False) is False
    binary, argv, data = transport.call_args.args
    assert binary == "/usr/local/bin/cos"
    assert argv == ["__notifications", "request", "--request-stdin", "--deadline", str(deadline)]
    assert json.loads(data) == intent
    assert transport.call_args.kwargs["deadline_unix_ms"] == deadline
    transport.call_args.kwargs["check_cancelled"]()
    assert dict(os.environ) == before


@pytest.mark.parametrize("tool,args", [
    ("notify.send", {"message": None}), ("notify.send", {"message": 1}),
    ("notify.send", {"message": " \n\t"}), ("notify.send", {"message": "x" * 4001}),
    ("notify.send", {"message": "x\x00"}), ("notify.send", {"message": "x\x7f"}),
    ("notify.send", {"message": "x\u0085"}), ("notify.send", {"message": "\ud800"}),
    ("notify.send", {"message": "Hi", "urgent": 1}),
    ("notify.send", {"message": "Hi", "urgent": "true"}),
    ("notify.list", {"limit": True}), ("notify.list", {"limit": "20"}),
    ("notify.list", {"limit": 0}), ("notify.list", {"limit": 101}),
    ("notify.list", {"limit": 1.5}),
])
def test_validation_precedes_broker_authority_and_effects(modules, monkeypatch, tool, args):
    transport = Mock()
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    result = modules.call(tool, args)
    assert "error" in result or result["result"]["isError"] is True
    transport.assert_not_called()


@pytest.mark.parametrize("field", [
    "owner_uid", "source", "app_name", "session", "session_id", "task_id", "confirm",
    "id", "icon", "dedupe_key",
])
@pytest.mark.parametrize("tool,args", [("notify.send", {"message": "Hi"}), ("notify.list", {})])
def test_forged_or_unknown_business_fields_never_reach_the_broker(modules, monkeypatch, field, tool, args):
    transport = Mock()
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    result = modules.call(tool, {**args, field: "forged"})
    assert result["result"]["isError"] is True
    transport.assert_not_called()


def test_missing_context_and_expired_deadlines_do_not_launch(modules, monkeypatch):
    transport = Mock()
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    assert "error" in modules.call("notify.list", {}, authenticated=False)
    result = modules.call("notify.send", {"message": "Too late"}, context={"deadline_unix_ms": 1})
    assert result["result"]["isError"] is True
    transport.assert_not_called()


@pytest.mark.parametrize("error,code", [
    (kernel.KernelDenied({"wire_version": 1, "ok": False, "code": "authorization-denied",
                          "error": "No grant"}), "authorization-denied"),
    (kernel.KernelDenied({"wire_version": 1, "ok": False, "code": "service-unavailable",
                          "error": "Storage unavailable"}), "service-unavailable"),
    (kernel.KernelUnavailable("No service"), "unavailable"),
])
def test_classified_errors_are_mcp_errors_not_success_or_retry(modules, monkeypatch, error, code):
    transport = Mock(side_effect=error)
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    result = modules.call("notify.list", {})
    assert result["result"]["isError"] is True
    assert result["result"]["structuredContent"]["code"] == code
    transport.assert_called_once()


@pytest.mark.parametrize("old", [
    b"{", b"\xff\x00", b'{"old-schema":"not a list"}', b'[1,null,"old"]',
    b'[{"id":"12345678","message":"Never replay","urgent":true,"read":false}]',
])
@pytest.mark.parametrize("unavailable", [False, True])
def test_historical_json_is_never_opened_mutated_moved_or_replayed(
    modules, monkeypatch, tmp_path, old, unavailable,
):
    history = tmp_path / "notifications.json"
    history.write_bytes(old)
    history.chmod(0o400)
    monkeypatch.setenv("COS_DATA_DIR", str(tmp_path))
    before = history.stat()
    originals = [(builtins, builtins.open), (io, io.open)]
    for module, original in originals:
        def guarded(path, *args, original=original, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                assert not os.fsdecode(path).endswith(("notifications.json", "notifications.json.lock"))
            return original(path, *args, **kwargs)
        monkeypatch.setattr(module, "open", guarded)
    transport = Mock(side_effect=kernel.KernelUnavailable("unavailable")) if unavailable else Mock(
        return_value={"notifications": [], "total": 0})
    monkeypatch.setattr(kernel, "call_json_with_stdin_binary", transport)
    for tool, arguments in [("notify.send", {"message": "Only new"}), ("notify.list", {})]:
        result = modules.call(tool, arguments)
        assert result["result"].get("isError", False) is unavailable
    assert transport.call_count == 2
    assert {json.loads(call.args[2])["action"] for call in transport.call_args_list} == {"send", "list"}
    after = history.stat()
    for field in ["st_ino", "st_uid", "st_gid", "st_mode", "st_mtime_ns", "st_atime_ns", "st_size"]:
        assert getattr(after, field) == getattr(before, field), field
    assert list(tmp_path.iterdir()) == [history]
    with originals[0][1](history, "rb") as stream:
        assert stream.read() == old


def test_staged_facade_is_complete_and_does_not_package_an_os_provider(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "notify_stage")
    assert stage.stage("notifications", tmp_path, ["notify"]) == ["notify"]
    installed = tmp_path / "usr/lib/cos/apps/notify"
    assert {path.name for path in installed.iterdir()} == {"app.json", "server.py", "main.py", "client.py"}
    for name in ("app.json", "server.py", "main.py", "client.py"):
        assert (installed / name).read_bytes() == (APP / name).read_bytes()
        assert (installed / name).stat().st_mode & 0o777 == 0o644
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var").exists()
    for filename in ("main.py", "server.py", "client.py"):
        source = (APP / filename).read_text()
        for forbidden in ("notifications.json", "COS_DATA_DIR", "sqlite", "subprocess", "Connection::session", "cos app"):
            assert forbidden not in source
