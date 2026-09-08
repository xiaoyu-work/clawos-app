"""Google Chat webhook contracts through direct and manifest SDK dispatch."""

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


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_googlechat_main")
WEBHOOK = "https://chat.example.test/v1/spaces/fixture/messages?key=fixture-key&token=fixture-token"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.delenv("COS_GOOGLECHAT_WEBHOOK_URL", raising=False)
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
        load_local_module(Path(__file__).with_name("server.py"), "gateway_googlechat_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-googlechat.send", "gateway-googlechat.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-googlechat.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


@pytest.mark.parametrize(("argv", "expected"), [
    (["hello", "--recipient", "space", "--title", "Title", "--thread-key", "thread"],
     ("space", "hello", "Title", "thread")),
    (["hello"], ("", "hello", "", "")),
    (["--", "--literal"], ("", "--literal", "", "")),
])
def test_list_dispatch_forwards_manifest_options(argv, expected):
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", argv) == {"ok": True}
    send.assert_called_once_with(*expected)


def test_removed_leading_recipient_is_rejected():
    with mock.patch.object(main, "_send") as send:
        result = main.run("send", ["space", "hello"])
    assert result["ok"] is False
    assert "too many positional arguments" in result["error"]
    send.assert_not_called()


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_args", "gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
@pytest.mark.parametrize("recipient", [None, "another-space"])
def test_plain_send_cannot_retarget_the_webhook(invoke, text, recipient):
    arguments = {} if recipient is None else {"recipient": recipient}
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(
        200, {}, b'{"name":"spaces/fixture/messages/1"}',
    )) as transport:
        result = invoke("send", text=text, **arguments)
    assert result == {
        "ok": True, "platform": "googlechat", "informational_recipient": recipient,
        "kind": "text", "thread_key": None, "name": "spaces/fixture/messages/1",
    }
    assert transport.call_args.args == ("POST", WEBHOOK)
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"text": text}
    assert kwargs["timeout"] == 20
    assert kwargs["verb_id"] == "net.dial"
    assert kwargs["headers"]["Content-Type"] == "application/json; charset=UTF-8"
    main.gateway_memory.remember_send.assert_called_once_with(
        "googlechat", result, channel_id=recipient or "", text=text,
    )


def test_card_and_thread_replace_stale_query_options(invoke, monkeypatch):
    monkeypatch.setenv("COS_GOOGLECHAT_WEBHOOK_URL", WEBHOOK + (
        "&threadKey=old&threadKey=duplicate&messageReplyOption=REPLY_MESSAGE_OR_FAIL&extra="
    ))
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        result = invoke("send", text="body", title=" --urgent ", thread_key="thread & one")
    assert result["kind"] == "cardsV2"
    assert result["thread_key"] == "thread & one"
    url = urllib.parse.urlsplit(transport.call_args.args[1])
    assert url.path == "/v1/spaces/fixture/messages"
    assert urllib.parse.parse_qs(url.query, keep_blank_values=True) == {
        "key": ["fixture-key"], "token": ["fixture-token"], "extra": [""],
        "threadKey": ["thread & one"],
        "messageReplyOption": ["REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"],
    }
    assert json.loads(transport.call_args.kwargs["body"]) == {
        "cardsV2": [{
            "cardId": "cos-card",
            "card": {
                "header": {"title": "--urgent"},
                "sections": [{"widgets": [{"textParagraph": {"text": "body"}}]}],
            },
        }],
    }
    main._load_credential.assert_not_called()


def test_long_text_preserves_existing_limit(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        invoke("send", text="x" * (main.SOFT_LEN + 1))
    content = json.loads(transport.call_args.kwargs["body"])["text"]
    assert len(content) == main.SOFT_LEN
    assert content == "x" * (main.SOFT_LEN - 1) + "\u2026"


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
        result = invoke("send", text="hello")
    assert result == {"ok": False, "error": "missing fixture"}
    transport.assert_not_called()


def test_status_is_outbound_only_and_does_not_disclose_webhook(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["running"] is False
    assert "fixture-key" not in json.dumps(result)
    assert "fixture-token" not in json.dumps(result)
    main._load_credential.assert_called_once_with("googlechat_webhook_url")
    transport.assert_not_called()
