"""Thunderbird-backed Email contracts; no real accounts, messages or models."""

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from test_support import load_local_module


email = load_local_module(
    Path(__file__).with_name("main.py"), "claw_test_email_main", clear_modules=("_shared",),
)
ACCOUNT = "00000000-0000-4000-8000-000000000001:account1"
OTHER = "00000000-0000-4000-8000-000000000001:account2"


def reference(account=ACCOUNT):
    return base64.urlsafe_b64encode(
        json.dumps([account, "native-folder", "public@example.invalid"], separators=(",", ":")).encode()
    ).decode().rstrip("=")


class TestThunderbirdEmail(unittest.TestCase):
    def setUp(self):
        self.policy_patch = patch.object(email.policy, "require")
        self.require = self.policy_patch.start()
        self.kernel_patch = patch.object(email.kernel, "call_json_with_stdin_binary")
        self.call = self.kernel_patch.start()
        self.memory_patch = patch.object(email.memory, "remember")
        self.memory_patch.start()
        self.events_patch = patch.object(email.events, "publish")
        self.publish = self.events_patch.start()
        self.addCleanup(patch.stopall)

    def request(self):
        binary, argv, data = self.call.call_args.args
        self.assertTrue(os.path.isabs(binary))
        self.assertEqual(argv, ["__mail", "request", "--request-stdin"])
        return json.loads(data)

    def test_accounts_and_message_operations_use_the_sdk_mail_bridge(self):
        self.call.return_value = {"accounts": [{"id": ACCOUNT}], "backend": "thunderbird"}
        self.assertEqual(email.run("accounts", [])["accounts"], [{"id": ACCOUNT}])
        self.assertNotIn("account", self.request())
        self.require.assert_called_with("mail.accounts", wild=True)
        self.call.return_value = {"account": ACCOUNT, "messages": [{"id": reference()}]}
        result = email.run("list", [
            f"--account={ACCOUNT}", "--max-results=3", "--unread=false",
        ])
        self.assertEqual(self.request()["args"], {"max_results": 3, "unread": False})
        self.assertIn("thunderbird-message", result["messages"][0]["object"])
        self.require.assert_called_with("mail.read", name=ACCOUNT)
        self.call.return_value = {"account": ACCOUNT, "id": reference(), "body": "Native body"}
        result = email.run("read", [f"--account={ACCOUNT}", f"--id={reference()}"])
        self.assertEqual(result["body"], "Native body")
        self.assertEqual(self.request()["action"], "read")

    def test_missing_account_legacy_providers_and_cross_account_ids_do_not_dispatch(self):
        for command, args in [
            ("list", []),
            ("read", [f"--account={ACCOUNT}", f"--id={reference(OTHER)}"]),
            ("send", ["--provider=gmail", "--to=public@example.invalid", "--subject=Hi", "--body=Hello"]),
        ]:
            self.assertIn("error", email.run(command, args))
        self.call.assert_not_called()
        self.require.assert_not_called()

    def test_draft_confirmation_and_source_account_are_validated_before_policy(self):
        args = [
            f"--account={ACCOUNT}", f"--sender-account={OTHER}",
            f"--id={reference()}", "--review=sha256:" + "a" * 64,
        ]
        self.assertIn("error", email.run("draft_send", [*args, "--confirm=false"]))
        self.require.assert_not_called()
        self.call.return_value = {"account": ACCOUNT, "error": "draft changed", "conflicted": True}
        result = email.run("draft_send", [*args, "--confirm=true"])
        self.assertTrue(result["conflicted"])
        self.assertEqual(self.request()["args"]["sender_account"], OTHER)
        self.assertEqual(self.require.call_args_list[-3].args, ("mail.read",))
        self.assertEqual(self.require.call_args_list[-2].args, ("mail.draft",))
        self.assertEqual(self.require.call_args_list[-1].kwargs, {"name": OTHER})
        self.publish.assert_not_called()
        self.require.reset_mock()
        self.call.reset_mock()
        result = email.run("draft_save", [
            f"--account={OTHER}", f"--id={reference()}",
            "--to=public@example.invalid", "--subject=Review", "--body=Draft",
        ])
        self.assertIn("source-account", result["error"])
        self.require.assert_not_called()
        self.call.assert_not_called()

    def test_attachment_bytes_stay_in_the_os_and_only_the_exact_new_path_is_requested(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "attachment.pdf")
            self.call.return_value = {
                "account": ACCOUNT, "id": reference(), "path": path, "bytes": 3,
                "sha256": "sha256:" + "a" * 64,
            }
            result = email.run("attachment_download", [
                f"--account={ACCOUNT}", f"--id={reference()}", "--attachment=1.2", f"--output={path}",
            ])
            self.assertNotIn("error", result)
            self.assertEqual(self.request()["args"]["output"], path)
            self.assertEqual(self.request()["args"]["max_bytes"], 16777216)
            self.require.assert_any_call("fs.write", path=path)
            self.assertNotIn("data", result)
            self.call.reset_mock()
            result = email.run("attachment_download", [
                f"--account={ACCOUNT}", f"--id={reference()}", "--attachment=../../other",
                f"--output={path}",
            ])
            self.assertIn("error", result)
            self.call.assert_not_called()

    def test_repeated_submission_returns_its_receipt_without_sending_again(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"COS_DATA_DIR": root}):
            request_id = str(uuid.uuid4())
            args = [
                f"--account={ACCOUNT}", "--to=public@example.invalid",
                "--subject=Report", "--body=Review this", f"--request-id={request_id}",
            ]
            self.call.return_value = {"account": ACCOUNT, "sent": True, "id": reference()}
            first = email.run("send", args)
            self.assertEqual(first, email.run("send", args))
            self.call.assert_called_once()
            changed = email.run("send", [*args[:-1], "--cc=other@example.invalid", args[-1]])
            self.assertIn("different Mail operation", changed["error"])
            self.call.assert_called_once()

    def test_indeterminate_transport_failure_cannot_resubmit_and_has_no_provider_fallback(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "COS_DATA_DIR": root, "GOOGLE_ACCESS_TOKEN": "synthetic-unused-token",
            "SMTP_HOST": "unused.example.invalid",
        }):
            args = [
                f"--account={ACCOUNT}", "--to=public@example.invalid",
                "--subject=Hi", "--body=Hello", f"--request-id={uuid.uuid4()}",
            ]
            self.call.side_effect = email.kernel.KernelUnavailable("accepted outcome is unknown")
            self.assertTrue(email.run("send", args)["indeterminate"])
            self.assertTrue(email.run("send", args)["indeterminate"])
            self.call.assert_called_once()

    def test_mailbox_baseline_and_event_failure_do_not_replay_or_advance_the_cursor(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"COS_DATA_DIR": root}):
            self.call.return_value = {"account": ACCOUNT, "cursor": 10, "messages": [], "baseline": True}
            first = email.run("sync", [f"--account={ACCOUNT}"])
            self.assertEqual(first["events_emitted"], 0)
            self.publish.assert_not_called()
            self.call.return_value = {
                "account": ACCOUNT, "cursor": 11, "baseline": False,
                "messages": [{"sequence": 11, "id": reference()}],
            }
            self.publish.side_effect = RuntimeError("synthetic event service unavailable")
            with self.assertRaises(RuntimeError):
                email.run("sync", [f"--account={ACCOUNT}"])
            self.publish.side_effect = None
            result = email.run("sync", [f"--account={ACCOUNT}"])
            self.assertEqual(self.request()["args"]["cursor"], 10)
            self.assertEqual(result["events_emitted"], 1)
            self.assertEqual(self.publish.call_args.kwargs["payload"]["account"], ACCOUNT)
            self.assertIn("thunderbird-message", self.publish.call_args.kwargs["payload"]["object"])


if __name__ == "__main__":
    unittest.main()
