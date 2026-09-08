"""Mattermost webhook contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_mattermost_main")
WEBHOOK = "https://mattermost.example.test/hooks/fixture"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.delenv("COS_MATTERMOST_WEBHOOK_URL", raising=False)
    with mock.patch.object(main, "_load_credential", return_value=(WEBHOOK, None)), mock.patch.object(
        main.gateway_memory, "remember_send",
    ):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_mattermost_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-mattermost.send", "gateway-mattermost.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-mattermost.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


@pytest.mark.parametrize(("argv", "expected"), [
    (["hello", "--recipient", "town-square", "--username", "bot", "--icon-url", "https://x"],
     ("town-square", "hello", "bot", "https://x")),
    (["hello"], ("", "hello", "", "")),
    (["--", "--literal"], ("", "--literal", "", "")),
])
def test_list_dispatch_forwards_manifest_options(argv, expected):
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv) == {"ok": True}
    send.assert_called_once_with(*expected)


def test_removed_leading_recipient_is_rejected():
    with mock.patch.object(main, "_send") as send:
        result = main.run("send", ["town-square", "hello"])
    assert result["ok"] is False
    assert "too many positional arguments" in result["error"]
    send.assert_not_called()


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("recipient", [None, "town-square", "@someone"])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_preserves_channel_selection_and_message(invoke, recipient, text):
    args = {} if recipient is None else {"recipient": recipient}
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"ok")) as transport:
        result = invoke("send", text=text, **args)
    assert result == {"ok": True, "platform": "mattermost", "channel": recipient, "response": "ok"}
    expected = {"text": text}
    if recipient is not None:
        expected["channel"] = recipient
    assert transport.call_args.args == ("POST", WEBHOOK)
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == expected
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    main.gateway_memory.remember_send.assert_called_once_with(
        "mattermost", result, channel_id=recipient or "", text=text,
    )


def test_username_icon_and_environment_override(invoke, monkeypatch):
    monkeypatch.setenv("COS_MATTERMOST_WEBHOOK_URL", " https://override.example.test/hook ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"ok")) as transport:
        invoke("send", text="hello", recipient="@someone", username=" --bot ", icon_url=" https://icons.example.test/bot.png ")
    assert transport.call_args.args == ("POST", "https://override.example.test/hook")
    assert json.loads(transport.call_args.kwargs["body"]) == {
        "text": "hello", "channel": "@someone", "username": "--bot",
        "icon_url": "https://icons.example.test/bot.png",
    }
    main._load_credential.assert_not_called()


def test_long_text_retains_existing_limit(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"ok")) as transport:
        invoke("send", text="x" * (main.SOFT_LEN + 1))
    assert json.loads(transport.call_args.kwargs["body"])["text"] == "x" * (main.SOFT_LEN - 1) + "\u2026"


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(WEBHOOK, 403, "Forbidden", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_missing_webhook_stops_before_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize("configured", [False, True])
def test_status_is_outbound_only_and_does_not_disclose_webhook(invoke, configured):
    credential = (WEBHOOK, None) if configured else (None, "missing fixture")
    with mock.patch.object(main, "_load_credential", return_value=credential) as credentials, mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is configured
    assert result["config_error"] == credential[1]
    assert result["running"] is False
    assert WEBHOOK not in json.dumps(result)
    credentials.assert_called_once_with("mattermost_webhook_url")
    transport.assert_not_called()
