"""Retained Telegram send behavior through direct and manifest dispatch."""

import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error
import urllib.parse

import pytest

from test_support import authenticated_mcp_params, load_local_module

main = load_local_module(Path(__file__).with_name("main.py"), "gateway_telegram_main")
safe_subprocess = main.safe_subprocess
safe_egress = main.safe_egress


@pytest.fixture(autouse=True)
def isolated_effects(monkeypatch):
    monkeypatch.setenv("COS_BIN", "cos")
    monkeypatch.delenv("COS_TELEGRAM_TOKEN", raising=False)
    with mock.patch.object(safe_subprocess, "safe_credential_load", return_value=("fixture-token", None)), mock.patch.object(
        safe_subprocess, "safe_subprocess", side_effect=AssertionError("unexpected process"),
    ), mock.patch.object(safe_egress, "safe_urlopen", side_effect=AssertionError("unexpected network")), mock.patch.object(
        main.gateway_memory, "remember_send",
    ):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    manifest = Path(__file__).with_name("app.json")
    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(manifest)},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_telegram_server")
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        f"gateway-telegram.{name}" for name in json.loads(manifest.read_text())["operations"]
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-telegram.{command}", "arguments": arguments,
        }), True)
        return result["structuredContent"]
    return call


@pytest.mark.parametrize("chat_id", ["12345", "-10012345"])
@pytest.mark.parametrize("parts", [["hello", "world"], ["--literal"], ["\u4f60\u597d"]])
def test_send_preserves_repeatable_text_and_chat(invoke, chat_id, parts):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        result = invoke("send", chat_id=chat_id, text=parts)
    text = " ".join(parts)
    assert result == {"ok": True, "platform": "telegram", "sent_to": chat_id, "len": len(text)}
    assert transport.call_args.args == ("POST", "https://api.telegram.org/botfixture-token/sendMessage")
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode()) == {"chat_id": [chat_id], "text": [text]}
    assert transport.call_args.kwargs["timeout"] == 15
    assert transport.call_args.kwargs["verb_id"] == "net.dial"
    safe_subprocess.safe_credential_load.assert_called_once_with("telegram_bot_token", timeout=10.0, cos_bin="cos")
    main.gateway_memory.remember_send.assert_called_once_with("telegram", result, channel_id=chat_id, text=text)


def test_environment_token_still_takes_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_TELEGRAM_TOKEN", " override-fixture ")
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        assert invoke("send", chat_id="12345", text=["hello"])["ok"] is True
    assert transport.call_args.args[1] == "https://api.telegram.org/botoverride-fixture/sendMessage"
    safe_subprocess.safe_credential_load.assert_not_called()


def test_missing_token_and_provider_rejection_are_explicit(invoke):
    with mock.patch.object(safe_subprocess, "safe_credential_load", return_value=(None, "missing fixture")):
        assert invoke("send", chat_id="12345", text=["hello"])["ok"] is False
    safe_egress.safe_urlopen.assert_not_called()
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":false,"description":"rejected fixture"}')):
        assert "rejected fixture" in invoke("send", chat_id="12345", text=["hello"])["error"]


@pytest.mark.parametrize("error", [urllib.error.URLError("unavailable fixture"), safe_egress.EgressBlocked("blocked fixture")])
def test_transport_errors_and_no_direct_agent_process(invoke, error):
    with mock.patch.object(safe_egress, "safe_urlopen", side_effect=error):
        assert invoke("send", chat_id="12345", text=["hello"])["ok"] is False
    safe_subprocess.safe_subprocess.assert_not_called()


def test_existing_outbound_truncation_is_preserved(invoke):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        invoke("send", chat_id="12345", text=["x" * 4097])
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())["text"] == ["x" * 4095 + "\u2026"]
