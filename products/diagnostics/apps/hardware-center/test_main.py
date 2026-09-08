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
    "claw_test_hardware_center_main",
    clear_modules=("_shared",),
)


def test_summary_uses_hardware_observe_scope():
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"schema": 1}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = main.inspect("summary")
    require.assert_called_once_with("sys.observe", name="hardware")
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__hardware", "summary"]
    assert result["schema"] == 1


def test_unknown_hardware_command_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="unknown hardware command"):
            main.inspect("unexpected")
    require.assert_not_called()


@pytest.mark.parametrize("command", sorted(main.COMMANDS))
def test_relocated_sdk_routes_preserve_hardware_scope(command):
    manifest = json.loads((APP_DIR / "app.json").read_text(encoding="utf-8"))
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {f"hardware-center.{name}" for name in main.COMMANDS}
    needs = tools[f"hardware-center.{command}"]["needs"]
    assert len(needs) == 1
    assert needs[0]["verb"] == "sys.observe"
    assert needs[0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "hardware"},
    }
    completed = mock.Mock(
        returncode=0, stdout=json.dumps({"inventory": command}), stderr="",
    )
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(APP_DIR / "app.json"),
            "COS_BIN": "/usr/local/bin/cos",
        }
    ):
        server = load_local_module(APP_DIR / "server.py", "claw_test_hardware_center_server")
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == set(tools)
        with mock.patch.object(main.policy, "require") as require, mock.patch.object(
            main.subprocess, "run", return_value=completed
        ) as run:
            result = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"hardware-center.{command}", "arguments": {},
                }),
                True,
            )
        assert result["structuredContent"] == {"inventory": command}
        require.assert_called_once_with("sys.observe", name="hardware")
        assert run.call_args.args[0] == ["/usr/local/bin/cos", "__hardware", command]
        assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
        assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS


@pytest.mark.parametrize(("returncode", "stdout", "message"), [
    (0, "{", "returned invalid JSON"),
    (0, "[]", "returned a non-object result"),
    (1, '{"error":"inventory unavailable"}', "inventory unavailable"),
])
def test_broker_failures_remain_errors(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.inspect("summary")
