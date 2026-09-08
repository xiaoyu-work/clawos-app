"""Slack Web API contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_slack_main")
TOKEN = "fixture-token"
SUCCESS = (200, {}, b'{"ok":true,"ts":"fixture-time"}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.delenv("COS_SLACK_TOKEN", raising=False)
    with mock.patch.object(
        main.safe_subprocess, "safe_credential_load", return_value=(TOKEN, None),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_slack_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-slack.send", "gateway-slack.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-slack.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("channel", ["C123ABC", "D123ABC"])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_preserves_destination_text_and_authentication(invoke, channel, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", channel_id=channel, text=text)
    assert result == {
        "ok": True, "platform": "slack", "channel_id": channel, "ts": "fixture-time",
    }
    assert transport.call_args.args == ("POST", "https://slack.com/api/chat.postMessage")
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"channel": channel, "text": text}
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert kwargs["headers"]["User-Agent"] == main.USER_AGENT
    assert kwargs["timeout"] == 15
    assert kwargs["verb_id"] == "net.dial"
    main.safe_subprocess.safe_credential_load.assert_called_once_with("slack_bot_token")
    main.gateway_memory.remember_send.assert_called_once_with(
        "slack", result, channel_id=channel, text=text,
    )


def test_environment_token_takes_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_SLACK_TOKEN", " override-fixture ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", channel_id="C123ABC", text="hello")
    assert result["ok"] is True
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer override-fixture"
    main.safe_subprocess.safe_credential_load.assert_not_called()


def test_missing_token_stops_before_network(invoke):
    with mock.patch.object(
        main.safe_subprocess, "safe_credential_load", return_value=(None, "missing fixture"),
    ), mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert invoke("send", channel_id="C123ABC", text="hello") == {
            "ok": False, "error": "missing fixture",
        }
    transport.assert_not_called()


@pytest.mark.parametrize(("channel", "text"), [("", "hello"), ("C123ABC", "   ")])
def test_empty_input_stops_before_credentials_and_network(invoke, channel, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", channel_id=channel, text=text)
    assert result["ok"] is False
    main.safe_subprocess.safe_credential_load.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize(("raw", "error"), [
    (b'{"ok":false,"error":"channel_not_found"}', "channel_not_found"),
    (b"{}", "unknown"),
    (b"[]", "unknown"),
    (b"not JSON", "non-JSON response"),
])
def test_http_success_is_not_slack_success(invoke, raw, error):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        result = invoke("send", channel_id="C123ABC", text="hello")
    assert result["ok"] is False
    assert error in result["error"]


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(
            main.SLACK_API, 429, "Too Many Requests", {}, io.BytesIO(b"limited fixture"),
        ),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", channel_id="C123ABC", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


@pytest.mark.parametrize("length", [main.MAX_LEN, main.MAX_LEN + 1])
def test_text_limit_is_preserved(invoke, length):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", channel_id="C123ABC", text="x" * length)
    expected = "x" * length if length == main.MAX_LEN else "x" * (main.MAX_LEN - 1) + "\u2026"
    assert json.loads(transport.call_args.kwargs["body"])["text"] == expected


def test_status_has_no_credentials_network_or_inbound_loop(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result == {
        "ok": True, "platform": "slack", "running": False,
        "note": "Outbound-only mode. Socket Mode / Events HTTP not yet implemented.",
    }
    main.safe_subprocess.safe_credential_load.assert_not_called()
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
