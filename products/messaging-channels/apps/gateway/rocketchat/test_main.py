"""Rocket.Chat REST contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_rocketchat_main")
SITE = "https://rocket.example.test"
CREDENTIALS = {
    "rocketchat_site": SITE + "/",
    "rocketchat_user_id": "fixture-user",
    "rocketchat_token": "fixture-token",
}


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_ROCKETCHAT_SITE", "COS_ROCKETCHAT_USER_ID", "COS_ROCKETCHAT_TOKEN"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_rocketchat_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-rocketchat.send", "gateway-rocketchat.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-rocketchat.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("target", ["general", "#general", "@someone"])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_preserves_target_and_auth_headers(invoke, target, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(
        200, {}, b'{"success":true,"message":{"_id":"message-1","ts":"fixture-time"}}',
    )) as transport:
        result = invoke("send", target=target, text=text)
    assert result == {
        "ok": True, "platform": "rocketchat", "site": SITE, "channel": target,
        "id": "message-1", "ts": "fixture-time", "raw": None,
    }
    assert transport.call_args.args == ("POST", SITE + "/api/v1/chat.postMessage")
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"channel": target, "text": text}
    assert kwargs["headers"]["X-Auth-Token"] == "fixture-token"
    assert kwargs["headers"]["X-User-Id"] == "fixture-user"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with("rocketchat", result, channel_id=target, text=text)


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_ROCKETCHAT_SITE", " https://override.example.test/// ")
    monkeypatch.setenv("COS_ROCKETCHAT_USER_ID", " override-user ")
    monkeypatch.setenv("COS_ROCKETCHAT_TOKEN", " override-token ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"success":true}')) as transport:
        result = invoke("send", target="#general", text="hello")
    assert result["ok"] is True
    assert transport.call_args.args[1] == "https://override.example.test/api/v1/chat.postMessage"
    assert transport.call_args.kwargs["headers"]["X-Auth-Token"] == "override-token"
    assert transport.call_args.kwargs["headers"]["X-User-Id"] == "override-user"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_credentials_stop_before_network(invoke, missing):
    def credential(name):
        return (None, "missing fixture") if name == missing else (CREDENTIALS[name], None)

    with mock.patch.object(main, "_load_credential", side_effect=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", target="#general", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


def test_invalid_site_scheme_stops_before_network(invoke, monkeypatch):
    monkeypatch.setenv("COS_ROCKETCHAT_SITE", "file:///fixture")
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", target="#general", text="hello")
    assert result["ok"] is False
    assert "http(s)" in result["error"]
    transport.assert_not_called()


@pytest.mark.parametrize("raw", [b'{"success":false,"error":"rejected"}', b"not JSON", b"[]"])
def test_remote_failure_is_not_success(invoke, raw):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        result = invoke("send", target="#general", text="hello")
    assert result["ok"] is False
    assert result["raw"] is not None


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(SITE, 403, "Forbidden", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", target="#general", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_long_text_retains_existing_limit(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"success":true}')) as transport:
        invoke("send", target="#general", text="x" * (main.SOFT_LEN + 1))
    assert json.loads(transport.call_args.kwargs["body"])["text"] == "x" * (main.SOFT_LEN - 1) + "\u2026"


def test_status_is_outbound_only_and_never_returns_access_token(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["running"] is False
    assert result["configured"] is True
    assert result["site"] == SITE
    assert result["user_id"] == "fixture-user"
    assert "fixture-token" not in json.dumps(result)
    transport.assert_not_called()
