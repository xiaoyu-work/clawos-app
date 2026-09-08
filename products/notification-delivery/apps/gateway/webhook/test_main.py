"""Tests for the webhook gateway: policy-gating and redirect-SSRF blocking."""

from __future__ import annotations

import io
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock
import urllib.error
import urllib.request

import pytest

from test_support import authenticated_mcp_params, load_local_module


def _load_main():
    """Load this gateway's main.py under a unique module name so it
    can coexist with the other gateway test modules in one pytest run."""
    path = os.path.join(os.path.dirname(__file__), "main.py")
    return load_local_module(
        path,
        "gateway_webhook_main",
    )


main = _load_main()
from gateway._shared import safe_egress  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_boundaries(monkeypatch):
    for name in ("COS_WEBHOOK_URL", "COS_WEBHOOK_SECRET", "COS_GATEWAY_ALLOW_PRIVATE"):
        monkeypatch.delenv(name, raising=False)

    def resolve(host, port, **kwargs):
        address = "93.184.216.34" if host == "example.com" else host
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

    with mock.patch.object(main, "_load_credential", return_value=(None, "missing fixture")), \
         mock.patch.object(main.gateway_memory, "remember_send"), \
         mock.patch.object(safe_egress.socket, "getaddrinfo", side_effect=resolve), \
         mock.patch.object(safe_egress.egress, "available", return_value=False), \
         mock.patch.object(safe_egress, "_open_pinned_socket", side_effect=AssertionError("unexpected network")):
        yield


@pytest.fixture(params=["direct", "mcp"])
def invoke(request):
    from claw_os_sdk.mcp import App

    servers = []
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(Path(__file__).with_name("app.json"))},
    ), mock.patch.object(App, "serve", lambda app: servers.append(app)):
        load_local_module(Path(__file__).with_name("server.py"), "gateway_webhook_server")
    assert len(servers) == 1
    app = servers[0]
    assert {tool["name"] for tool in app._handle_request("tools/list", {}, True)["tools"]} == {
        "gateway-webhook.send", "gateway-webhook.status",
    }

    def call(command, **arguments):
        if request.param == "direct":
            return main.run(command, arguments)
        result = app._handle_request("tools/call", authenticated_mcp_params({
            "name": f"gateway-webhook.{command}", "arguments": arguments,
        }), True)
        body = result["structuredContent"]
        assert result.get("isError", False) is (body.get("ok") is False)
        return body

    return call


def test_list_dispatch_forwards_manifest_options():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        assert main.run("send", [
            "hello", "--target", "https://example.test/hook", "--raw",
            "--bearer", "token", "--basic", "user:pass", "--api-key", "key",
            "--hmac-sha256", "secret",
        ]) == {"ok": True}
    send.assert_called_once_with(
        "https://example.test/hook", "hello", True, "token", "user:pass", "key", "secret",
    )


def test_removed_leading_positionals_are_rejected():
    with mock.patch.object(main, "_send") as send:
        result = main.run("send", ["https://example.test/hook", "hello"])
    assert result["ok"] is False
    assert "too many positional arguments" in result["error"]
    send.assert_not_called()


def test_one_positional_is_always_message_text():
    with mock.patch.object(main, "_send", return_value={"ok": True}) as send:
        main.run("send", ["hello"])
    assert send.call_args.args[:2] == ("", "hello")


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("text", ["hello\nworld", "--literal", "\u4f60\u597d"])
def test_payload_and_response_preview(invoke, raw, text):
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(202, {}, b"x" * 250)) as transport, \
         mock.patch.object(main.time, "time", return_value=1234):
        result = invoke("send", target="https://example.test/hook", text=text, raw=raw)
    assert result == {
        "ok": True, "platform": "webhook", "target": "https://example.test/hook",
        "status": 202, "kind": "raw" if raw else "json", "signed": False,
        "body_preview": "x" * 200,
    }
    assert transport.call_args.args == ("POST", "https://example.test/hook")
    kwargs = transport.call_args.kwargs
    if raw:
        assert kwargs["body"] == text.encode("utf-8")
        assert kwargs["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    else:
        assert json.loads(kwargs["body"]) == {"text": text, "platform": "webhook", "ts": 1234}
        assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["timeout"] == 20 and kwargs["verb_id"] == "net.dial"
    main._load_credential.assert_called_once_with("webhook_default_secret")
    main.gateway_memory.remember_send.assert_called_once_with(
        "webhook", result, channel_id="https://example.test/hook", text=text,
    )


@pytest.mark.parametrize("mode", ["bearer", "basic", "api-key", "hmac-only"])
def test_auth_precedence_and_independent_hmac(invoke, mode):
    args = {"hmac-sha256": "sign-fixture"}
    if mode in ("bearer", "basic", "api-key"):
        args["api-key"] = "key-fixture"
    if mode in ("bearer", "basic"):
        args["basic"] = "user:pass"
    if mode == "bearer":
        args["bearer"] = "bearer-fixture"
    with mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b"ok")) as transport:
        assert invoke("send", target="https://example.test/hook", text="hello", **args)["ok"]
    kwargs = transport.call_args.kwargs
    headers = kwargs["headers"]
    expected_auth = {
        "bearer": "Bearer bearer-fixture",
        "basic": "Basic " + base64.b64encode(b"user:pass").decode(),
    }
    assert headers.get("Authorization") == expected_auth.get(mode)
    assert headers.get("X-API-Key") == ("key-fixture" if mode == "api-key" else None)
    digest = hmac.new(b"sign-fixture", kwargs["body"], hashlib.sha256).hexdigest()
    assert headers["X-Signature"] == f"sha256={digest}"
    main._load_credential.assert_not_called()


