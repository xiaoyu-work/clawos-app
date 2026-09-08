import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_usb_guard_main",
    clear_modules=("_shared",),
)


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"), "claw_test_usb_guard_server",
        )
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == {
            f"usb-guard.{name}" for name in ["status", "authorize", "block", "unblock", "eject", "restore"]
        }

        def call(command, **arguments):
            if request.param == "direct":
                return getattr(main, command)(**arguments)
            response = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"usb-guard.{command}", "arguments": arguments,
                }),
                True,
            )
            return response["structuredContent"]

        yield call


def test_manifest_keeps_separate_scopes_and_conditional_confirmation():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    for tool in manifest["mcp"]["tools"]:
        command = tool["name"].removeprefix("usb-guard.")
        verb, scope = (
            ("sys.observe", "usb") if command == "status" else ("device.usb", "control")
        )
        assert [(need["verb"], need["scope"]) for need in tool["needs"]] == [
            (verb, {"kind": "fixed", "scope": {"kind": "name", "value": scope}}),
        ]
        if command == "status":
            continue
        confirmation = next(arg for arg in tool["args"] if arg["name"] == "confirm")
        assert confirmation["choices"] == [True]
        assert confirmation["required"] is (command != "authorize")
        if command == "authorize":
            assert confirmation["required_when"] == {
                "kind": "arg-equals", "arg": "state", "value": "off",
            }
            assert "default" not in confirmation


def test_block_uses_usb_control_scope_and_broker_command(invoke):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"blocked": True}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = invoke("block", device="1-2.3", confirm=True)
    require.assert_called_once_with("device.usb", name="control")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__usb",
        "block",
        "--device",
        "1-2.3",
        "--confirm",
    ]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert result["blocked"] is True


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: main.authorize("not-a-device", "on"), "device must be"),
        (lambda: main.authorize("1-2", "invalid"), "state must be on or off"),
        (lambda: main.authorize("1-2", "off", False), "deauthorization requires"),
        (lambda: main.authorize("1-2", "on", True), "authorization does not accept"),
        (lambda: main.authorize("1-2", "on", None), "confirm must be a boolean"),
        (lambda: main.block("1-2", False), "block requires confirm=true"),
        (lambda: main.eject("invalid", True), "device must be"),
        (lambda: main.unblock("not-a-rule", True), "rule_id must be"),
        (lambda: main.restore("not-a-token", True), "backup_token must be"),
        (lambda: main._execute("unexpected"), "unknown USB Guard action"),
    ],
)
def test_invalid_inputs_are_rejected_before_policy(call, message):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=message):
            call()
    require.assert_not_called()


def test_authorization_without_confirm_preserves_historical_behavior(invoke):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"authorized": True}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = invoke("authorize", device="1-2", state="on")
    require.assert_called_once_with("device.usb", name="control")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos", "__usb", "authorize", "--device", "1-2", "--state", "on",
    ]
    assert result["authorized"] is True


def test_unblock_normalizes_rule_id(invoke):
    completed = mock.Mock(returncode=0, stdout=json.dumps({"unblocked": True}), stderr="")
    rule_id = "ABCDEF0123456789ABCDEF0123456789"
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        invoke("unblock", rule_id=rule_id, confirm=True)
    require.assert_called_once_with("device.usb", name="control")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__usb",
        "unblock",
        "--rule-id",
        rule_id.lower(),
        "--confirm",
    ]


@pytest.mark.parametrize(("command", "arguments", "flags"), [
    ("status", {}, []),
    (
        "authorize", {"device": "1-2", "state": "off", "confirm": True},
        ["--device", "1-2", "--state", "off", "--confirm"],
    ),
    ("eject", {"device": "1-2.3", "confirm": True}, ["--device", "1-2.3", "--confirm"]),
    (
        "restore", {"backup_token": "ABCDEF0123456789ABCDEF0123456789", "confirm": True},
        ["--token", "abcdef0123456789abcdef0123456789", "--confirm"],
    ),
])
def test_remaining_routes_keep_exact_scopes_and_argv(invoke, command, arguments, flags):
    completed = mock.Mock(returncode=0, stdout='{"ok":true}', stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        assert invoke(command, **arguments) == {"ok": True}
    if command == "status":
        require.assert_called_once_with("sys.observe", name="usb")
    else:
        require.assert_called_once_with("device.usb", name="control")
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__usb", command, *flags]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL


@pytest.mark.parametrize("confirm", [False, None, 0, 1, "true"])
@pytest.mark.parametrize(("command", "arguments"), [
    ("authorize", {"device": "1-2", "state": "off"}),
    ("block", {"device": "1-2"}),
    ("unblock", {"rule_id": "abcdef0123456789abcdef0123456789"}),
    ("eject", {"device": "1-2"}),
    ("restore", {"backup_token": "abcdef0123456789abcdef0123456789"}),
])
def test_control_rejects_non_true_confirmation_before_policy(command, arguments, confirm):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="confirm"):
            getattr(main, command)(**arguments, confirm=confirm)
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "USB Guard broker returned invalid JSON"),
        (0, "[]", "USB Guard broker returned a non-object result"),
        (0, json.dumps({"error": "usb control failed"}), "usb control failed"),
        (
            0,
            json.dumps({"error": None}),
            "USB Guard broker returned an invalid error payload",
        ),
        (7, "{}", "USB Guard broker exited 7"),
    ],
)
def test_broker_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()
    require.assert_called_once_with("sys.observe", name="usb")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="USB Guard broker unavailable"):
            main.status()
    require.assert_called_once_with("sys.observe", name="usb")


def test_broker_execution_failure_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", side_effect=PermissionError("access denied")
    ):
        with pytest.raises(
            RuntimeError, match="USB Guard broker execution failed: access denied"
        ):
            main.status()
    require.assert_called_once_with("sys.observe", name="usb")


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(RuntimeError, match="USB Guard broker exceeded"):
            main.status()
    require.assert_called_once_with("sys.observe", name="usb")
