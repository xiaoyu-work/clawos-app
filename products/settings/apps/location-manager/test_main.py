import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_location_manager_main",
    clear_modules=("_shared",),
)


@pytest.fixture
def mcp_app():
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
        },
    ):
        server = load_local_module(
            pathlib.Path(__file__).with_name("server.py"),
            "claw_test_location_manager_server",
        )
        yield server.app


def test_manifest_and_sdk_discovery_preserve_accuracy_and_location_grant(mcp_app):
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    tools = manifest["mcp"]["tools"]
    expected = {"location-manager.locate", "location-manager.timezone"}
    assert {tool["name"] for tool in tools} == expected
    listed = mcp_app._handle_request("tools/list", {}, True)
    assert {tool["name"] for tool in listed["tools"]} == expected
    for tool in tools:
        assert tool["args"] == [{
            "name": "accuracy", "kind": "name", "required": False,
            "default": "city",
            "choices": ["country", "city", "neighborhood", "street", "exact"],
        }]
        assert [
            (need["verb"], need["scope"]) for need in tool["needs"]
        ] == [("device.location", {"kind": "wild"})]


@pytest.mark.parametrize("transport", ["direct", "mcp"])
@pytest.mark.parametrize("action", ["locate", "timezone"])
@pytest.mark.parametrize("accuracy", [None, "country", "city", "neighborhood", "street", "exact"])
def test_queries_require_location_capability(mcp_app, transport, action, accuracy):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"provider": "geoclue2"}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        arguments = {} if accuracy is None else {"accuracy": accuracy}
        if transport == "direct":
            result = main.query(action, **arguments)
        else:
            response = mcp_app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"location-manager.{action}", "arguments": arguments,
                }),
                True,
            )
            result = response["structuredContent"]
    require.assert_called_once_with("device.location", wild=True)
    assert result["provider"] == "geoclue2"
    run.assert_called_once()
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos", "__location", action, "--accuracy",
        "city" if accuracy is None else accuracy,
    ]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL


def test_invalid_accuracy_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="accuracy must be"):
            main.query("timezone", "gps")
    require.assert_not_called()


def test_unknown_action_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="unknown location action"):
            main.query("set-timezone")
    require.assert_not_called()
