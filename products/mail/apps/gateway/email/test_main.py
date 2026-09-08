"""Tests for the email gateway: STARTTLS on port 587 is mandatory.

A MITM that strips ``STARTTLS`` from an EHLO response would surface
locally as ``smtp.has_extn("starttls") == False``. The gateway MUST
abort rather than fall back to cleartext authentication.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from test_support import load_local_module

def _load_main():
    """Load this gateway's main.py under a unique module name so it
    can coexist with the other gateway test modules in one pytest run."""
    path = os.path.join(os.path.dirname(__file__), "main.py")
    return load_local_module(
        path,
        "gateway_email_main",
        clear_modules=("gateway",),
    )


main = _load_main()


class _FakeSMTP:
    """Pretend SMTP server. ``advertises_starttls`` toggles whether
    EHLO advertises the STARTTLS extension."""

    def __init__(self, host, port, timeout=None, *, advertises_starttls=False):
        self.host = host
        self.port = port
        self._advertises = advertises_starttls
        self.login_called = False
        self.send_called = False
        self.starttls_called = False

    # Context-manager protocol --------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    # SMTP API surface used by main._send ---------------------------
    def ehlo(self):
        return (250, b"hi")

    def has_extn(self, name):
        return name.lower() == "starttls" and self._advertises

    def starttls(self, context=None):
        self.starttls_called = True
        return (220, b"ready")

    def login(self, user, password):
        self.login_called = True

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.send_called = True


class StartTLSMandatoryTests(unittest.TestCase):
    """Port 587 with STARTTLS missing => must NOT log in or send."""

    def setUp(self):
        # Wire a working config (env vars beat credential helper).
        self._saved = {
            k: os.environ.get(k)
            for k in (
                "COS_SMTP_HOST", "COS_SMTP_USER", "COS_SMTP_PASSWORD",
                "COS_SMTP_PORT", "COS_SMTP_FROM",
            )
        }
        os.environ["COS_SMTP_HOST"] = "smtp.example.com"
        os.environ["COS_SMTP_USER"] = "user@example.com"
        os.environ["COS_SMTP_PASSWORD"] = "hunter2"
        os.environ["COS_SMTP_PORT"] = "587"
        os.environ["COS_SMTP_FROM"] = "user@example.com"

        self._policy_patch = patch.object(main.policy, "require")
        self._policy_check = self._policy_patch.start()

        # Track the last SMTP instance built so the assertions can
        # reach into it.
        self._last_smtp: _FakeSMTP | None = None

        transport = main.cos_smtp
        self._orig_SMTP = transport.SafeSMTP

        def _factory(host, port, timeout=None):
            inst = _FakeSMTP(host, port, timeout, advertises_starttls=False)
            self._last_smtp = inst
            return inst

        transport.SafeSMTP = _factory  # type: ignore[assignment]

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._policy_patch.stop()
        main.cos_smtp.SafeSMTP = self._orig_SMTP

    def test_587_without_starttls_aborts_before_login(self):
        result = main._send(
            to="dest@example.com",
            subject="hi",
            body="hello",
            cc="",
        )
        # The send is refused.
        self.assertFalse(result["ok"])
        # The error mentions STARTTLS (so the operator can grok what
        # to do) rather than a vague network error.
        err = result.get("error", "").lower()
        self.assertIn("starttls", err)
        # And crucially: we did NOT call login() or send_message().
        self.assertIsNotNone(self._last_smtp)
        self.assertFalse(self._last_smtp.login_called)
        self.assertFalse(self._last_smtp.send_called)
        self.assertFalse(self._last_smtp.starttls_called)


class StartTLSAdvertisedSucceedsTests(unittest.TestCase):
    """Sanity-check: when STARTTLS *is* advertised, we negotiate it
    and then proceed to login."""

    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in (
                "COS_SMTP_HOST", "COS_SMTP_USER", "COS_SMTP_PASSWORD",
                "COS_SMTP_PORT", "COS_SMTP_FROM",
            )
        }
        os.environ["COS_SMTP_HOST"] = "smtp.example.com"
        os.environ["COS_SMTP_USER"] = "user@example.com"
        os.environ["COS_SMTP_PASSWORD"] = "hunter2"
        os.environ["COS_SMTP_PORT"] = "587"
        os.environ["COS_SMTP_FROM"] = "user@example.com"
        self._policy_patch = patch.object(main.policy, "require")
        self._policy_check = self._policy_patch.start()
        self._last_smtp: _FakeSMTP | None = None
        transport = main.cos_smtp
        self._orig_SMTP = transport.SafeSMTP

        def _factory(host, port, timeout=None):
            inst = _FakeSMTP(host, port, timeout, advertises_starttls=True)
            self._last_smtp = inst
            return inst

        transport.SafeSMTP = _factory  # type: ignore[assignment]

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._policy_patch.stop()
        main.cos_smtp.SafeSMTP = self._orig_SMTP

    def test_starttls_advertised_path_succeeds(self):
        result = main._send(
            to="dest@example.com",
            subject="hi",
            body="hello",
            cc="",
        )
        self.assertTrue(result["ok"], msg=str(result))
        self.assertTrue(self._last_smtp.starttls_called)
        self.assertTrue(self._last_smtp.login_called)
        self.assertTrue(self._last_smtp.send_called)
        self._policy_check.assert_called_once_with("net.dial", host="smtp.example.com")

    def test_unavailable_policy_aborts_before_smtp(self):
        self._policy_check.side_effect = main.policy.PolicyUnavailable("unavailable")
        result = main._send("dest@example.com", "hi", "hello")
        self.assertFalse(result["ok"])
        self.assertIsNone(self._last_smtp)

    def test_unexpected_policy_error_is_not_hidden(self):
        self._policy_check.side_effect = RuntimeError("unexpected")
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            main._send("dest@example.com", "hi", "hello")
        self.assertIsNone(self._last_smtp)


if __name__ == "__main__":
    unittest.main()
