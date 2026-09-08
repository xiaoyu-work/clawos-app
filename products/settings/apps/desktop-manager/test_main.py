import inspect
import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_desktop_manager_main",
    clear_modules=("_shared",),
)


@pytest.mark.parametrize("transport", ["direct", "mcp"])
@pytest.mark.parametrize(
    ("function_name", "action", "args", "capabilities", "flags", "expected"),
    [
        (
            "list_windows", "list", (),
            [mock.call("sys.observe", name="desktop")],
            [], {"windows": []},
        ),
        (
            "focus_window", "focus", ("window-identifier",),
            [mock.call("desktop.window", name="control")],
            ["--identifier", "window-identifier"], {"activated": True},
        ),
        (
            "close_window", "close", ("window-identifier",),
            [mock.call("desktop.window", name="control")],
            ["--identifier", "window-identifier"], {"closed": True},
        ),
        (
            "restart_application", "restart", ("window-identifier", "com.example.App"),
            [
                mock.call("desktop.window", name="control"),
                mock.call("desktop.launch", name="com.example.App"),
            ],
            ["--identifier", "window-identifier", "--app-id", "com.example.App"],
            {"restarted": True},
        ),
    ],
)
def test_routes_use_exact_scopes_and_broker_argv(
    transport, function_name, action, args, capabilities, flags, expected
):
    completed = mock.Mock(
        returncode=0, stdout=json.dumps(expected), stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        function = getattr(main, function_name)
        if transport == "direct":
            result = function(*args)
        else:
            manifest_path = pathlib.Path(__file__).with_name("app.json")
            with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
                os.environ, {"COS_APP_MANIFEST": str(manifest_path)}
            ):
                server = load_local_module(
                    pathlib.Path(__file__).with_name("server.py"),
                    "claw_test_desktop_manager_server",
                )
                listed = server.app._handle_request("tools/list", {}, True)
                assert {tool["name"] for tool in listed["tools"]} == {
                    f"desktop-manager.{name}" for name in ("list", "focus", "close", "restart")
                }
                response = server.app._handle_request(
                    "tools/call",
                    authenticated_mcp_params({
                        "name": f"desktop-manager.{action}",
                        "arguments": dict(inspect.signature(function).bind(*args).arguments),
                    }),
                    True,
                )
                result = response["structuredContent"]
    assert result == expected
    assert require.call_args_list == capabilities
    run.assert_called_once()
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos", "__desktop", action, *flags,
    ]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL


def test_manifest_keeps_separate_observe_window_and_exact_launch_scopes():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    actual = {
        name: [(need["verb"], need["scope"]) for need in tool["needs"]]
        for name, tool in tools.items()
    }
    window = [
        ("desktop.window", {"kind": "fixed", "scope": {"kind": "name", "value": "control"}}),
    ]
    assert actual == {
        "desktop-manager.list": [
            ("sys.observe", {"kind": "fixed", "scope": {"kind": "name", "value": "desktop"}}),
        ],
        "desktop-manager.focus": window,
        "desktop-manager.close": window,
        "desktop-manager.restart": [
            *window, ("desktop.launch", {"kind": "from-arg", "arg": "app_id"}),
        ],
    }


@pytest.mark.parametrize(
    ("identifier", "app_id", "message"),
    [
        ("--window", "com.example.App", "identifier must be a valid window identifier"),
        ("window-identifier", "*", "app_id must be an exact desktop AppID"),
    ],
)
def test_restart_validates_before_policy(identifier, app_id, message):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=message):
            main.restart_application(identifier, app_id)
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Desktop Manager broker returned invalid JSON"),
        (0, "[]", "Desktop Manager broker returned a non-object result"),
        (
            0,
            json.dumps({"error": "compositor unavailable"}),
            "compositor unavailable",
        ),
        (
            0,
            json.dumps({"error": None}),
            "Desktop Manager broker returned an invalid error payload",
        ),
        (7, "{}", "Desktop Manager broker exited 7"),
    ],
)
def test_broker_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.list_windows()
    require.assert_called_once_with("sys.observe", name="desktop")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.list_windows()
    require.assert_called_once_with("sys.observe", name="desktop")


def test_broker_execution_failure_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess, "run", side_effect=PermissionError("access denied")
    ):
        with pytest.raises(
            RuntimeError, match="Desktop Manager broker execution failed: access denied"
        ):
            main.list_windows()
    require.assert_called_once_with("sys.observe", name="desktop")


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(RuntimeError, match="Desktop Manager broker exceeded"):
            main.list_windows()
    require.assert_called_once_with("sys.observe", name="desktop")
