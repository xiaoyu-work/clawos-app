"""Zulip REST contracts through direct and manifest SDK dispatch."""

import base64
import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error
import urllib.parse

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_zulip_main")
SITE = "https://zulip.example.test"
CREDENTIALS = {
    "zulip_site": SITE + "/",
    "zulip_bot_email": "bot@example.test",
    "zulip_bot_api_key": "fixture-key",
}
SUCCESS = (200, {}, b'{"result":"success","id":42,"msg":""}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_ZULIP_SITE", "COS_ZULIP_BOT_EMAIL", "COS_ZULIP_BOT_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with mock.patch.object(
        main, "_load_credential", side_effect=lambda name: (CREDENTIALS[name], None),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_zulip_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-zulip.send", "gateway-zulip.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-zulip.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("recipient", "fields"), [
    (" general ", {"type": "stream", "to": "general", "topic": "(no topic)"}),
    (" general : release:one ", {"type": "stream", "to": "general", "topic": "release:one"}),
    ("general: ", {"type": "stream", "to": "general", "topic": "(no topic)"}),
    ("person@example.test", {"type": "private", "to": '["person@example.test"]'}),
    ("a@example.test, b@example.test", {"type": "private", "to": '["a@example.test", "b@example.test"]'}),
])
@pytest.mark.parametrize("text", ["hello + world & more=\n", "--literal", "\u4f60\u597d"])
def test_send_preserves_stream_topic_and_private_routing(invoke, recipient, fields, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", recipient=recipient, text=text)
    assert result == {
        "ok": True, "platform": "zulip", "routing": fields["type"], "site": SITE,
        "id": 42, "result": "success", "msg": "",
    }
    assert transport.call_args.args == ("POST", SITE + "/api/v1/messages")
    kwargs = transport.call_args.kwargs
    assert urllib.parse.parse_qs(kwargs["body"].decode()) == {
        key: [value] for key, value in {**fields, "content": text}.items()
    }
    scheme, auth = kwargs["headers"]["Authorization"].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(auth).decode() == "bot@example.test:fixture-key"
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    assert main._load_credential.call_args_list == [mock.call(name) for name in CREDENTIALS]
    main.gateway_memory.remember_send.assert_called_once_with(
        "zulip", result, channel_id=recipient, text=text,
    )


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_ZULIP_SITE", " https://override.example.test/// ")
    monkeypatch.setenv("COS_ZULIP_BOT_EMAIL", " override@example.test ")
    monkeypatch.setenv("COS_ZULIP_BOT_API_KEY", " override-key ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        assert invoke("send", recipient="general", text="hello")["ok"] is True
    assert transport.call_args.args[1] == "https://override.example.test/api/v1/messages"
    auth = transport.call_args.kwargs["headers"]["Authorization"].split(" ", 1)[1]
    assert base64.b64decode(auth).decode() == "override@example.test:override-key"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_credentials_stop_before_network(invoke, missing):
    def credential(name):
        return (None, "missing fixture") if name == missing else (CREDENTIALS[name], None)

    with mock.patch.object(main, "_load_credential", side_effect=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", recipient="general", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


def test_invalid_site_scheme_stops_before_network(invoke, monkeypatch):
    monkeypatch.setenv("COS_ZULIP_SITE", "file:///fixture")
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", recipient="general", text="hello")
    assert result["ok"] is False
    assert "http(s)" in result["error"]
    transport.assert_not_called()


def test_empty_stream_name_is_rejected(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert invoke("send", recipient=":topic", text="hello") == {"ok": False, "error": "stream name empty"}
    transport.assert_not_called()


@pytest.mark.parametrize("raw", [b'{"result":"error","msg":"rejected fixture"}', b"{}", b"[]", b"not JSON"])
def test_http_success_requires_api_success(invoke, raw):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        result = invoke("send", recipient="general", text="hello")
    assert result["ok"] is False
    assert result["result"] != "success"


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(SITE, 400, "Bad Request", {}, io.BytesIO(b"rejected fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", recipient="general", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


@pytest.mark.parametrize("length", [main.SOFT_LEN, main.SOFT_LEN + 1])
def test_text_limit_is_preserved(invoke, length):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", recipient="general", text="x" * length)
    expected = "x" * length if length == main.SOFT_LEN else "x" * (main.SOFT_LEN - 1) + "\u2026"
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())["content"] == [expected]


def test_status_omits_bot_credentials_and_does_not_contact_realm(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["running"] is False
    assert result["site"] == SITE
    assert CREDENTIALS["zulip_bot_email"] not in json.dumps(result)
    assert CREDENTIALS["zulip_bot_api_key"] not in json.dumps(result)
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()


def test_status_reports_missing_configuration(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")):
        result = invoke("status")
    assert result["configured"] is False
    assert result["site"] is None
    assert result["config_error"] == "missing fixture"
