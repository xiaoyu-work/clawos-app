import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_power_manager_main",
    clear_modules=("_shared",),
)


ACTIONS = [
    "suspend", "hibernate", "hybrid-sleep", "suspend-then-hibernate",
    "reboot", "poweroff",
]


@pytest.fixture
def mcp_app():
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"),
            "claw_test_power_manager_server",
        )
        yield server.app


def test_manifest_and_discovery_keep_confirmation_and_separate_power_scope(mcp_app):
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {f"power-manager.{action}" for action in ["status", *ACTIONS]}
    listed = mcp_app._handle_request("tools/list", {}, True)
    assert {tool["name"] for tool in listed["tools"]} == set(tools)
    assert [
        (need["verb"], need["scope"]) for need in tools["power-manager.status"]["needs"]
    ] == [
        ("sys.observe", {"kind": "fixed", "scope": {"kind": "name", "value": "power"}}),
    ]
    for action in ACTIONS:
        tool = tools[f"power-manager.{action}"]
        assert tool["args"] == [{
            "name": "confirm", "kind": "bool", "required": True,
            "binding": "flag", "choices": [True],
        }]
        assert [
            (need["verb"], need["scope"]) for need in tool["needs"]
        ] == [("sys.power", {"kind": "wild"})]


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("confirm", [False, None, 0, 1, "true"])
def test_power_requires_exact_confirm_before_policy(action, confirm):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=f"{action} requires confirm=true"):
            main.request_power(action, confirm)
    require.assert_not_called()


@pytest.mark.parametrize("transport", ["direct", "mcp"])
@pytest.mark.parametrize("action", ["status", *ACTIONS])
def test_all_routes_use_exact_power_scopes(mcp_app, transport, action):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"requested": True}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        if transport == "direct":
            result = main.status() if action == "status" else main.request_power(action, True)
        else:
            response = mcp_app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"power-manager.{action}",
                    "arguments": {} if action == "status" else {"confirm": True},
                }),
                True,
            )
            result = response["structuredContent"]
    if action == "status":
        require.assert_called_once_with("sys.observe", name="power")
    else:
        require.assert_called_once_with("sys.power", wild=True)
    run.assert_called_once()
    expected = ["/usr/local/bin/cos", "__power", action]
    if action != "status":
        expected.append("--confirm")
    assert run.call_args.args[0] == expected
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result["requested"] is True


def test_broker_error_raises():
    completed = mock.Mock(
        returncode=1,
        stdout=json.dumps({"error": "reboot failed"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match="reboot failed"):
            main.request_power("reboot", True)
    require.assert_called_once_with("sys.power", wild=True)
