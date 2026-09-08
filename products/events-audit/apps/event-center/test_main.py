import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(
    pathlib.Path(__file__).with_name("main.py"),
    "claw_test_event_center_main",
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
            pathlib.Path(__file__).with_name("server.py"), "claw_test_event_center_server",
        )
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == {
            f"event-center.{name}" for name in ["status", "recent", "watch-pid"]
        }

        def call(command, **arguments):
            if request.param == "direct":
                function = main.watch_pid if command == "watch-pid" else getattr(main, command)
                return function(**arguments)
            response = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"event-center.{command}", "arguments": arguments,
                }),
                True,
            )
            return response["structuredContent"]

        yield call


def test_manifest_keeps_sensitive_event_grant_and_query_default():
    manifest = json.loads(pathlib.Path(__file__).with_name("app.json").read_text())
    assert "operations" not in manifest
    for tool in manifest["mcp"]["tools"]:
        assert [(need["verb"], need["scope"]) for need in tool["needs"]] == [
            ("sys.events", {"kind": "fixed", "scope": {"kind": "name", "value": "observe"}}),
        ]
        if tool["name"] == "event-center.recent":
            args = {arg["name"]: arg for arg in tool["args"]}
            assert args["limit"]["default"] == 100
            assert args["limit"]["kind"] == "integer"
            assert args["source"]["required"] is False
            assert args["source"]["binding"] == "flag"


def test_status_uses_event_scope_and_safe_argv(invoke):
    completed = mock.Mock(returncode=0, stdout='{"active_pid_watches":0}', stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        assert invoke("status") == {"active_pid_watches": 0}
    require.assert_called_once_with("sys.events", name="observe")
    assert run.call_args.args[0] == ["/usr/local/bin/cos", "__events", "status"]


@pytest.mark.parametrize("source", ["udev", "systemd", "journal", "storage", "security", "process"])
@pytest.mark.parametrize("limit", [1, 20, 1000])
def test_filtered_events_use_event_scope(invoke, source, limit):
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"count": 2}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = invoke("recent", limit=limit, source=source)
    require.assert_called_once_with("sys.events", name="observe")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__events",
        "recent",
        "--source",
        source,
        "--limit",
        str(limit),
    ]
    assert result["count"] == 2


def test_invalid_source_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match=r"unknown event source: \*"):
            main.recent(10, "*")
    require.assert_not_called()


@pytest.mark.parametrize("limit", [0, 1001, True, "25"])
def test_invalid_limit_is_rejected_before_policy(limit):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="limit"):
            main.recent(limit)
    require.assert_not_called()


@pytest.mark.parametrize("pid", [0, 2**32, True, "123"])
def test_invalid_pid_is_rejected_before_policy(pid):
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="pid"):
            main.watch_pid(pid)
    require.assert_not_called()


def test_recent_default_limit_is_forwarded(invoke):
    completed = mock.Mock(returncode=0, stdout=json.dumps({"count": 1}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        invoke("recent")
    require.assert_called_once_with("sys.events", name="observe")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos", "__events", "recent", "--limit", "100",
    ]


@pytest.mark.parametrize("pid", [1, 123, 2**32 - 1])
def test_watch_pid_uses_event_scope_and_safe_argv(invoke, pid):
    completed = mock.Mock(returncode=0, stdout=json.dumps({"watching": pid}), stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = invoke("watch-pid", pid=pid)
    require.assert_called_once_with("sys.events", name="observe")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__events",
        "watch-pid",
        "--pid",
        str(pid),
    ]
    assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
    assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
    assert result["watching"] == pid


@pytest.mark.parametrize(
    ("returncode", "stdout", "message"),
    [
        (0, "{", "Event Center broker returned invalid JSON"),
        (0, "[]", "Event Center broker returned a non-object result"),
        (0, json.dumps({"error": ""}), "invalid error payload"),
        (0, json.dumps({"error": "event query failed"}), "event query failed"),
        (7, "{}", "Event Center broker exited 7"),
        (
            9,
            json.dumps({"error": "broker detail"}),
            "broker detail",
        ),
    ],
)
def test_broker_payload_failures_raise(returncode, stdout, message):
    completed = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed):
        with pytest.raises(RuntimeError, match=message):
            main.status()
    require.assert_called_once_with("sys.events", name="observe")


def test_missing_broker_executable_raises():
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
        main.shutil, "which", return_value=None
    ), mock.patch.object(main.policy, "require") as require:
        with pytest.raises(FileNotFoundError, match="cos binary not found"):
            main.status()
    require.assert_called_once_with("sys.events", name="observe")


@pytest.mark.parametrize(
    ("error", "exception", "message"),
    [
        (
            FileNotFoundError("missing"),
            FileNotFoundError,
            "Event Center broker executable not found",
        ),
        (
            PermissionError("denied"),
            PermissionError,
            "permission denied launching Event Center broker",
        ),
    ],
)
def test_broker_launch_failures_raise(error, exception, message):
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ), mock.patch.object(main.subprocess, "run", side_effect=error):
        with pytest.raises(exception, match=message):
            main.status()


def test_broker_timeout_raises():
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(
        main.subprocess,
        "run",
        side_effect=main.subprocess.TimeoutExpired(["cos"], main.TIMEOUT_SECS),
    ):
        with pytest.raises(TimeoutError, match="Event Center broker exceeded"):
            main.status()
    require.assert_called_once_with("sys.events", name="observe")
