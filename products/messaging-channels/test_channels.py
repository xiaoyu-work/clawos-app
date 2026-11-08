"""All four connectors use only the public, owner-bound channel client."""

import json
import os
from pathlib import Path
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


@pytest.fixture(params=["discord", "telegram", "slack", "whatsapp"])
def connector(request):
    from claw_os_sdk.mcp import App

    platform = request.param
    directory = Path(__file__).parent / "apps" / "gateway" / platform
    main = load_local_module(directory / "main.py", f"channel_{platform}_client")
    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(directory / "app.json")},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(directory / "server.py", f"channel_{platform}_server")
    return platform, main, servers[0]


def invoke(connector, command, arguments):
    platform, _, app = connector
    return app._handle_request("tools/call", authenticated_mcp_params({
        "name": f"gateway-{platform}.{command}", "arguments": arguments,
    }), True)


@pytest.mark.parametrize("action", ["status", "start", "stop"])
def test_lifecycle_uses_the_os_client_not_local_process_or_credentials(connector, action):
    platform, main, _ = connector
    expected = {"ok": True, "platform": platform, "running": action == "start"}
    with mock.patch.object(main.channels.channels, "control", return_value=expected) as control, mock.patch.object(
        main.safe_subprocess, "safe_subprocess", side_effect=AssertionError("no App process lifecycle"),
    ), mock.patch.object(main.safe_subprocess, "safe_credential_load", side_effect=AssertionError("no App ingress credentials")):
        assert main.run(action, {}) == expected
        assert invoke(connector, action, {})["structuredContent"] == expected
    assert control.call_count == 2
    assert control.call_args.args == (action,)
    assert callable(control.call_args.kwargs["check_cancelled"])


@pytest.mark.parametrize("text", [["hello", "world"], ["--literal", "reply"]])
def test_safe_reply_supplies_only_event_text_confirmation_and_current_deadline(connector, text):
    _, main, _ = connector
    with mock.patch.object(main.channels.channels, "control", return_value={"ok": True, "submitted": True}) as control:
        result = invoke(connector, "reply", {"event_id": "channel-event-fixture", "text": text, "confirm": True})
    assert result["structuredContent"]["submitted"] is True
    assert control.call_args.args == ("reply",)
    options = control.call_args.kwargs
    assert options["event_id"] == "channel-event-fixture"
    assert options["text"] == " ".join(text)
    assert options["confirm"] is True
    assert set(options) == {"event_id", "text", "confirm", "deadline_unix_ms", "check_cancelled"}


def test_false_confirmation_never_reaches_the_os(connector):
    _, main, _ = connector
    with mock.patch.object(main.channels.channels, "control") as control:
        result = main.run("reply", {"event_id": "event", "text": "text", "confirm": False})
    assert result["ok"] is False
    control.assert_not_called()


def test_daemon_failure_has_no_process_or_agent_fallback(connector):
    _, main, _ = connector
    with mock.patch.object(main.channels.channels, "control", side_effect=RuntimeError("daemon unavailable")), mock.patch.object(
        main.safe_subprocess, "safe_subprocess",
    ) as process:
        result = main.run("start", {})
    assert result["ok"] is False
    assert result["error"] == "daemon unavailable"
    process.assert_not_called()
