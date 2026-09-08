"""Lark/Feishu webhook and signature contracts through direct and SDK dispatch."""

import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_larksuite_main")
WEBHOOK = "https://open.example.test/open-apis/bot/v2/hook/fixture"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_LARK_WEBHOOK_URL", "COS_LARK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with mock.patch.object(
        main, "_load_credential",
        side_effect=lambda name: (WEBHOOK, None) if name == "lark_webhook_url" else (None, None),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_larksuite_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-larksuite.send", "gateway-larksuite.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-larksuite.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_list_dispatch_forwards_manifest_options():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", [
            "hello", "--post", "--title", "Title", "--card", "--card-json", "{}",
        ]) == {"ok": True}
    send.assert_called_once_with("hello", post=True, title="Title", card=True, card_json="{}")


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("timestamp", "expected"), [
    ("100", "jquNHnVOwmDRfw+vqTIrY5dooJAgi5EcRtLsQE4wfXg="),
    ("1599360473", "l1N0gAcBjdwBvGm1xMjOF0XSyaLRpR7tuO5dHfhAYc8="),
])
def test_signature_uses_timestamp_secret_key_and_empty_message(timestamp, expected):
    # Official custom-bot algorithm, with known answers independently computed using Node crypto.
    assert main._sign(timestamp, "demo") == expected


@pytest.mark.parametrize("text", ["hello", "--literal", "\u4f60\u597d"])
def test_plain_send_defaults(invoke, text):
    with mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"code":0,"msg":"success"}'),
    ) as transport:
        result = invoke("send", text=text)
    assert result["ok"] is True
    assert result["kind"] == "text"
    assert result["signed"] is False
    assert transport.call_args.args == ("POST", WEBHOOK)
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"msg_type": "text", "content": {"text": text}}
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with("larksuite", result, channel_id="", text=text)


@pytest.mark.parametrize("mode", ["text", "post", "interactive"])
def test_signed_requests_use_seconds_and_official_signature(invoke, monkeypatch, mode):
    monkeypatch.setenv("COS_LARK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("COS_LARK_SECRET", "demo")
    args = {}
    if mode == "post":
        args = {"post": True, "title": "--urgent"}
    elif mode == "interactive":
        args = {"post": True, "card": True, "card_json": '{"elements":[]}'}
    with mock.patch.object(main.time, "time", return_value=1599360473.75), mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"code":0}'),
    ) as transport:
        result = invoke("send", text="body", **args)
    payload = json.loads(transport.call_args.kwargs["body"])
    assert result["ok"] is True
    assert result["kind"] == mode
    assert result["signed"] is True
    assert payload["timestamp"] == "1599360473"
    assert payload["sign"] == "l1N0gAcBjdwBvGm1xMjOF0XSyaLRpR7tuO5dHfhAYc8="
    assert payload["msg_type"] == mode
    if mode == "post":
        assert payload["content"] == {"post": {"zh_cn": {
            "title": "--urgent", "content": [[{"tag": "text", "text": "body"}]],
        }}}
    elif mode == "interactive":
        assert payload["card"] == {"elements": []}
        assert "content" not in payload
    main._load_credential.assert_not_called()


def test_rich_text_defaults_title_from_first_line(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"code":0}')) as transport:
        invoke("send", text="First\nSecond", post=True)
    content = json.loads(transport.call_args.kwargs["body"])["content"]["post"]["zh_cn"]
    assert content["title"] == "First"
    assert content["content"] == [[{"tag": "text", "text": "First\nSecond"}]]


@pytest.mark.parametrize("card_json", [None, "{invalid"])
def test_card_requires_valid_json_before_network(invoke, card_json):
    args = {} if card_json is None else {"card_json": card_json}
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("send", text="unused", card=True, **args)
    assert result["ok"] is False
    assert "--card-json" in result["error"]
    transport.assert_not_called()


@pytest.mark.parametrize("raw", [b'{"code":19021,"msg":"signature rejected"}', b"not JSON", b"[]"])
def test_remote_failure_is_not_success(invoke, raw):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        assert invoke("send", text="hello")["ok"] is False


@pytest.mark.parametrize("error", [
    main.safe_egress.EgressBlocked("blocked fixture"), urllib.error.URLError("unavailable fixture"),
])
def test_transport_failure_is_reported(invoke, error):
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=error):
        result = invoke("send", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_missing_webhook_stops_before_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize("signed", [False, True])
def test_status_is_outbound_only_and_does_not_disclose_credentials(invoke, monkeypatch, signed):
    if signed:
        monkeypatch.setenv("COS_LARK_SECRET", "fixture-secret")
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["running"] is False
    assert result["signed"] is signed
    assert WEBHOOK not in json.dumps(result)
    assert "fixture-secret" not in json.dumps(result)
    transport.assert_not_called()