@pytest.mark.parametrize("environment", [False, True])
def test_default_target_and_signing_secret(invoke, monkeypatch, environment):
    credentials = {"webhook_default_url": "https://default.example.test/hook", "webhook_default_secret": "secret-fixture"}
    if environment:
        monkeypatch.setenv("COS_WEBHOOK_URL", " " + credentials["webhook_default_url"] + " ")
        monkeypatch.setenv("COS_WEBHOOK_SECRET", " secret-fixture ")
    with mock.patch.object(main, "_load_credential", side_effect=lambda name: (credentials[name], None)) as load, \
         mock.patch.object(safe_egress, "safe_urlopen", return_value=(200, {}, b"ok")) as transport:
        result = invoke("send", text="hello", raw=True)
    assert result["signed"] is True
    assert transport.call_args.args[1] == credentials["webhook_default_url"]
    assert transport.call_args.kwargs["headers"]["X-Signature"] == (
        "sha256=" + hmac.new(b"secret-fixture", b"hello", hashlib.sha256).hexdigest()
    )
    assert load.call_count == (0 if environment else 2)


@pytest.mark.parametrize("arguments", [
    {"text": "hello"}, {"text": " ", "target": "https://example.test/hook"},
    {"text": "hello", "target": "file:///fixture"},
])
def test_missing_or_invalid_inputs_stop_before_transport(invoke, arguments):
    with mock.patch.object(safe_egress, "safe_urlopen") as transport:
        assert invoke("send", **arguments)["ok"] is False
    transport.assert_not_called()


@pytest.mark.parametrize("error", [
    safe_egress.EgressBlocked("blocked fixture"),
    urllib.error.URLError("unavailable fixture"),
])
def test_transport_failure_is_reported(invoke, error):
    with mock.patch.object(safe_egress, "safe_urlopen", side_effect=error):
        result = invoke("send", text="hello", target="https://example.test/hook")
    assert result["ok"] is False and "fixture" in result["error"]


def test_http_failure_is_reported(invoke):
    error = urllib.error.HTTPError("https://example.test", 403, "Forbidden", {}, io.BytesIO(b"denied fixture"))
    with mock.patch.object(safe_egress, "safe_urlopen", side_effect=error):
        result = invoke("send", text="hello", target="https://example.test/hook")
    assert result["ok"] is False and result["error"] == "HTTP 403: denied fixture"


def test_status_does_not_disclose_defaults_or_contact_network(invoke):
    with mock.patch.object(main, "_load_credential", return_value=("private-fixture", None)), \
         mock.patch.object(safe_egress, "safe_urlopen") as transport:
        result = invoke("status")
    assert result["default_url_configured"] and result["default_secret_configured"]
    assert not result["running"]
    assert "private-fixture" not in json.dumps(result)
    transport.assert_not_called()
    main.gateway_memory.remember_send.assert_not_called()


def test_policy_denial_preserves_structured_details(invoke):
    with mock.patch.object(safe_egress, "policy", _DenyingPolicy()):
        result = invoke("send", target="https://example.com/hook", text="hello")
    assert result["ok"] is False
    assert result["denial"] == {"verb": "net.dial", "host": "example.com:443", "decision": "deny"}
    safe_egress._open_pinned_socket.assert_not_called()


