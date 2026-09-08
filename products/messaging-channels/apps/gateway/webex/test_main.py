"""Webex REST contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_webex_main")
SUCCESS = (200, {}, b'{"id":"message-fixture","created":"fixture-time"}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.delenv("COS_WEBEX_BOT_TOKEN", raising=False)
    with mock.patch.object(main, "_load_credential", return_value=("fixture-token", None)), mock.patch.object(
        main.gateway_memory, "remember_send",
    ):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_webex_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-webex.send", "gateway-webex.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-webex.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


@pytest.mark.parametrize(("argv", "expected"), [
    (["person@example.com", "hello", "--plain"], ("person@example.com", "hello", True)),
    (["room", "hello"], ("room", "hello", False)),
    (["room", "hello", "--plain=false"], ("room", "hello", False)),
    (["--", "room", "--literal"], ("room", "--literal", False)),
])
def test_list_dispatch_forwards_manifest_options(argv, expected):
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv) == {"ok": True}
    send.assert_called_once_with(*expected)


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("recipient", "field", "value"), [
    (" person@example.test ", "toPersonEmail", "person@example.test"),
    (" room-fixture ", "roomId", "room-fixture"),
])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_default_markdown_send_routes_one_destination(invoke, recipient, field, value, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", recipient=recipient, text=text)
    assert result == {
        "ok": True, "platform": "webex", "field": field, "value": value,
        "id": "message-fixture", "created": "fixture-time", "kind": "markdown",
    }
    assert transport.call_args.args == ("POST", "https://webexapis.com/v1/messages")
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {field: value, "markdown": text, "text": text}
    assert kwargs["headers"]["Authorization"] == "Bearer fixture-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main._load_credential.assert_called_once_with("webex_bot_token")
    main.gateway_memory.remember_send.assert_called_once_with(
        "webex", result, channel_id=recipient, text=text,
    )


def test_plain_send_omits_markdown(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", recipient="room", text="**hello**", plain=True)
    assert result["kind"] == "text"
    assert json.loads(transport.call_args.kwargs["body"]) == {"roomId": "room", "text": "**hello**"}


def test_environment_token_takes_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_WEBEX_BOT_TOKEN", " override-fixture ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        assert invoke("send", recipient="room", text="hello")["ok"] is True
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer override-fixture"
    main._load_credential.assert_not_called()


def test_missing_token_stops_before_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", recipient="room", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize(("recipient", "text"), [("", "hello"), ("room", "   ")])
def test_empty_input_stops_before_credentials_and_network(invoke, recipient, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", recipient=recipient, text=text)
    assert result["ok"] is False
    main._load_credential.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize("plain", [False, True])
def test_text_limit_is_preserved(invoke, plain):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", recipient="room", text="x" * (main.SOFT_LEN + 1), plain=plain)
    payload = json.loads(transport.call_args.kwargs["body"])
    assert payload["text"] == "x" * (main.SOFT_LEN - 1) + "\u2026"
    if not plain:
        assert payload["markdown"] == payload["text"]


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_preserves_destination_context(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(main.API_URL, 400, "Bad Request", {}, io.BytesIO(b"rejected fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", recipient="room", text="hello", plain=True)
    assert result["ok"] is False
    assert result["field"] == "roomId"
    assert result["value"] == "room"
    assert result["kind"] == "text"
    assert "fixture" in result["error"]


@pytest.mark.parametrize("configured", [False, True])
def test_status_is_outbound_only_and_does_not_disclose_token(invoke, configured):
    credential = ("fixture-token", None) if configured else (None, "missing fixture")
    with mock.patch.object(main, "_load_credential", return_value=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is configured
    assert result["config_error"] == credential[1]
    assert result["running"] is False
    assert "fixture-token" not in json.dumps(result)
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
