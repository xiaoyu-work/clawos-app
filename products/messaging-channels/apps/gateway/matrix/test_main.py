"""Matrix send/status contracts with real SDK dispatch and synthetic transport."""

import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
import urllib.error

import pytest

from test_support import authenticated_mcp_params, load_local_module


main = load_local_module(Path(__file__).with_name("main.py"), "gateway_matrix_main")
HOMESERVER = "https://matrix.example.test/base"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ("COS_MATRIX_TOKEN", "COS_MATRIX_HOMESERVER"):
        monkeypatch.delenv(name, raising=False)
    credentials = {"matrix_access_token": "fixture-token", "matrix_homeserver": HOMESERVER + "/"}
    with mock.patch.object(
        main, "_load_credential", side_effect=lambda name: (credentials[name], None),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_matrix_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-matrix.send", "gateway-matrix.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-matrix.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("gateway_memory", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


@pytest.mark.parametrize(("room_id", "encoded_room"), [
    ("!room:example.test", "%21room%3Aexample.test"),
    ("!room/part?x=1#fragment:example.test", "%21room%2Fpart%3Fx%3D1%23fragment%3Aexample.test"),
])
@pytest.mark.parametrize("text", ["hello world", "--literal", "\u4f60\u597d"])
def test_send_escapes_room_and_preserves_text(invoke, room_id, encoded_room, text):
    with mock.patch.object(main, "_txn_id", return_value="cos-fixture"), mock.patch.object(
        main.safe_egress, "safe_urlopen", return_value=(200, {}, b'{"event_id":"$fixture"}'),
    ) as transport:
        result = invoke("send", room_id=room_id, text=text)
    assert result == {
        "ok": True, "platform": "matrix", "room_id": room_id,
        "event_id": "$fixture", "homeserver": HOMESERVER,
    }
    assert transport.call_args.args == (
        "PUT", f"{HOMESERVER}/_matrix/client/v3/rooms/{encoded_room}/send/m.room.message/cos-fixture",
    )
    kwargs = transport.call_args.kwargs
    assert json.loads(kwargs["body"]) == {"msgtype": "m.text", "body": text}
    assert kwargs["headers"]["Authorization"] == "Bearer fixture-token"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 15
    assert kwargs["verb_id"] == "net.dial"
    main.gateway_memory.remember_send.assert_called_once_with("matrix", result, channel_id=room_id, text=text)


def test_environment_credentials_take_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_MATRIX_HOMESERVER", " https://override.example.test/// ")
    monkeypatch.setenv("COS_MATRIX_TOKEN", " override-token ")
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        result = invoke("send", room_id="!room:example.test", text="hello")
    assert result["homeserver"] == "https://override.example.test"
    assert transport.call_args.args[1].startswith("https://override.example.test/_matrix/")
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer override-token"
    main._load_credential.assert_not_called()


def test_missing_token_stops_before_homeserver_and_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")) as credentials, mock.patch.object(
        main.safe_egress, "safe_urlopen",
    ) as transport:
        assert invoke("send", room_id="!room:example.test", text="hello") == {
            "ok": False, "error": "missing fixture",
        }
    credentials.assert_called_once_with("matrix_access_token")
    transport.assert_not_called()


def test_status_does_not_read_access_token_or_start_sync(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["ok"] is True
    assert result["running"] is False
    assert result["homeserver"] == HOMESERVER
    assert "/sync loop not yet implemented" in result["note"]
    main._load_credential.assert_called_once_with("matrix_homeserver")
    transport.assert_not_called()


def test_status_retains_existing_default_homeserver(invoke):
    with mock.patch.object(main, "_load_credential", return_value=(None, None)):
        assert invoke("status")["homeserver"] == "https://matrix.org"


def test_transaction_ids_include_time_and_fresh_random_suffix():
    ids = [mock.Mock(hex="a" * 32), mock.Mock(hex="b" * 32)]
    with mock.patch.object(main.time, "time", return_value=1234.5), mock.patch.object(
        main.uuid, "uuid4", side_effect=ids,
    ):
        assert main._txn_id() == "cos-1234500-aaaaaaaa"
        assert main._txn_id() == "cos-1234500-bbbbbbbb"


def test_long_text_retains_existing_limit(invoke):
    with mock.patch.object(main.safe_egress, "safe_urlopen", return_value=(200, {}, b"{}")) as transport:
        invoke("send", room_id="!room:example.test", text="x" * (main.SOFT_LEN + 1))
    assert json.loads(transport.call_args.kwargs["body"])["body"] == "x" * (main.SOFT_LEN - 1) + "\u2026"


@pytest.mark.parametrize("kind", ["egress", "url", "http"])
def test_transport_failure_is_reported(invoke, kind):
    errors = {
        "egress": main.safe_egress.EgressBlocked("blocked fixture"),
        "url": urllib.error.URLError("unavailable fixture"),
        "http": urllib.error.HTTPError(HOMESERVER, 403, "Forbidden", {}, io.BytesIO(b"denied fixture")),
    }
    with mock.patch.object(main.safe_egress, "safe_urlopen", side_effect=errors[kind]):
        result = invoke("send", room_id="!room:example.test", text="hello")
    assert result["ok"] is False
    assert "fixture" in result["error"]