class _DenyingPolicy:
    """A policy stub whose ``require`` always denies."""

    class PermissionDenied(Exception):
        pass

    def require(self, verb_id, host=None, name=None, path=None, wild=False):
        exc = self.PermissionDenied(f"deny {verb_id} -> {host}")
        exc.denial = {"verb": verb_id, "host": host, "decision": "deny"}
        raise exc


class _AllowingPolicy:
    """A policy stub whose ``require`` is a no-op."""

    def require(self, verb_id, host=None, name=None, path=None, wild=False):
        return None


class WebhookPolicyDenialTests(unittest.TestCase):
    """When the kernel denies the verb, no bytes hit the wire."""

    def setUp(self):
        self._orig_policy = safe_egress.policy

    def tearDown(self):
        safe_egress.policy = self._orig_policy

    def test_send_surfaces_permission_denial(self):
        safe_egress.policy = _DenyingPolicy()
        # Use a public host so we don't trip the private-IP check
        # before reaching the policy gate.
        result = main._send(
            target="https://example.com/hook",
            text="hello",
            raw=False,
            bearer=None,
            basic=None,
            api_key=None,
            hmac_secret=None,
        )
        self.assertFalse(result["ok"])
        # The webhook gateway forwards either "permission denied"
        # (kernel denial) or "egress blocked" (if the policy module
        # is missing). Either path means we did NOT actually POST.
        err = result.get("error", "")
        self.assertTrue(
            "permission denied" in err or "egress blocked" in err
            or result.get("denial") is not None,
            f"unexpected error shape: {result!r}",
        )


class RedirectSSRFTests(unittest.TestCase):
    """A 30x response must NOT cause urllib to follow Location:.

    This is the core defence against redirect-SSRF: an attacker who
    controls a hooks.example.com endpoint must not be able to chain
    us into ``http://169.254.169.254/latest/meta-data/`` via a 302.
    """

    def setUp(self):
        self._orig_policy = safe_egress.policy
        safe_egress.policy = _AllowingPolicy()
        # Pre-resolve example.com to a non-private address by setting
        # the env override OFF (default).
        os.environ.pop("COS_GATEWAY_ALLOW_PRIVATE", None)

    def tearDown(self):
        safe_egress.policy = self._orig_policy

    def test_redirect_handler_returns_none(self):
        """The opener's redirect handler MUST short-circuit."""
        handler = safe_egress._NoRedirectHandler()
        # Build a fake 302 — the redirect_request return value of
        # None is what causes urllib to raise HTTPError with the 302
        # rather than chase the Location header.
        result = handler.redirect_request(
            req=None,
            fp=io.BytesIO(b""),
            code=302,
            msg="Found",
            headers={"Location": "http://169.254.169.254/latest/meta-data/"},
            newurl="http://169.254.169.254/latest/meta-data/",
        )
        self.assertIsNone(result)

    def test_opener_has_no_redirect_handler_subclass(self):
        """The module-level opener uses _NoRedirectHandler, not
        the stdlib HTTPRedirectHandler."""
        # The opener stores its handlers in ``handlers``.
        redirect_handlers = [
            h for h in safe_egress._OPENER.handlers
            if isinstance(h, urllib.request.HTTPRedirectHandler)
        ]
        # The base HTTPRedirectHandler may show up because
        # _NoRedirectHandler subclasses it. Verify ALL redirect
        # handlers are our no-op subclass.
        for h in redirect_handlers:
            self.assertIsInstance(h, safe_egress._NoRedirectHandler)


class PrivateHostBlockingTests(unittest.TestCase):
    """RFC1918 / loopback / link-local targets must be refused."""

    def setUp(self):
        self._orig_policy = safe_egress.policy
        safe_egress.policy = _AllowingPolicy()
        os.environ.pop("COS_GATEWAY_ALLOW_PRIVATE", None)

    def tearDown(self):
        safe_egress.policy = self._orig_policy

    def test_imds_ip_is_blocked(self):
        with self.assertRaises(safe_egress.EgressBlocked):
            safe_egress.safe_urlopen(
                "GET",
                "http://169.254.169.254/latest/meta-data/",
                verb_id="net.dial",
            )

    def test_loopback_is_blocked(self):
        with self.assertRaises(safe_egress.EgressBlocked):
            safe_egress.safe_urlopen(
                "GET",
                "http://127.0.0.1:8080/admin",
                verb_id="net.dial",
            )

    def test_file_scheme_is_blocked(self):
        with self.assertRaises(safe_egress.EgressBlocked):
            safe_egress.safe_urlopen(
                "GET",
                "file:///etc/passwd",
                verb_id="net.dial",
            )


if __name__ == "__main__":
    unittest.main()
