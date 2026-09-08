"""Tests for the telegram gateway: sender allowlist + rate limiting.

We exercise ``_ask_agent`` end-to-end with the kernel policy stubbed
and ``cos agent ask`` short-circuited to a fake subprocess result, so
the test focuses on the *gate* logic (sender allowlist, rate limiter,
policy.require) rather than the subprocess plumbing.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock
import urllib.error
import urllib.parse

import pytest

from test_support import authenticated_mcp_params, load_local_module


def _load_main():
    """Load this gateway's main.py under a unique module name so it
    can coexist with the other gateway test modules in one pytest run."""
    path = os.path.join(os.path.dirname(__file__), "main.py")
    return load_local_module(
        path,
        "gateway_telegram_main",
    )


main = _load_main()
from gateway._shared import inbound, safe_egress, safe_subprocess  # noqa: E402

try:
    from cos_runtime import policy as _cos_policy  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    _cos_policy = None


class _AllowingPolicy:
    def require(self, verb_id, host=None, name=None, path=None, wild=False):
        return None


class _FakeProc:
    def __init__(self, stdout="ok", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TelegramSenderAllowlistTests(unittest.TestCase):
    """``_ask_agent`` must reject senders not in
    ``COS_TELEGRAM_ALLOWED_CHATS``."""

    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k) for k in (main.ENV_ALLOWED_CHATS, main.ENV_RPM)
        }
        self._orig_policy = safe_egress.policy
        safe_egress.policy = _AllowingPolicy()
        # Also bypass the kernel-side policy gate used by
        # ``_ask_agent`` directly (``from cos_runtime import policy``).
        if _cos_policy is not None:
            self._orig_cos_require = _cos_policy.require
            _cos_policy.require = lambda *a, **kw: None
        else:
            self._orig_cos_require = None
        main._reset_rate_limiter_for_tests()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        safe_egress.policy = self._orig_policy
        if _cos_policy is not None and self._orig_cos_require is not None:
            _cos_policy.require = self._orig_cos_require
        main._reset_rate_limiter_for_tests()

    def test_empty_allowlist_rejects_everyone(self):
        """No env var set ⇒ nobody is allowed."""
        os.environ.pop(main.ENV_ALLOWED_CHATS, None)
        with self.assertRaises(inbound.SenderNotAllowed):
            main._ask_agent(42, "hi")

    def test_unlisted_sender_rejected(self):
        os.environ[main.ENV_ALLOWED_CHATS] = "1,2,3"
        with self.assertRaises(inbound.SenderNotAllowed):
            main._ask_agent(42, "hi")

    def test_listed_sender_passes_allowlist(self):
        """An allowlisted sender clears the gate (and would reach
        ``safe_subprocess`` if we didn't stub it)."""
        os.environ[main.ENV_ALLOWED_CHATS] = "42"
        # Stub the subprocess call so we don't shell out to `cos`.
        orig = safe_subprocess.safe_subprocess
        safe_subprocess.safe_subprocess = lambda *a, **kw: _FakeProc("hi back")
        try:
            reply = main._ask_agent(42, "ping")
        finally:
            safe_subprocess.safe_subprocess = orig
        self.assertEqual(reply, "hi back")


class TelegramRateLimitTests(unittest.TestCase):
    """Allowlisted sender, but pummeling the gateway should trip
    ``inbound.RateLimited`` once the per-minute budget is gone."""

    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k) for k in (main.ENV_ALLOWED_CHATS, main.ENV_RPM)
        }
        os.environ[main.ENV_ALLOWED_CHATS] = "42"
        os.environ[main.ENV_RPM] = "5"
        self._orig_policy = safe_egress.policy
        safe_egress.policy = _AllowingPolicy()
        if _cos_policy is not None:
            self._orig_cos_require = _cos_policy.require
            _cos_policy.require = lambda *a, **kw: None
        else:
            self._orig_cos_require = None
        main._reset_rate_limiter_for_tests()
        # Stub the subprocess so the rate-limiter gate is what we
        # are actually testing.
        self._orig_subp = safe_subprocess.safe_subprocess
        safe_subprocess.safe_subprocess = lambda *a, **kw: _FakeProc("ok")

    def tearDown(self):
        safe_subprocess.safe_subprocess = self._orig_subp
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        safe_egress.policy = self._orig_policy
        if _cos_policy is not None and self._orig_cos_require is not None:
            _cos_policy.require = self._orig_cos_require
        main._reset_rate_limiter_for_tests()

    def test_sixth_call_within_minute_is_rate_limited(self):
        # First 5 calls succeed.
        for _ in range(5):
            reply = main._ask_agent(42, "ping")
            self.assertEqual(reply, "ok")
        # 6th call within the same minute must trip RateLimited.
        with self.assertRaises(inbound.RateLimited):
            main._ask_agent(42, "ping")


