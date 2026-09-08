"""One-shot ntfy contracts through direct and manifest SDK dispatch."""

import base64
import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_ntfy_main")
SITE = "https://notify.example.test:8443"
CREDENTIALS = {"ntfy_default_topic": "default-topic", "ntfy_token": "stored-token"}
SUCCESS = (200, {}, b'{"id":"fixture-id"}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_NTFY_SERVER", "COS_NTFY_DEFAULT_TOPIC", "COS_NTFY_TOKEN"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_ntfy_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-ntfy.send", "gateway-ntfy.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-ntfy.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_list_dispatch_forwards_manifest_options():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", ["hello", "--topic", "alerts", "--title", "Title", "--markdown"]) == {"ok": True}
    send.assert_called_once_with(
        "alerts", "hello", title="Title", priority=None, tags=None, click=None,
        markdown=True, server=None, bearer=None, basic=None,
    )


def test_removed_leading_topic_is_rejected():
    with mock.patch.object(main, "_send") as send:
        result = main.run("send", ["alerts", "hello"])
    assert result["ok"] is False
    assert "too many positional arguments" in result["error"]
    send.assert_not_called()


def test_one_positional_is_always_message_text():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        main.run("send", ["hello"])
    assert send.call_args.args == (None, "hello")


def test_ntfy_materialized_server_is_shared_by_send_and_status():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        main.run("send", ["hello", "--server=" + SITE])
    assert send.call_args.kwargs["server"] == SITE
    assert main.run("status", ["--server=" + SITE])["server"] == SITE


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_publish_preserves_utf8_metadata_and_explicit_server(invoke, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke(
            "send", server=SITE + "/", topic="alerts", text=text, title=" Title ",
            priority=" HIGH ", tags=" warning,computer ", click="https://action.example.test",
            markdown=True,
        )
    assert result == {
        "ok": True, "platform": "ntfy", "server": SITE, "topic": "alerts",
        "status": 200, "id": "fixture-id", "result": {"id": "fixture-id"},
    }
    assert transport.call_args.args == ("POST", SITE + "/alerts")
    kwargs = transport.call_args.kwargs
    assert kwargs["body"] == text.encode("utf-8")
    assert kwargs["headers"] == {
        "Content-Type": "text/plain; charset=utf-8", "User-Agent": main.USER_AGENT,
        "Title": "Title", "Priority": "high", "Tags": "warning,computer",
        "Click": "https://action.example.test", "Markdown": "yes",
        "Authorization": "Bearer stored-token",
    }
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    transport.assert_called_once()
    main.gateway_memory.remember_send.assert_called_once_with("ntfy", result, channel_id="alerts", text=text)


@pytest.mark.parametrize("server", ["https://ntfy.sh", "https://ntfy.sh/"])
def test_ntfy_fallback_host_never_receives_stored_token(invoke, server):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        assert invoke("send", server=server, topic="alerts", text="hello")["ok"] is True
    assert "Authorization" not in transport.call_args.kwargs["headers"]
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("mode", ["bearer", "basic", "both", "anonymous", "environment"])
def test_authentication_precedence(invoke, monkeypatch, mode):
    kwargs = {}
    if mode in ("bearer", "both"):
        kwargs["bearer"] = " explicit-token "
    if mode in ("basic", "both"):
        kwargs["basic"] = "user:fixture"
    monkeypatch.setenv("COS_NTFY_TOKEN", " env-token " if mode == "environment" else "")
    with mock.patch.object(main, "_load_credential", return_value=(None, None)), mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=SUCCESS,
    ) as transport:
        invoke("send", server=SITE, topic="alerts", text="hello", **kwargs)
    expected = {
        "bearer": "Bearer explicit-token", "both": "Bearer explicit-token",
        "basic": "Basic " + base64.b64encode(b"user:fixture").decode(),
        "anonymous": None, "environment": "Bearer env-token",
    }
    assert transport.call_args.kwargs["headers"].get("Authorization") == expected[mode]


def test_public_server_allows_explicit_auth_only(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", server=main.DEFAULT_SERVER, topic="alerts", text="hello", bearer="explicit-token")
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer explicit-token"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("environment", [False, True])
def test_default_topic_selection(invoke, monkeypatch, environment):
    if environment:
        monkeypatch.setenv("COS_NTFY_DEFAULT_TOPIC", " env-topic ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS):
        result = invoke("send", server=main.DEFAULT_SERVER, text="hello")
    assert result["topic"] == ("env-topic" if environment else "default-topic")


@pytest.mark.parametrize("arguments", [
    {"server": "file:///fixture", "topic": "alerts", "text": "hello"},
    {"server": SITE, "topic": "alerts", "text": "hello", "priority": "invalid"},
    {"server": SITE, "topic": "alerts", "text": "   "},
])
def test_invalid_request_does_not_send(invoke, arguments):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", **arguments)
    assert result["ok"] is False
    transport.assert_not_called()


def test_missing_topic_does_not_send(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, None)), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", server=SITE, text="hello") == {"ok": False, "error": "topic required"}
    transport.assert_not_called()


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(SITE, 403, "Forbidden", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", server=SITE, topic="alerts", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_text_limit_is_preserved(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", server=SITE, topic="alerts", text="x" * (main.SOFT_LEN + 1))
    assert transport.call_args.kwargs["body"].decode() == "x" * (main.SOFT_LEN - 1) + "\u2026"


def test_status_reports_configuration_without_network_or_token(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status", server=SITE)
    assert result["server"] == SITE
    assert result["default_topic"] == "default-topic"
    assert result["token_configured"] is True
    assert result["running"] is False
    assert "stored-token" not in json.dumps(result)
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
