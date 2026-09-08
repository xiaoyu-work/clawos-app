"""Pushover delivery contracts through direct and manifest SDK dispatch."""

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


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_pushover_main")
CREDENTIALS = {"pushover_app_token": "app-fixture", "pushover_user_key": "user-fixture"}
SUCCESS = (200, {}, b'{"status":1,"request":"request-fixture","receipt":"receipt-fixture"}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_PUSHOVER_APP_TOKEN", "COS_PUSHOVER_USER_KEY"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_pushover_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-pushover.send", "gateway-pushover.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-pushover.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_list_dispatch_forwards_manifest_options():
    argv = [
        "hello", "--recipient", "user", "--title", "Title", "--priority", "2",
        "--sound", "magic", "--url", "https://x", "--url-title", "Open",
        "--device", "phone", "--html", "--ttl", "60", "--retry", "30", "--expire", "120",
    ]
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv) == {"ok": True}
    send.assert_called_once_with(
        "hello", recipient="user", title="Title", priority=2, sound="magic",
        url="https://x", url_title="Open", device="phone", html=True, ttl=60, retry=30, expire=120,
    )


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("text", ["hello + world & more=\n", "--literal", "\u4f60\u597d"])
def test_default_send_uses_separate_app_and_recipient_keys(invoke, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", text=text)
    assert result == {
        "ok": True, "platform": "pushover", "request_id": "request-fixture",
        "status": 1, "errors": None, "receipt": "receipt-fixture",
    }
    assert transport.call_args.args == ("POST", "https://api.pushover.net/1/messages.json")
    kwargs = transport.call_args.kwargs
    assert urllib.parse.parse_qs(kwargs["body"].decode()) == {
        "token": ["app-fixture"], "user": ["user-fixture"], "message": [text],
    }
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with("pushover", result, channel_id="", text=text)


def test_emergency_send_forwards_options_without_local_retry(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke(
            "send", text="body", recipient="group-fixture", title="Title", priority=2,
            retry=30, expire=10800, sound="magic", url="https://action.example.test",
            url_title="Open", device="phone,tablet", html=True, ttl=60,
        )
    assert result["receipt"] == "receipt-fixture"
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode()) == {
        "token": ["app-fixture"], "user": ["group-fixture"], "message": ["body"],
        "title": ["Title"], "priority": ["2"], "retry": ["30"], "expire": ["10800"],
        "sound": ["magic"], "url": ["https://action.example.test"], "url_title": ["Open"],
        "device": ["phone,tablet"], "html": ["1"], "ttl": ["60"],
    }
    transport.assert_called_once()
    main._load_credential.assert_called_once_with("pushover_app_token")


@pytest.mark.parametrize("options", [
    {"priority": -3}, {"priority": 3}, {"priority": 2},
    {"priority": 2, "retry": 30}, {"priority": 2, "expire": 60},
    {"priority": 2, "retry": 29, "expire": 60},
    {"priority": 2, "retry": 30, "expire": 10801},
])
def test_priority_and_emergency_constraints_stop_before_network(invoke, options):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", text="hello", **options)
    assert result["ok"] is False
    transport.assert_not_called()


@pytest.mark.parametrize("priority", [-2, -1, 0, 1])
def test_nonemergency_priorities_omit_retry_fields(invoke, priority):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", text="hello", priority=priority, retry=30, expire=60)
    fields = urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())
    assert fields["priority"] == [str(priority)]
    assert "retry" not in fields and "expire" not in fields


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_PUSHOVER_APP_TOKEN", " env-app ")
    monkeypatch.setenv("COS_PUSHOVER_USER_KEY", " env-user ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        assert invoke("send", text="hello")["ok"] is True
    fields = urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())
    assert fields["token"] == ["env-app"] and fields["user"] == ["env-user"]
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_credentials_stop_before_network(invoke, missing):
    def credential(name):
        return (None, "missing fixture") if name == missing else (CREDENTIALS[name], None)

    with mock.patch.object(main, "_load_credential", side_effect=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize("raw", [b'{"status":0,"errors":["rejected"]}', b"{}", b"[]", b"not JSON"])
def test_api_failure_is_not_http_success(invoke, raw):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        assert invoke("send", text="hello")["ok"] is False


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(main.API_URL, 400, "Bad Request", {}, io.BytesIO(b"rejected fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_message_and_metadata_limits_are_preserved(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke(
            "send", text="x" * (main.SOFT_LEN + 1), title="x" * (main.TITLE_LEN + 1),
            url="x" * (main.URL_LEN + 1), url_title="x" * (main.URL_TITLE_LEN + 1),
        )
    fields = urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())
    for name, limit in (
        ("message", main.SOFT_LEN), ("title", main.TITLE_LEN),
        ("url", main.URL_LEN), ("url_title", main.URL_TITLE_LEN),
    ):
        assert fields[name] == ["x" * (limit - 1) + "\u2026"]


@pytest.mark.parametrize("configured", [False, True])
def test_status_does_not_contact_service_or_disclose_credentials(invoke, configured):
    with mock.patch.object(
        main, "_load_credential",
        side_effect=lambda name: (CREDENTIALS[name], None) if configured else (None, "missing fixture"),
    ), mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["configured"] is configured
    assert result["running"] is False
    assert result["config_error"] == (None if configured else "missing fixture")
    assert all(value not in json.dumps(result) for value in CREDENTIALS.values())
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
