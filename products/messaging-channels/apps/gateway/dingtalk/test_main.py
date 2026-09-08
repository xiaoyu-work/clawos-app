"""DingTalk transport contracts through direct and real manifest SDK dispatch."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error
import urllib.parse

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_dingtalk_main")
WEBHOOK = "https://oapi.dingtalk.test/robot/send?access_token=fixture"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_DINGTALK_WEBHOOK_URL", "COS_DINGTALK_SECRET", "COS_DINGTALK_KEYWORD"):
        monkeypatch.delenv(name, raising=False)
    with mock.patch.object(
        main, "_load_credential",
        side_effect=lambda name: (WEBHOOK, None) if name == "dingtalk_webhook_url" else (None, None),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_dingtalk_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-dingtalk.send", "gateway-dingtalk.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-dingtalk.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_list_dispatch_forwards_manifest_options():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        result = main.run("send", [
            "hello", "--markdown=false", "--title=--urgent", "--keyword", "Key",
            "--at-mobiles", "1,2", "--at-user-ids", "u1,u2", "--at-all",
        ])
    assert result == {"ok": True}
    send.assert_called_once_with(
        "hello", markdown=False, title="--urgent", keyword="Key",
        at_mobiles=["1", "2"], at_user_ids=["u1", "u2"], at_all=True,
    )


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_plain_send_defaults_and_message_text(invoke, text):
    with mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"errcode":0,"errmsg":"ok"}'),
    ) as transport:
        result = invoke("send", text=text)
    assert result["ok"] is True
    assert result["kind"] == "text"
    assert result["signed"] is False
    assert transport.call_args.args == ("POST", WEBHOOK)
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"msgtype": "text", "text": {"content": text}}
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    main.gateway_memory.remember_send.assert_called_once_with("dingtalk", result, channel_id="", text=text)


def test_signed_markdown_keyword_and_mentions(invoke, monkeypatch):
    monkeypatch.setenv("COS_DINGTALK_SECRET", "fixture-secret")
    with mock.patch.object(main.time, "time", return_value=1234.5), mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"errcode":0}'),
    ) as transport:
        result = invoke(
            "send", text="body", markdown=True, title="--urgent", keyword="Key",
            at_mobiles="1, 2", at_user_ids="u1,u2", at_all=True,
        )
    assert result["ok"] is True
    assert result["signed"] is True
    assert result["kind"] == "markdown"
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(transport.call_args.args[1]).query)
    signature = base64.b64encode(hmac.new(
        b"fixture-secret", b"1234500\nfixture-secret", hashlib.sha256,
    ).digest()).decode()
    assert query == {"access_token": ["fixture"], "timestamp": ["1234500"], "sign": [signature]}
    assert json.loads(transport.call_args.kwargs["body"]) == {
        "msgtype": "markdown", "markdown": {"title": "--urgent", "text": "Key\nbody"},
        "at": {"atMobiles": ["1", "2"], "atUserIds": ["u1", "u2"], "isAtAll": True},
    }


def test_environment_keyword_and_derived_markdown_title(invoke, monkeypatch):
    monkeypatch.setenv("COS_DINGTALK_KEYWORD", "Notice")
    with mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"errcode":0}'),
    ) as transport:
        invoke("send", text="body", markdown=True)
    assert json.loads(transport.call_args.kwargs["body"]) == {
        "msgtype": "markdown", "markdown": {"title": "Notice", "text": "Notice\nbody"},
    }


@pytest.mark.parametrize("raw", [b'{"errcode":310000,"errmsg":"rejected"}', b"not JSON", b"[]"])
def test_remote_failure_is_not_success(invoke, raw):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, raw)):
        assert invoke("send", text="hello")["ok"] is False


@pytest.mark.parametrize("error", [
    main.safe_egress.EgressBlocked("blocked fixture"),
    urllib.error.URLError("unavailable fixture"),
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
        result = invoke("send", text="hello")
    assert result == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize("signed", [False, True])
def test_status_is_outbound_only_and_does_not_disclose_credentials(invoke, monkeypatch, signed):
    monkeypatch.setenv("COS_DINGTALK_WEBHOOK_URL", WEBHOOK)
    if signed:
        monkeypatch.setenv("COS_DINGTALK_SECRET", "fixture-secret")
    with mock.patch.object(main, "_load_credential", return_value=(None, None)) as credentials, mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["running"] is False
    assert result["signed"] is signed
    assert WEBHOOK not in json.dumps(result)
    assert "fixture-secret" not in json.dumps(result)
    assert mock.call("dingtalk_webhook_url") not in credentials.call_args_list
    transport.assert_not_called()
