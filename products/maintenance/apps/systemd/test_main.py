import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_systemd_main",
    clear_modules=("_shared",),
)


ACTIONS = ["start", "stop", "restart", "reload", "enable", "disable"]


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"), "claw_test_systemd_server",
        )
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == {
            f"systemd.{name}" for name in ["status", *ACTIONS]
        }

        def call(command, unit):
            if request.param == "direct":
                return main.status(unit) if command == "status" else main.control(command, unit)
            response = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"systemd.{command}", "arguments": {"unit": unit},
                }),
                True,
            )
            return response["structuredContent"]

        yield call


def test_manifest_keeps_exact_unit_grants_without_new_confirmation():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    for tool in manifest["mcp"]["tools"]:
        assert tool["args"] == [{
            "name": "unit", "kind": "name", "required": True, "binding": "positional",
        }]
        verb = "sys.observe" if tool["name"] == "systemd.status" else "sys.service"
        assert [(need["verb"], need["scope"]) for need in tool["needs"]] == [
            (verb, {"kind": "from-arg", "arg": "unit"}),
        ]


def test_rejects_option_and_path_units():
    with mock.patch.object(main.policy, "require") as require:
        for unit in ("--user", "../ssh.service"):
            with pytest.raises(ValueError, match="unit must be a valid systemd name"):
                main.status(unit)
    require.assert_not_called()


def test_accepts_instantiated_service_unit(invoke):
    completed = mock.Mock(returncode=0, stdout="{}", stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as runner:
        invoke("status", "user@1000.service")
    require.assert_called_once_with("sys.observe", name="user@1000.service")
    assert runner.call_args.args[0][-1] == "user@1000.service"


@pytest.mark.parametrize("unit", [
    "ssh.service", "demo.socket", "demo.timer", "data.mount", "demo.target", "demo.path",
])
def test_status_uses_observe_capability(invoke, unit):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"state": {"active": True}}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as runner:
        result = invoke("status", unit)
    require.assert_called_once_with("sys.observe", name=unit)
    assert runner.call_args[0][0] == [
        "/usr/local/bin/cos",
        "__systemd",
        "status",
        unit,
    ]
    assert runner.call_args.kwargs["timeout"] == main.QUERY_TIMEOUT_SECS
    assert result["state"]["active"] is True


@pytest.mark.parametrize("action", ACTIONS)
def test_controls_use_exact_service_capability(invoke, action):
    completed = mock.Mock(returncode=0, stdout=json.dumps({"changed": True}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", return_value=completed
    ) as runner:
        result = invoke(action, "demo.service")
    require.assert_called_once_with("sys.service", name="demo.service")
    assert runner.call_args.args[0] == [
        "/usr/local/bin/cos", "__systemd", action, "demo.service",
    ]
    assert runner.call_args.kwargs["timeout"] == main.CONTROL_TIMEOUT_SECS
    assert runner.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result["changed"] is True


def test_unknown_action_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="unknown systemd action"):
            main.control("unexpected", "demo.service")
    require.assert_not_called()


@pytest.mark.parametrize("action", ["status", *ACTIONS])
@pytest.mark.parametrize("unit", [
    None, 1, "", "--user", "../ssh.service", "ssh", "ssh.service\n",
    "a" * 256 + ".service",
])
def test_invalid_units_are_rejected_before_authority(action, unit):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="unit must be a valid systemd name"):
            if action == "status":
                main.status(unit)
            else:
                main.control(action, unit)
    require.assert_not_called()


def test_broker_error_raises():
    completed = mock.Mock(
        returncode=1,
        stdout=json.dumps({"error": "restart failed"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match="restart failed"):
            main.control("restart", "demo.service")
    require.assert_called_once_with("sys.service", name="demo.service")


def test_invalid_json_raises():
    completed = mock.Mock(returncode=0, stdout="not-json", stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match="systemd broker returned invalid JSON"):
            main.status("ssh.service")