@pytest.fixture(autouse=True)
def isolated_effects(monkeypatch, tmp_path):
    monkeypatch.setenv("COS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_BIN", "cos")
    monkeypatch.delenv("COS_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv(main.ENV_ALLOWED_CHATS, raising=False)
    with mock.patch.object(
        safe_subprocess, "safe_credential_load", return_value=("fixture-token", None),
    ), mock.patch.object(
        safe_subprocess, "safe_subprocess", side_effect=AssertionError("unexpected subprocess"),
    ), mock.patch.object(
        safe_egress, "safe_urlopen", side_effect=AssertionError("unexpected network"),
    ), mock.patch.object(main.gateway_memory, "remember_send"):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_telegram_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        f"gateway-telegram.{command}" for command in ("send", "status", "start", "stop")
    }

    def call(command, **arguments):
        if request.param == "direct":
            argv = ["--", arguments["chat_id"], *arguments["text"]] if command == "send" else []
            return main.run(command, argv)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-telegram.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_shared_imports_are_gateway_scoped():
    for name in ("atomic", "gateway_memory", "inbound", "safe_egress", "safe_subprocess"):
        assert getattr(main, name).__name__ == f"gateway._shared.{name}"


def test_inbound_policy_denial_prevents_agent_subprocess(monkeypatch):
    monkeypatch.setenv(main.ENV_ALLOWED_CHATS, "42")
    with mock.patch.object(_cos_policy, "require", side_effect=RuntimeError("denied fixture")):
        with pytest.raises(RuntimeError, match="denied fixture"):
            main._ask_agent(42, "hello")
    safe_subprocess.safe_subprocess.assert_not_called()


@pytest.mark.parametrize("chat_id", ["12345", "-10012345"])
@pytest.mark.parametrize("parts", [["hello", "world"], ["--literal"], ["\u4f60\u597d"]])
def test_send_preserves_repeatable_text_and_chat(invoke, chat_id, parts):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        result = invoke("send", chat_id=chat_id, text=parts)
    text = " ".join(parts)
    assert result == {"ok": True, "platform": "telegram", "sent_to": chat_id, "len": len(text)}
    assert transport.call_args.args == ("POST", "https://api.telegram.org/botfixture-token/sendMessage")
    kwargs = transport.call_args.kwargs
    assert urllib.parse.parse_qs(kwargs["body"].decode()) == {"chat_id": [chat_id], "text": [text]}
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert kwargs["timeout"] == 15
    assert kwargs["verb_id"] == "net.dial"
    safe_subprocess.safe_credential_load.assert_called_once_with(
        "telegram_bot_token", timeout=10.0, cos_bin="cos",
    )
    main.gateway_memory.remember_send.assert_called_once_with("telegram", result, channel_id=chat_id, text=text)


def test_environment_token_takes_precedence(invoke, monkeypatch):
    monkeypatch.setenv("COS_TELEGRAM_TOKEN", " override-fixture ")
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        assert invoke("send", chat_id="12345", text=["hello"])["ok"] is True
    assert transport.call_args.args[1] == "https://api.telegram.org/botoverride-fixture/sendMessage"
    safe_subprocess.safe_credential_load.assert_not_called()


