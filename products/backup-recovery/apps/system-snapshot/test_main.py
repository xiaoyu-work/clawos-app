import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


APP_DIR = pathlib.Path(__file__).parent
main = load_local_module(
    APP_DIR / "main.py",
    "claw_test_system_snapshot_main",
    clear_modules=("_shared",),
)


SNAPSHOT_ID = "snap_" + "a" * 32


@pytest.mark.parametrize("confirm", [False, None, 0, 1, "true"])
def test_rollback_requires_confirmation_before_policy(confirm):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="rollback requires confirm=true"):
            main.rollback_snapshot(SNAPSHOT_ID, confirm)
    require.assert_not_called()


def test_invalid_snapshot_id_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="snapshot id must match"):
            main.delete_snapshot("snap_invalid")
    require.assert_not_called()


def test_create_uses_snapshot_capability():
    completed = mock.Mock(returncode=0, stdout=json.dumps({"created": {}}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = main.create_snapshot("before upgrade")
    require.assert_called_once_with("sys.snapshot", wild=True)
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__snapshot",
        "create",
        "before upgrade",
    ]
    assert result == {"created": {}}


def test_create_preserves_default_description():
    completed = mock.Mock(returncode=0, stdout=json.dumps({"created": {}}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        main.create_snapshot()
    assert run.call_args.args[0][-1] == "Claw OS recovery point"


def test_broker_error_payload_raises():
    completed = mock.Mock(
        returncode=1,
        stdout=json.dumps({"error": "snapshot creation failed"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match="snapshot creation failed"):
            main.create_snapshot()


def test_manifest_preserves_snapshot_scopes_and_rollback_confirmation():
    manifest = json.loads((APP_DIR / "app.json").read_text(encoding="utf-8"))
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {
        f"system-snapshot.{action}"
        for action in ("status", "list", "create", "delete", "rollback")
    }
    for action in ("status", "list", "create", "delete", "rollback"):
        needs = tools[f"system-snapshot.{action}"]["needs"]
        assert len(needs) == 1
        if action in ("status", "list"):
            assert needs[0]["verb"] == "sys.observe"
            assert needs[0]["scope"] == {
                "kind": "fixed",
                "scope": {"kind": "name", "value": "system-snapshots"},
            }
        else:
            assert needs[0]["verb"] == "sys.snapshot"
            assert needs[0]["scope"] == {"kind": "wild"}
    assert tools["system-snapshot.rollback"]["args"][-1] == {
        "name": "confirm", "kind": "bool", "required": True,
        "binding": "flag", "choices": [True],
    }


@pytest.mark.parametrize(("action", "arguments", "tail"), [
    ("status", {}, []),
    ("list", {}, []),
    ("create", {}, ["Claw OS recovery point"]),
    ("create", {"description": "before upgrade"}, ["before upgrade"]),
    ("delete", {"id": SNAPSHOT_ID}, [SNAPSHOT_ID]),
    ("rollback", {"id": SNAPSHOT_ID, "confirm": True}, [SNAPSHOT_ID, "--confirm"]),
])
def test_relocated_sdk_dispatch_preserves_broker_argv_and_scope(action, arguments, tail):
    completed = mock.Mock(returncode=0, stdout=json.dumps({"action": action}), stderr="")
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(APP_DIR / "app.json"), "COS_BIN": "/usr/local/bin/cos"}
    ):
        server = load_local_module(APP_DIR / "server.py", "claw_test_system_snapshot_server")
        listed = server.app._handle_request("tools/list", {}, True)
        assert len(listed["tools"]) == 5
        with mock.patch.object(main.policy, "require") as require, mock.patch.object(
            main.subprocess, "run", return_value=completed
        ) as run:
            result = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"system-snapshot.{action}", "arguments": arguments,
                }),
                True,
            )
        assert result["structuredContent"] == {"action": action}
        assert run.call_args.args[0] == ["/usr/local/bin/cos", "__snapshot", action, *tail]
        assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
        assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
        if action in ("status", "list"):
            require.assert_called_once_with("sys.observe", name="system-snapshots")
        else:
            require.assert_called_once_with("sys.snapshot", wild=True)
