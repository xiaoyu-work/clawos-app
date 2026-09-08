"""Home Assistant REST contracts without contacting a server or devices."""

import io
import json
import os
from pathlib import Path
import socket
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_homeassistant_main")
CREDENTIALS = {
    "homeassistant_url": "https://ha.example.test/",
    "homeassistant_token": "token-fixture",
}
SUCCESS = (200, {}, b'[{"entity_id":"light.fixture","state":"on"}]')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_HOMEASSISTANT_URL", "COS_HOMEASSISTANT_TOKEN", "COS_GATEWAY_ALLOW_PRIVATE"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_homeassistant_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-homeassistant.send", "gateway-homeassistant.call", "gateway-homeassistant.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-homeassistant.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


@pytest.mark.parametrize("service,endpoint", [
    ("notify", "notify/notify"), ("notify.mobile_app_fixture", "notify/mobile_app_fixture"),
])
@pytest.mark.parametrize("text", ["hello", "--literal", "\u4f60\u597d\nworld"])
def test_send_payload_and_notify_shorthand(invoke, service, endpoint, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", service=service, text=text, title=" Fixture ")
    assert result["ok"] is True
    assert result["service"] == endpoint.replace("/", ".")
    assert result["result"] == json.loads(SUCCESS[2])
    assert transport.call_args.args == ("POST", f"https://ha.example.test/api/services/{endpoint}")
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"message": text, "title": "Fixture"}
    assert kwargs["headers"]["Authorization"] == "Bearer token-fixture"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20 and kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with(
        "homeassistant", result, channel_id=service, text=text,
    )


def test_call_forwards_object_without_send_memory(invoke):
    payload = {"entity_id": ["light.fixture"], "brightness": 42, "transition": 0.5}
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("call", service="light.turn_on", json=json.dumps(payload))
    assert result["ok"] is True
    assert transport.call_args.args[1].endswith("/api/services/light/turn_on")
    assert json.loads(transport.call_args.kwargs["body"]) == payload
    main.gateway_memory.remember_send.assert_not_called()


def test_legacy_direct_call_accepts_object_payload():
    with mock.patch.object(main, "_post_service", return_value={"ok": True}) as post:
        assert main.run("call", {"service": "light.turn_on", "json": {"entity_id": "light.fixture"}})["ok"]
    post.assert_called_once_with("light", "turn_on", {"entity_id": "light.fixture"})


@pytest.mark.parametrize("argv", [
    ["notify", "hello", "--title", "Fixture"],
    ["--title=Fixture", "--", "notify", "hello"],
    ["--title", "Fixture", "notify", "hello"],
])
def test_canonical_options_do_not_displace_service_or_text(argv):
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv)["ok"]
    send.assert_called_once_with("notify", "hello", "Fixture")


@pytest.mark.parametrize("command,argv", [
    ("send", ["notify", "hello", "extra"]),
    ("send", ["notify", "hello", "--unknown"]),
    ("send", ["notify", "hello", "--title"]),
    ("call", ["light.turn_on", "{}", "extra"]),
    ("call", ["light.turn_on", "{}", "--unknown"]),
])
def test_invalid_direct_argv_is_not_silently_ignored(command, argv):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert main.run(command, argv)["ok"] is False
    transport.assert_not_called()
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("command,arguments", [
    ("send", {"service": "light.turn_on", "text": "hello"}),
    ("send", {"service": "notify", "text": " "}),
    ("call", {"service": "light", "json": "{}"}),
    ("call", {"service": ".turn_on", "json": "{}"}),
    ("call", {"service": "light.", "json": "{}"}),
    ("call", {"service": "light.turn_on", "json": "not-json"}),
    ("call", {"service": "light.turn_on", "json": "[]"}),
    ("call", {"service": "light.turn_on", "json": "null"}),
    ("call", {"service": "light.turn_on", "json": "42"}),
])
def test_invalid_payload_or_service_stops_before_configuration(invoke, command, arguments):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert invoke(command, **arguments)["ok"] is False
    transport.assert_not_called()
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_configuration_stops_before_network(invoke, missing):
    with mock.patch.object(
        main, "_load_credential",
        side_effect=lambda name: (None, "missing fixture") if name == missing else (CREDENTIALS[name], None),
    ), mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert invoke("send", service="notify", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


def test_environment_overrides_stored_configuration(invoke, monkeypatch):
    monkeypatch.setenv("COS_HOMEASSISTANT_URL", " https://override.example.test/// ")
    monkeypatch.setenv("COS_HOMEASSISTANT_TOKEN", " override-fixture ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", service="notify", text="hello")
    assert transport.call_args.args[1] == "https://override.example.test/api/services/notify/notify"
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer override-fixture"
    assert json.loads(transport.call_args.kwargs["body"]) == {"message": "hello"}
    main._load_credential.assert_not_called()


def test_non_http_base_is_rejected(invoke, monkeypatch):
    monkeypatch.setenv("COS_HOMEASSISTANT_URL", "file:///fixture")
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        assert invoke("send", service="notify", text="hello")["ok"] is False
    transport.assert_not_called()


@pytest.mark.parametrize("raw,expected", [(b'{"ok":true}', {"ok": True}), (b"accepted", "accepted")])
def test_response_keeps_json_or_text(invoke, raw, expected):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        result = invoke("call", service="light.turn_on", json="{}")
    assert result["result"] == expected


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_errors_are_structured(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError("https://ha.example.test", 401, "Unauthorized", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("call", service="light.turn_on", json="{}")
    assert result["ok"] is False
    assert result["service"] == "light.turn_on"
    assert "fixture" in result["error"]


def test_private_endpoint_remains_blocked(invoke, monkeypatch):
    monkeypatch.setenv("COS_HOMEASSISTANT_URL", "http://127.0.0.1:8123")
    answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8123))]
    with mock.patch.object(main.safe_egress.egress, "available", return_value=False), \
         mock.patch.object(main.safe_egress.socket, "getaddrinfo", return_value=answers), \
         mock.patch.object(main.safe_egress, "_open_pinned_socket") as connect:
        result = invoke("call", service="light.turn_on", json="{}")
    assert result["ok"] is False and "non-public" in result["error"]
    connect.assert_not_called()


@pytest.mark.parametrize("configured", [False, True])
def test_status_is_configuration_only_and_omits_token(invoke, configured):
    with mock.patch.object(
        main, "_load_credential",
        side_effect=lambda name: (CREDENTIALS[name], None) if configured else (None, "missing fixture"),
    ), mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["configured"] is configured
    assert result["base"] == ("https://ha.example.test" if configured else None)
    assert result["config_error"] == (None if configured else "missing fixture")
    assert result["running"] is False
    assert "token-fixture" not in json.dumps(result)
    transport.assert_not_called()
    main.gateway_memory.remember_send.assert_not_called()