def test_missing_token_does_not_send(invoke):
    with mock.patch.object(safe_subprocess, "safe_credential_load", return_value=(None, "missing fixture")):
        assert invoke("send", chat_id="12345", text=["hello"]) == {"ok": False, "error": "missing fixture"}
    safe_egress.safe_urlopen.assert_not_called()


def test_api_rejection_is_not_http_success(invoke):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(
        200, {}, b'{"ok":false,"description":"rejected fixture"}',
    )):
        result = invoke("send", chat_id="12345", text=["hello"])
    assert result["ok"] is False
    assert "rejected fixture" in result["error"]


@pytest.mark.parametrize("error", [
    urllib.error.URLError("unavailable fixture"), safe_egress.EgressBlocked("blocked fixture"),
])
def test_send_reports_transport_errors(invoke, error):
    with mock.patch.object(safe_egress, "safe_urlopen", side_effect=error):
        result = invoke("send", chat_id="12345", text=["hello"])
    assert result["ok"] is False
    assert "fixture" in result["error"]


def test_long_text_retains_existing_truncation(invoke):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b'{"ok":true}')) as transport:
        invoke("send", chat_id="12345", text=["x" * (main.TG_MESSAGE_LIMIT + 1)])
    assert urllib.parse.parse_qs(transport.call_args.kwargs["body"].decode())["text"] == [
        "x" * (main.TG_MESSAGE_LIMIT - 1) + "\u2026",
    ]


def test_status_reads_only_isolated_state(invoke, tmp_path):
    main._write_state({"offset": 42})
    result = invoke("status")
    assert result["running"] is False
    assert result["offset"] == 42
    assert result["state_dir"] == str(tmp_path / "apps" / "gateway-telegram")
    assert result["allowlist_configured"] is False
    safe_subprocess.safe_credential_load.assert_not_called()
    safe_egress.safe_urlopen.assert_not_called()


def test_start_refuses_existing_process(invoke):
    main._write_pid(424242)
    with mock.patch.object(main, "_pid_alive", return_value=True):
        result = invoke("start")
    assert result["ok"] is False
    assert "already running" in result["error"]
    safe_subprocess.safe_credential_load.assert_not_called()
    safe_egress.safe_urlopen.assert_not_called()


def test_start_persists_offset_and_clears_pid_without_real_signals(invoke):
    main._write_state({"offset": 10})
    handlers = {}
    update = {"update_id": 11, "message": {"chat": {"id": 12345}, "text": "hello"}}
    calls = []

    def poll(token, method, params, timeout):
        calls.append((token, method, params, timeout))
        if len(calls) == 1:
            return {"ok": True, "result": [update]}
        handlers[main.signal.SIGTERM](None, None)
        return {"ok": True, "result": []}

    with mock.patch.object(main.signal, "signal", side_effect=lambda sig, handler: handlers.update({sig: handler})), mock.patch.object(
        main, "_api_call", side_effect=poll,
    ), mock.patch.object(main, "_process_update") as process:
        result = invoke("start")
    assert result == {"ok": True, "platform": "telegram", "stopped": True, "offset": 12}
    assert calls == [
        ("fixture-token", "getUpdates", {"offset": offset, "timeout": 25}, 30) for offset in (10, 12)
    ]
    process.assert_called_once_with("fixture-token", update)
    assert main._read_state() == {"offset": 12}
    assert main._read_pid() is None


@pytest.mark.parametrize("stale", [False, True])
def test_stop_handles_absent_or_stale_pid(invoke, stale):
    if stale:
        main._write_pid(424242)
    with mock.patch.object(main, "_pid_alive", return_value=False), mock.patch.object(main.os, "kill") as kill:
        result = invoke("stop")
    assert result["ok"] is True
    assert result["running"] is False
    assert main._read_pid() is None
    kill.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Linux signal contract")
def test_stop_signals_recorded_pid_only(invoke):
    main._write_pid(424242)
    with mock.patch.object(main, "_pid_alive", return_value=True), mock.patch.object(main.os, "kill") as kill:
        result = invoke("stop")
    assert result["stopped_pid"] == 424242
    kill.assert_called_once_with(424242, main.signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
