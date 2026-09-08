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
    "claw_test_storage_manager_main",
    clear_modules=("_shared",),
)


def test_mount_requires_exact_device_scope():
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"changed": True}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.os.path, "realpath", return_value="/dev/sdb1"
    ), mock.patch.object(main.policy, "require") as require, mock.patch.object(
        main.subprocess, "run", return_value=completed
    ) as run:
        result = main.mount("/dev/sdb1")
    require.assert_called_once_with("sys.mount", path="/dev/sdb1")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__storage",
        "mount",
        "--device",
        "/dev/sdb1",
    ]
    assert result["changed"] is True


def test_health_uses_diagnostic_scope():
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"status": "ok"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.os.path, "realpath", return_value="/dev/nvme0n1"
    ), mock.patch.object(main.policy, "require") as require, mock.patch.object(
        main.subprocess, "run", return_value=completed
    ):
        result = main.health("/dev/nvme0n1")
    require.assert_called_once_with("sys.storage", name="diagnose")
    assert result["status"] == "ok"


def test_symlink_device_is_rejected_before_policy():
    with mock.patch.object(
        main.os.path, "realpath", return_value="/dev/sdb1"
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="canonical"):
            main.mount("/dev/disk/by-id/example")
    require.assert_not_called()


@pytest.mark.parametrize(
    "device",
    [
        None,
        "",
        "dev/sdb1",
        "/dev/../sdb1",
        "/dev/sdb1\n",
    ],
)
def test_invalid_device_is_rejected_before_policy(device):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(
            ValueError, match="device must be a canonical absolute /dev path"
        ):
            main.mount(device)
    require.assert_not_called()


def test_unknown_action_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="unknown storage action"):
            main._device_action("format", "/dev/sdb1")
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Storage Manager broker returned invalid JSON"),
        (0, "[]", "Storage Manager broker returned a non-object result"),
        (0, json.dumps({"error": "UDisks2 unavailable"}), "UDisks2 unavailable"),
        (
            0,
            json.dumps({"error": None}),
            "Storage Manager broker returned an invalid error payload",
        ),
        (7, "{}", "Storage Manager broker exited 7"),
    ],
)
def test_broker_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()
    require.assert_called_once_with("sys.observe", name="storage")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.status()
    require.assert_called_once_with("sys.observe", name="storage")


def test_broker_execution_failure_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", side_effect=PermissionError("access denied")
    ):
        with pytest.raises(
            RuntimeError, match="Storage Manager broker execution failed: access denied"
        ):
            main.status()
    require.assert_called_once_with("sys.observe", name="storage")


@pytest.mark.parametrize(
    ("call", "timeout", "action"),
    [
        (lambda: main.status(), main.QUERY_TIMEOUT_SECS, "status"),
        (lambda: main.check("/dev/sdb1"), main.CHECK_TIMEOUT_SECS, "check"),
    ],
)
def test_broker_timeout_raises(call, timeout, action):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.os.path, "realpath", side_effect=lambda value: value
    ), mock.patch.object(main.policy, "require"), mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], timeout),
    ) as run:
        with pytest.raises(
            RuntimeError,
            match=rf"Storage Manager broker exceeded {timeout}s for {action}",
        ):
            call()
    assert run.call_args.kwargs["timeout"] == timeout


@pytest.mark.parametrize("action", ["status", "health", "check", "mount", "unmount", "eject"])
def test_relocated_sdk_preserves_storage_authority_and_broker_contract(action):
    device = "/dev/claw-test-device"
    arguments = {} if action == "status" else {"device": device}
    manifest = json.loads((APP_DIR / "app.json").read_text(encoding="utf-8"))
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {
        f"storage-manager.{name}"
        for name in ("status", "health", "check", "mount", "unmount", "eject")
    }
    if action == "status":
        verb, scope = "sys.observe", {"name": "storage"}
    elif action in ("health", "check"):
        verb, scope = "sys.storage", {"name": "diagnose"}
    else:
        verb, scope = "sys.mount", {"path": device}
    needs = tools[f"storage-manager.{action}"]["needs"]
    assert len(needs) == 1
    assert needs[0]["verb"] == verb
    assert needs[0]["scope"] == (
        {"kind": "fixed", "scope": {"kind": "name", "value": scope["name"]}}
        if "name" in scope else {"kind": "from-arg", "arg": "device"}
    )
    completed = mock.Mock(returncode=0, stdout=json.dumps({"action": action}), stderr="")
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(APP_DIR / "app.json"),
            "COS_BIN": "/usr/local/bin/cos",
        }
    ):
        server = load_local_module(APP_DIR / "server.py", "claw_test_storage_manager_server")
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == set(tools)
        with mock.patch.object(main.os.path, "realpath", side_effect=lambda value: value), \
             mock.patch.object(main.policy, "require") as require, \
             mock.patch.object(main.subprocess, "run", return_value=completed) as run:
            result = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"storage-manager.{action}", "arguments": arguments,
                }),
                True,
            )
        assert result["structuredContent"] == {"action": action}
        require.assert_called_once_with(verb, **scope)
        tail = [] if action == "status" else ["--device", device]
        assert run.call_args.args[0] == ["/usr/local/bin/cos", "__storage", action, *tail]
        assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
        expected_timeout = main.CHECK_TIMEOUT_SECS if action == "check" else main.QUERY_TIMEOUT_SECS
        assert run.call_args.kwargs["timeout"] == expected_timeout
