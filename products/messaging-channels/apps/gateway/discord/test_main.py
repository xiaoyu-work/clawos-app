"""Retained outbound/config contracts and manifest-bound Discord dispatch."""

import json
import os
from pathlib import Path
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module

main = load_local_module(Path(__file__).with_name("main.py"), "gateway_discord_main")


@pytest.fixture
def sdk_app(tmp_path, monkeypatch):
    from claw_os_sdk.mcp import App

    monkeypatch.setenv("COS_DATA_DIR", str(tmp_path))
    for name in vars(main):
        if name.startswith("ENV_"):
            monkeypatch.delenv(getattr(main, name), raising=False)
    manifest_path = Path(__file__).with_name("app.json")
    monkeypatch.setenv("COS_APP_MANIFEST", str(manifest_path))
    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_discord_server")
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        f"gateway-discord.{name}" for name in json.loads(manifest_path.read_text())["operations"]
    }
    return app


def call(app, command, **arguments):
    return app._handle_request("tools/call", authenticated_mcp_params({
        "name": f"gateway-discord.{command}", "arguments": arguments,
    }), True)


def test_local_preferences_remain_persisted_but_are_not_owner_admission(sdk_app):
    result = call(sdk_app, "configure", settings=[
        "users=42,43", "guilds=99", "channels=100", "require_mention=false", "rpm=7",
    ])["structuredContent"]
    assert result["ok"] is True
    assert result["owner_admission"] is False
    assert result["configured"] == {
        "allowed_users": ["42", "43"], "allowed_guilds": ["99"], "allowed_channels": ["100"],
        "require_mention": False, "requests_per_minute": 7,
    }
    assert json.loads(Path(main._config_path()).read_text()) == result["configured"]


def test_configure_still_refuses_an_open_local_allowlist(sdk_app):
    result = call(sdk_app, "configure", settings=["guilds=99"])
    assert result["isError"] is True
    assert not Path(main._config_path()).exists()


@pytest.mark.parametrize("words", [["hello", "world"], ["--literal", "message"], ["\u4f60\u597d", "Discord"]])
def test_sdk_send_preserves_repeatable_text_and_disables_mentions(sdk_app, words):
    with mock.patch.object(main, "_load_token", return_value="fixture-token"), mock.patch.object(
        main, "_api_call", return_value={"id": "3001"},
    ) as api, mock.patch.object(main.gateway_memory, "remember_send") as remember:
        result = call(sdk_app, "send", channel_id="2001", text=words)["structuredContent"]
    api.assert_called_once_with("fixture-token", "POST", "/channels/2001/messages", {
        "content": " ".join(words), "allowed_mentions": {"parse": [], "replied_user": False},
    })
    assert result["message_ids"] == ["3001"]
    remember.assert_called_once_with("discord", result, channel_id="2001", text=" ".join(words))


def test_credential_failure_prevents_send(sdk_app):
    with mock.patch.object(main, "_load_token", side_effect=RuntimeError("fixture unavailable")), mock.patch.object(
        main, "_api_call",
    ) as api, mock.patch.object(main.gateway_memory, "remember_send"):
        result = call(sdk_app, "send", channel_id="2001", text=["hello"])
    assert result["isError"] is True
    api.assert_not_called()


def test_long_outbound_replies_still_split_at_discord_limits():
    text = "word " * 1000
    chunks = main._split_message(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)
    assert " ".join(chunks).replace(" ", "") == text.replace(" ", "")
