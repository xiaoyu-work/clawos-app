"""Credential client checks independent of an App's business identity."""

import json
import unittest
from unittest import mock

from _shared import credentials


class CredentialLoaderTests(unittest.TestCase):
    def setUp(self):
        self.binary = mock.patch.dict(credentials.os.environ, {"COS_BIN": "/fixture/cos"})
        self.binary.start()
        self.addCleanup(self.binary.stop)

    @mock.patch.object(credentials.subprocess, "run")
    def test_loads_value_from_cos_json(self, run):
        run.return_value = mock.MagicMock(
            returncode=0,
            stdout=json.dumps({"value": "secret-value"}),
            stderr="",
        )

        value, error = credentials.load_credential("TOKEN")

        self.assertEqual(value, "secret-value")
        self.assertIsNone(error)

    @mock.patch.object(credentials.subprocess, "run")
    def test_suppresses_child_stderr_on_failure(self, run):
        run.return_value = mock.MagicMock(
            returncode=1,
            stdout="",
            stderr="must-not-leak-secret-value",
        )

        value, error = credentials.load_credential("TOKEN")

        self.assertIsNone(value)
        self.assertNotIn("must-not-leak", error)
        self.assertIn("stderr suppressed", error)

    @mock.patch.object(credentials.subprocess, "run")
    def test_app_identity_never_overrides_a_provider_denial(self, run):
        run.return_value = mock.MagicMock(
            returncode=1,
            stdout=json.dumps({"value": "must-not-be-accepted"}),
            stderr="denied-secret-details",
        )
        for app_id in ("pkg", "mail-ai", "user-owned-example"):
            with self.subTest(app_id=app_id), mock.patch.dict(
                credentials.os.environ, {"COS_APP_ID": app_id},
            ):
                value, error = credentials.load_credential("TOKEN", namespace="owner")
                self.assertIsNone(value)
                self.assertIn("returned 1", error)
                self.assertNotIn("denied-secret-details", error)
                self.assertNotIn("must-not-be-accepted", error)
                self.assertEqual(
                    run.call_args.args[0],
                    ["/fixture/cos", "credential", "load", "TOKEN", "--namespace", "owner"],
                )


if __name__ == "__main__":
    unittest.main()
