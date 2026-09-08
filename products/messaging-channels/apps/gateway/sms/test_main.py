"""Twilio SMS contracts through direct and manifest SDK dispatch."""

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


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_sms_main")
CREDENTIALS = {
    "twilio_account_sid": "ACfixture",
    "twilio_auth_token": "fixture-token",
    "twilio_from": "+1 (202) 555-0100",
}
SUCCESS = (201, {}, b'{"sid":"SMfixture","status":"queued","num_segments":"1"}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_TWILIO_ACCOUNT_SID", "COS_TWILIO_AUTH_TOKEN", "COS_TWILIO_FROM"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_sms_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-sms.send", "gateway-sms.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-sms.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("sender", "field", "normalized"), [
    ("+1 (202) 555-0100", "From", "+12025550100"),
    ("MGfixture", "MessagingServiceSid", "MGfixture"),
])
@pytest.mark.parametrize("text", ["hello + world & more=\n", "--literal", "\u4f60\u597d"])
def test_send_encodes_form_and_preserves_sender_selection(invoke, monkeypatch, sender, field, normalized, text):
    monkeypatch.setenv("COS_TWILIO_FROM", sender)
    recipient = "+1 (202) 555-0101"
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", to=recipient, text=text)
    assert result == {
        "ok": True, "platform": "sms", "to": "+12025550101", "from": normalized,
        "sid": "SMfixture", "status": "queued", "num_segments": "1",
    }
    assert transport.call_args.args == (
        "POST", "https://api.twilio.com/2010-04-01/Accounts/ACfixture/Messages.json",
    )
    kwargs = transport.call_args.kwargs
    assert urllib.parse.parse_qs(kwargs["body"].decode()) == {
        "To": ["+12025550101"], "Body": [text], field: [normalized],
    }
    scheme, auth = kwargs["headers"]["Authorization"].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(auth).decode() == "ACfixture:fixture-token"
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert kwargs["headers"]["Accept"] == "application/json"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with(
        "sms", result, channel_id=recipient, text=text,
    )


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_TWILIO_ACCOUNT_SID", " ACoverride ")
    monkeypatch.setenv("COS_TWILIO_AUTH_TOKEN", " override-token ")
    monkeypatch.setenv("COS_TWILIO_FROM", " MGoverride ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", to="+12025550101", text="hello")
    assert result["ok"] is True
    assert transport.call_args.args[1].endswith("/Accounts/ACoverride/Messages.json")
    auth = transport.call_args.kwargs["headers"]["Authorization"].split(" ", 1)[1]
    assert base64.b64decode(auth).decode() == "ACoverride:override-token"
    assert result["from"] == "MGoverride"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_credentials_stop_before_network(invoke, missing):
    def credential(name):
        return (None, "missing fixture") if name == missing else (CREDENTIALS[name], None)

    with mock.patch.object(main, "_load_credential", side_effect=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", to="+12025550101", text="hello") == {
            "ok": False, "error": "missing fixture",
        }
    transport.assert_not_called()


@pytest.mark.parametrize("recipient", ["12025550101", "+123", "invalid"])
def test_invalid_recipient_stops_before_network(invoke, recipient):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", to=recipient, text="hello")
    assert result["ok"] is False
    assert "to must be E.164" in result["error"]
    transport.assert_not_called()


@pytest.mark.parametrize(("recipient", "text"), [("", "hello"), ("+12025550101", "   ")])
def test_empty_input_stops_before_credentials_and_network(invoke, recipient, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", to=recipient, text=text)
    assert result["ok"] is False
    main._load_credential.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(
            main.TWILIO_API, 400, "Bad Request", {}, io.BytesIO(b'{"message":"invalid fixture"}'),
        ),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", to="+12025550101", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


@pytest.mark.parametrize("length", [main.SOFT_LEN, main.SOFT_LEN + 1])
def test_text_limit_is_preserved(invoke, length):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", to="+12025550101", text="x" * length)
    expected = "x" * length if length == main.SOFT_LEN else "x" * (main.SOFT_LEN - 1) + "\u2026"
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())["Body"] == [expected]


def test_status_has_no_network_or_inbound_loop_and_omits_credentials(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result == {
        "ok": True, "platform": "sms", "running": False, "configured": True,
        "from": CREDENTIALS["twilio_from"], "config_error": None,
        "note": "Outbound-only mode. Inbound webhook receiver not yet implemented.",
    }
    assert CREDENTIALS["twilio_auth_token"] not in json.dumps(result)
    assert CREDENTIALS["twilio_account_sid"] not in json.dumps(result)
    main._load_credential.assert_has_calls([mock.call(name) for name in CREDENTIALS])
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()


def test_status_reports_missing_configuration(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")):
        result = invoke("status")
    assert result["configured"] is False
    assert result["from"] is None
    assert result["config_error"] == "missing fixture"
