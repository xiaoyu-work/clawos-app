"""Teams webhook contracts through direct and manifest SDK dispatch."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_teams_main")
WEBHOOK = "https://teams.example.test/workflows/fixture?sig=fixture-key"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.delenv("COS_TEAMS_WEBHOOK_URL", raising=False)
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_teams_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-teams.send", "gateway-teams.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-teams.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


@pytest.mark.parametrize(("argv", "expected"), [
    (["hello", "--recipient", "channel", "--title", "Title", "--legacy"],
     ("channel", "hello", "Title", True)),
    (["hello"], ("", "hello", "", False)),
    (["hello", "--legacy=false"], ("", "hello", "", False)),
    (["--", "--literal"], ("", "--literal", "", False)),
])
def test_list_dispatch_forwards_manifest_options(argv, expected):
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv) == {"ok": True}
    send.assert_called_once_with(*expected)


def test_removed_leading_recipient_is_rejected():
    with mock.patch.object(main, "_send") as send:
        result = main.run("send", ["channel", "hello"])
    assert result["ok"] is False
    assert "too many positional arguments" in result["error"]
    send.assert_not_called()


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
@pytest.mark.parametrize("recipient", [None, "another-channel"])
def test_default_adaptive_card_cannot_retarget_webhook(invoke, text, recipient):
    arguments = {} if recipient is None else {"recipient": recipient}
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(202, {}, b"accepted")) as transport:
        result = invoke("send", text=text, **arguments)
    assert result == {
        "ok": True, "platform": "teams", "informational_recipient": recipient,
        "card_kind": "adaptive", "response": "accepted",
    }
    assert transport.call_args.args == ("POST", WEBHOOK)
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.5",
                "body": [{"type": "TextBlock", "text": text, "wrap": True}],
            },
        }],
    }
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    main._load_credential.assert_called_once_with("teams_webhook_url")
    main.gateway_memory.remember_send.assert_called_once_with(
        "teams", result, channel_id=recipient or "", text=text,
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_explicit_card_kind_and_trimmed_title(invoke, legacy):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"1")) as transport:
        result = invoke("send", text="body", title=" --urgent ", legacy=legacy)
    payload = json.loads(transport.call_args.kwargs["body"])
    assert result["card_kind"] == ("messagecard" if legacy else "adaptive")
    if legacy:
        assert payload == {
            "@type": "MessageCard", "@context": "https://schema.org/extensions",
            "text": "body", "title": "--urgent",
        }
    else:
        assert payload["attachments"][0]["content"]["body"] == [
            {"type": "TextBlock", "text": "--urgent", "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "text": "body", "wrap": True},
        ]


def test_environment_webhook_takes_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_TEAMS_WEBHOOK_URL", " https://override.example.test/hook ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(202, {}, b"")) as transport:
        assert invoke("send", text="hello")["ok"] is True
    assert transport.call_args.args == ("POST", "https://override.example.test/hook")
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("legacy", [False, True])
def test_text_limit_is_preserved(invoke, legacy):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"1")) as transport:
        invoke("send", text="x" * (main.SOFT_LEN + 1), legacy=legacy)
    payload = json.loads(transport.call_args.kwargs["body"])
    text = payload["text"] if legacy else payload["attachments"][0]["content"]["body"][0]["text"]
    assert text == "x" * (main.SOFT_LEN - 1) + "\u2026"


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_errors_do_not_trigger_automatic_legacy_fallback(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(WEBHOOK, 400, "Bad Request", {}, io.BytesIO(b"rejected fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]) as transport:
        result = invoke("send", text="hello")
    assert result["ok"] is False
    assert result["card_kind"] == "adaptive"
    assert "fixture" in result["error"]
    transport.assert_called_once()


def test_missing_webhook_stops_before_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", text="hello") == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


@pytest.mark.parametrize("configured", [False, True])
def test_status_is_outbound_only_and_does_not_disclose_webhook(invoke, configured):
    credential = (WEBHOOK, None) if configured else (None, "missing fixture")
    with mock.patch.object(main, "_load_credential", return_value=credential), mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is configured
    assert result["config_error"] == credential[1]
    assert result["running"] is False
    assert "fixture-key" not in json.dumps(result)
    main.gateway_memory.remember_send.assert_not_called()
    transport.assert_not_called()
