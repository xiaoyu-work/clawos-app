import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_network_manager_main",
    clear_modules=("_shared",),
)


@pytest.mark.parametrize("transport", ["direct", "mcp"])
@pytest.mark.parametrize(
    ("function_name", "action", "arguments", "capabilities", "flags"),
    [
        *[
            (function_name, action, {}, [mock.call("sys.observe", name="network")], [])
            for function_name, action in [
                ("status", "status"), ("list_wifi", "wifi-list"),
                ("list_connections", "connection-list"), ("list_vpns", "vpn-list"),
            ]
        ],
        (
            "connect_wifi", "wifi-connect", {"ssid": "Cafe"},
            [mock.call("net.manage", name="wifi")], ["--target", "Cafe"],
        ),
        (
            "connect_wifi", "wifi-connect",
            {"ssid": "Cafe", "credential": "default/cafe_psk"},
            [
                mock.call("net.manage", name="wifi"),
                mock.call("secret.read", name="default/cafe_psk"),
            ],
            ["--target", "Cafe", "--credential", "default/cafe_psk"],
        ),
        (
            "disconnect_wifi", "wifi-disconnect", {"device": "wlan0"},
            [mock.call("net.manage", name="wifi")], ["--target", "wlan0"],
        ),
        (
            "forget_wifi", "wifi-forget", {"connection": "Cafe"},
            [mock.call("net.manage", name="wifi")], ["--target", "Cafe"],
        ),
        *[
            (function_name, action, {"state": state},
             [mock.call("net.manage", name=scope)], ["--state", state])
            for function_name, action, scope in [
                ("set_wifi", "wifi-toggle", "wifi"),
                ("set_airplane_mode", "airplane", "airplane"),
            ]
            for state in ["on", "off"]
        ],
        *[
            (function_name, action, {"profile": "work-vpn"},
             [mock.call("net.manage", name="vpn")], ["--target", "work-vpn"])
            for function_name, action in [
                ("activate_vpn", "vpn-up"), ("deactivate_vpn", "vpn-down"),
            ]
        ],
    ],
)
def test_all_routes_preserve_scopes_and_broker_argv(
    transport, function_name, action, arguments, capabilities, flags
):
    completed = mock.Mock(returncode=0, stdout='{"changed":true}', stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        if transport == "direct":
            result = getattr(main, function_name)(**arguments)
        else:
            with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
                os.environ, {
                    "COS_APP_MANIFEST": str(pathlib.Path(__file__).with_name("app.json")),
                },
            ):
                server = load_local_module(
                    pathlib.Path(__file__).with_name("server.py"),
                    "claw_test_network_manager_server",
                )
                listed = server.app._handle_request("tools/list", {}, True)
                assert {tool["name"] for tool in listed["tools"]} == {
                    f"network-manager.{name}" for name in [
                        "status", "wifi-list", "connection-list", "vpn-list",
                        "wifi-connect", "wifi-disconnect", "wifi-forget",
                        "wifi-toggle", "airplane", "vpn-up", "vpn-down",
                    ]
                }
                response = server.app._handle_request(
                    "tools/call",
                    authenticated_mcp_params({
                        "name": f"network-manager.{action}", "arguments": arguments,
                    }),
                    True,
                )
                result = response["structuredContent"]
    assert result == {"changed": True}
    assert require.call_args_list == capabilities
    run.assert_called_once()
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__network", action, *flags]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL


def test_wifi_connect_requests_network_and_secret_scopes():
    completed = mock.Mock(returncode=0, stdout=json.dumps({"changed": True}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = main.connect_wifi("Cafe", "default/cafe_psk")
    assert require.call_args_list == [
        mock.call("net.manage", name="wifi"),
        mock.call("secret.read", name="default/cafe_psk"),
    ]
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__network",
        "wifi-connect",
        "--target",
        "Cafe",
        "--credential",
        "default/cafe_psk",
    ]
    assert result["changed"] is True


@pytest.mark.parametrize(
    ("ssid", "credential", "message"),
    [
        ("", None, "ssid must be a non-empty string"),
        ("Cafe", "", "credential must be a non-empty string"),
    ],
)
def test_wifi_connect_validates_before_policy(ssid, credential, message):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=message):
            main.connect_wifi(ssid, credential)
    require.assert_not_called()


def test_airplane_maps_to_fixed_scope():
    completed = mock.Mock(returncode=0, stdout=json.dumps({"changed": True}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        main.set_airplane_mode("on")
    require.assert_called_once_with("net.manage", name="airplane")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__network",
        "airplane",
        "--state",
        "on",
    ]


def test_invalid_airplane_state_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=r"airplane requires on\|off"):
            main.set_airplane_mode("auto")
    require.assert_not_called()


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Network Manager broker returned invalid JSON"),
        (0, "[]", "Network Manager broker returned a non-object result"),
        (
            0,
            json.dumps({"error": "NetworkManager unavailable"}),
            "NetworkManager unavailable",
        ),
        (7, "{}", "Network Manager broker exited 7"),
    ],
)
def test_broker_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()
    require.assert_called_once_with("sys.observe", name="network")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.status()
    require.assert_called_once_with("sys.observe", name="network")


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(RuntimeError, match="Network Manager broker exceeded"):
            main.status()
    require.assert_called_once_with("sys.observe", name="network")
