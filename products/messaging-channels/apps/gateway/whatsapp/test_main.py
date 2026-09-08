"""WhatsApp Cloud API contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_whatsapp_main")
CREDENTIALS = {
    "whatsapp_access_token": "fixture-token",
    "whatsapp_phone_number_id": "987654321",
}
SUCCESS = (200, {}, b'{"messages":[{"id":"wamid.fixture"}]}')


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_WHATSAPP_TOKEN", "COS_WHATSAPP_PHONE_NUMBER_ID"):
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_whatsapp_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-whatsapp.send", "gateway-whatsapp.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-whatsapp.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("recipient", ["12025550101", "+1 (202) 555-0101"])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_separates_sender_id_and_recipient_number(invoke, recipient, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        result = invoke("send", recipient_phone=recipient, text=text)
    assert result == {"ok": True, "platform": "whatsapp", "to": "12025550101", "wamid": "wamid.fixture"}
    assert transport.call_args.args == (
        "POST", "https://graph.facebook.com/v21.0/987654321/messages",
    )
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": "12025550101", "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    assert kwargs["headers"]["Authorization"] == "Bearer fixture-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 15
    assert kwargs["verb_id"] == "net.dial"
    assert main._load_credential.call_args_list == [mock.call(name) for name in CREDENTIALS]
    main.gateway_memory.remember_send.assert_called_once_with(
        "whatsapp", result, channel_id=recipient, text=text,
    )


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_WHATSAPP_TOKEN", " override-fixture ")
    monkeypatch.setenv("COS_WHATSAPP_PHONE_NUMBER_ID", " 123456789 ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        assert invoke("send", recipient_phone="+12025550101", text="hello")["ok"] is True
    assert transport.call_args.args[1] == "https://graph.facebook.com/v21.0/123456789/messages"
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer override-fixture"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("missing", list(CREDENTIALS))
def test_missing_credentials_stop_before_network(invoke, missing):
    def credential(name):
        return (None, "missing fixture") if name == missing else (CREDENTIALS[name], None)

    with mock.patch.object(main, "_load_credential", side_effect=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", recipient_phone="+12025550101", text="hello") == {
            "ok": False, "error": "missing fixture",
        }
    transport.assert_not_called()


@pytest.mark.parametrize(("recipient", "text"), [
    ("", "hello"), ("not-a-phone", "hello"), ("+12025550101", "   "),
])
def test_invalid_input_stops_before_credentials_and_network(invoke, recipient, text):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", recipient_phone=recipient, text=text)
    assert result["ok"] is False
    main._load_credential.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(
            main.GRAPH_API, 400, "Bad Request", {}, io.BytesIO(b'{"error":{"message":"rejected fixture"}}'),
        ),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", recipient_phone="+12025550101", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


@pytest.mark.parametrize("length", [main.SOFT_LEN, main.SOFT_LEN + 1])
def test_text_limit_is_preserved(invoke, length):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=SUCCESS) as transport:
        invoke("send", recipient_phone="+12025550101", text="x" * length)
    expected = "x" * length if length == main.SOFT_LEN else "x" * (main.SOFT_LEN - 1) + "\u2026"
    assert json.loads(transport.call_args.kwargs["body"])["text"]["body"] == expected


def test_status_has_no_credentials_network_or_webhook_receiver(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result == {
        "ok": True, "platform": "whatsapp", "running": False, "api_version": "v21.0",
        "note": "Outbound-only mode. Webhook receiver not yet implemented.",
    }
    main._load_credential.assert_not_called()
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
