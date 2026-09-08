import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_security_center_main",
    clear_modules=("_shared",),
)


ACTIONS = ["summary", "auth", "ssh", "sudo", "mac", "ports", "events"]


@pytest.fixture
def mcp_app():
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"),
            "claw_test_security_center_server",
        )
        yield server.app


def test_manifest_and_sdk_discovery_keep_sensitive_read_scope(mcp_app):
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    tools = manifest["mcp"]["tools"]
    expected = {f"security-center.{action}" for action in ACTIONS}
    assert {tool["name"] for tool in tools} == expected
    listed = mcp_app._handle_request("tools/list", {}, True)
    assert {tool["name"] for tool in listed["tools"]} == expected
    for tool in tools:
        assert not tool.get("args")
        assert [
            (need["verb"], need["scope"]) for need in tool["needs"]
        ] == [
            ("sys.security", {"kind": "fixed", "scope": {"kind": "name", "value": "audit"}}),
        ]


@pytest.mark.parametrize("transport", ["direct", "mcp"])
@pytest.mark.parametrize("action", ACTIONS)
def test_routes_use_sensitive_security_scope(mcp_app, transport, action):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"status": "warning"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        if transport == "direct":
            result = getattr(main, action)()
        else:
            response = mcp_app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"security-center.{action}", "arguments": {},
                }),
                True,
            )
            result = response["structuredContent"]
    require.assert_called_once_with("sys.security", name="audit")
    run.assert_called_once()
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__security", action]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result["status"] == "warning"


@pytest.mark.parametrize("action", ACTIONS)
def test_security_commands_reject_arguments_before_policy(action):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(TypeError):
            getattr(main, action)("unexpected")
    require.assert_not_called()


def test_broker_error_raises():
    completed = mock.Mock(
        returncode=1,
        stdout=json.dumps({"error": "security inspection failed"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match="security inspection failed"):
            main.ports()
    require.assert_called_once_with("sys.security", name="audit")
