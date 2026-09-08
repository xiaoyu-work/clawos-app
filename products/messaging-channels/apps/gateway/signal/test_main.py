"""Signal REST connector contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_signal_main")
BASE_URL = "https://signal.example.test"
NUMBER = "+12025550100"
CREDENTIALS = {"signal_base_url": BASE_URL + "/", "signal_number": NUMBER}


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_SIGNAL_BASE_URL", "COS_SIGNAL_NUMBER", "COS_GATEWAY_ALLOW_PRIVATE"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_signal_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-signal.send", "gateway-signal.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-signal.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("recipient", "normalized"), [
    ("+12025550101", "+12025550101"),
    ("+1 (202) 555-0101", "+12025550101"),
    ("group.abcdefghijklmnopqrstuvwxyz==", "group.abcdefghijklmnopqrstuvwxyz=="),
])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_preserves_numbers_groups_and_message(invoke, recipient, normalized, text):
    with mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"timestamp":"fixture-time"}'),
    ) as transport:
        result = invoke("send", recipient=recipient, text=text)
    assert result == {
        "ok": True, "platform": "signal", "recipient": normalized,
        "number": NUMBER, "base_url": BASE_URL, "timestamp": "fixture-time",
    }
    assert transport.call_args.args == ("POST", BASE_URL + "/v2/send")
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"message": text, "number": NUMBER, "recipients": [normalized]}
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with(
        "signal", result, channel_id=recipient, text=text,
    )


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_SIGNAL_BASE_URL", " https://override.example.test/// ")
    monkeypatch.setenv("COS_SIGNAL_NUMBER", " +12025550102 ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        result = invoke("send", recipient="+12025550101", text="hello")
    assert result["ok"] is True
    assert transport.call_args.args[1] == "https://override.example.test/v2/send"
    assert json.loads(transport.call_args.kwargs["body"])["number"] == "+12025550102"
    main._load_credential.assert_not_called()


def test_missing_number_stops_before_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")) as credentials, mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", recipient="+12025550101", text="hello") == {
            "ok": False, "error": "missing fixture",
        }
    credentials.assert_called_once_with("signal_number")
    transport.assert_not_called()


def test_short_non_phone_recipient_is_rejected(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", recipient="invalid", text="hello")
    assert result["ok"] is False
    assert "E.164 or group id" in result["error"]
    transport.assert_not_called()


def test_private_rest_server_is_not_automatically_authorized(invoke, monkeypatch):
    monkeypatch.setenv("COS_SIGNAL_BASE_URL", "http://127.0.0.1:8080")
    with mock.patch.object(main.safe_egress, "_resolve_targets") as resolve:
        result = invoke("send", recipient="+12025550101", text="hello")
    assert result["ok"] is False
    assert "egress blocked" in result["error"]
    assert "COS_GATEWAY_ALLOW_PRIVATE" in result["error"]
    assert "COS_GATEWAY_ALLOW_PRIVATE" not in os.environ
    resolve.assert_not_called()


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(BASE_URL, 403, "Forbidden", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", recipient="+12025550101", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_long_text_retains_existing_limit(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        invoke("send", recipient="+12025550101", text="x" * (main.SOFT_LEN + 1))
    assert json.loads(transport.call_args.kwargs["body"])["message"] == "x" * (main.SOFT_LEN - 1) + "\u2026"


def test_status_does_not_poll_or_contact_server(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["running"] is False
    assert result["number"] == NUMBER
    assert result["base_url"] == BASE_URL
    assert "/v1/receive polling not yet implemented" in result["note"]
    transport.assert_not_called()


def test_status_preserves_unconfigured_account_and_default_url(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")):
        result = invoke("status")
    assert result["configured"] is False
    assert result["number"] is None
    assert result["config_error"] == "missing fixture"
    assert result["base_url"] == "http://localhost:8080"
