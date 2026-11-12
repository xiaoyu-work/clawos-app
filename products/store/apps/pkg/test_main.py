"""Tests for the pkg App's catalog clients and argument handling."""

from contextlib import contextmanager
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

import pytest

from cos_runtime import mcp
from test_support import authenticated_mcp_params, load_local_module

APP_DIR = pathlib.Path(__file__).parent
main = load_local_module(
    APP_DIR / "main.py",
    "claw_test_pkg_main",
    clear_modules=("_shared",),
)
DEFAULT_SEARCH_LIMIT = main.DEFAULT_SEARCH_LIMIT
MAX_SEARCH_LIMIT = main.MAX_SEARCH_LIMIT
_apt_install = main._apt_install
_parse_search_args = main._parse_search_args
_valid_package_name = main._valid_package_name
cmd_need = main.cmd_need
cmd_search = main.cmd_search
cmd_show = main.cmd_show
run = main.run


@contextmanager
def _allow_policy():
    with mock.patch.object(main.policy, "require", lambda *a, **kw: None), mock.patch.object(
        main, "_cos_binary", return_value="/usr/local/bin/cos"
    ):
        yield


def _fake_completed(stdout="", stderr="", returncode=0):
    return mock.Mock(stdout=stdout, stderr=stderr, returncode=returncode)


# ---------------------------------------------------------------------------
# _parse_search_args
# ---------------------------------------------------------------------------

class ParseSearchArgsTests(unittest.TestCase):
    def test_defaults_to_default_limit(self):
        query, limit = _parse_search_args(["image", "converter"])
        self.assertEqual(query, "image converter")
        self.assertEqual(limit, DEFAULT_SEARCH_LIMIT)

    def test_flag_limit_separate_value(self):
        query, limit = _parse_search_args(["pdf", "--limit", "5"])
        self.assertEqual(query, "pdf")
        self.assertEqual(limit, 5)

    def test_delimited_limit_token_is_query_text(self):
        query, limit = _parse_search_args(["--", "--limit"])
        self.assertEqual(query, "--limit")
        self.assertEqual(limit, DEFAULT_SEARCH_LIMIT)

    def test_short_limit_token_is_query_text(self):
        query, limit = _parse_search_args(["-n", "3", "json"])
        self.assertEqual(query, "-n 3 json")
        self.assertEqual(limit, DEFAULT_SEARCH_LIMIT)

    def test_flag_limit_equals(self):
        query, limit = _parse_search_args(["--limit=7", "csv"])
        self.assertEqual(query, "csv")
        self.assertEqual(limit, 7)

    def test_limit_capped_at_max(self):
        _, limit = _parse_search_args(["foo", "--limit", str(MAX_SEARCH_LIMIT * 10)])
        self.assertEqual(limit, MAX_SEARCH_LIMIT)

    def test_non_positive_limit_rejected(self):
        with self.assertRaises(ValueError):
            _parse_search_args(["foo", "--limit", "0"])

    def test_non_integer_limit_rejected(self):
        with self.assertRaises(ValueError):
            _parse_search_args(["foo", "--limit", "many"])

    def test_missing_limit_value_rejected(self):
        with self.assertRaises(ValueError):
            _parse_search_args(["foo", "--limit"])


class PackageInstallTests(unittest.TestCase):
    def test_package_name_validation_rejects_options(self):
        self.assertTrue(_valid_package_name("python3-venv"))
        self.assertTrue(_valid_package_name("curl:amd64"))
        self.assertFalse(_valid_package_name("-oDpkg::Pre-Invoke::=id"))
        self.assertFalse(_valid_package_name("../curl"))

    def test_need_rejects_invalid_package_before_policy_check(self):
        with mock.patch.object(main.policy, "require") as require:
            result = cmd_need(["-oDpkg::Pre-Invoke::=id"])
        self.assertIn("error", result)
        require.assert_not_called()

    def test_install_uses_hidden_clawd_broker(self):
        payload = json.dumps({"status": "accepted", "accepted": True, "request_id": "a" * 32})
        with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
            main.subprocess,
            "run",
            return_value=_fake_completed(stdout=payload),
        ) as runner:
            installed, failed, errors, pending = _apt_install(["curl"])
        self.assertEqual(installed, [])
        self.assertEqual(failed, [])
        self.assertEqual(errors, {})
        argv = runner.call_args[0][0]
        self.assertEqual(argv, [
            "/usr/local/bin/cos", "__package", "--retained", "ensure-packages", "curl",
        ])
        self.assertEqual(pending[0]["request_id"], "a" * 32)
        self.assertNotIn("after", pending[0])

    def test_need_submits_one_batch_before_the_requesting_app_can_be_retired(self):
        payload = json.dumps({"status": "accepted", "accepted": True, "request_id": "b" * 32})
        with _allow_policy(), mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
            main.subprocess, "run", return_value=_fake_completed(stdout=payload)
        ) as runner:
            result = cmd_need(["curl", "git"])
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0], [
            "/usr/local/bin/cos", "__package", "--retained", "ensure-packages", "curl", "git"
        ])
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["preflight"], "retained")
        self.assertEqual(result["installed"], [])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["transactions"][0]["packages"], ["curl", "git"])

    def test_payload_result_without_a_root_handoff_is_not_success(self):
        payload = json.dumps({"package": "curl", "after": {"installed": True}})
        with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
            main.subprocess, "run", return_value=_fake_completed(stdout=payload)
        ):
            installed, failed, errors, pending = _apt_install(["curl"])
        self.assertEqual(installed, [])
        self.assertEqual(failed, ["curl"])
        self.assertIn("handoff", errors["curl"])
        self.assertEqual(pending, [])

    def test_remove_uses_exact_package_scope(self):
        payload = json.dumps({"status": "accepted", "accepted": True, "request_id": "c" * 32})
        with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
            main.policy, "require"
        ) as require, mock.patch.object(
            main.subprocess, "run", return_value=_fake_completed(stdout=payload)
        ):
            result = main.run("remove", ["curl"])
        require.assert_called_once_with("sys.package", name="curl")
        self.assertEqual(result["status"], "accepted")
        self.assertNotIn("changed", result)

    def test_update_requires_wild_package_permission(self):
        payload = json.dumps({"action": "update-index"})
        with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
            main.policy, "require"
        ) as require, mock.patch.object(
            main.subprocess, "run", return_value=_fake_completed(stdout=payload)
        ):
            main.run("update", [])
        require.assert_called_once_with("sys.package", wild=True)


# ---------------------------------------------------------------------------
# cmd_search
# ---------------------------------------------------------------------------

class CmdSearchTests(unittest.TestCase):
    def test_empty_args_returns_error(self):
        result = cmd_search([])
        self.assertIn("error", result)

    def test_only_flag_no_query_returns_error(self):
        with _allow_policy():
            result = cmd_search(["--limit", "5"])
        self.assertIn("error", result)

    def test_returns_catalog_response_through_the_os_reader(self):
        response = {
            "query": "image", "count": 1,
            "results": [{"name": "imagemagick", "summary": "Image tools"}],
            "truncated": True, "hint": "Refine the query",
        }
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value=response
        ) as reader, mock.patch.object(main.subprocess, "run") as local:
            result = cmd_search(["image"])
        self.assertEqual(result, response)
        self.assertEqual(reader.call_args.args, (
            "/usr/local/bin/cos", ["__package_query", "search", "image", "25"], b"",
        ))
        local.assert_not_called()

    def test_unavailable_runtime_has_no_local_apt_fallback(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            side_effect=main.kernel.KernelUnavailable("no package reader"),
        ), mock.patch.object(main.subprocess, "run") as local:
            result = cmd_search(["foo"])
        self.assertEqual(result["results"], [])
        self.assertIn("no package reader", result["error"])
        local.assert_not_called()

    def test_os_denial_is_preserved_and_does_not_run_apt(self):
        denial = {"wire_version": 1, "ok": False, "code": "PERMISSION_DENIED", "error": "scope denied"}
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            side_effect=main.kernel.KernelDenied(denial),
        ), mock.patch.object(main.subprocess, "run") as local:
            result = cmd_search(["foo"])
        self.assertEqual(result["results"], [])
        self.assertEqual(result["denial"], denial)
        local.assert_not_called()

    def test_passes_one_canonical_query_and_bounded_limit(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value={"results": []}
        ) as reader:
            cmd_search(["pdf", "viewer", "--limit", "10"])
        self.assertEqual(reader.call_args.args[1], ["__package_query", "search", "pdf viewer", "10"])

    def test_option_like_query_is_data_not_apt_configuration(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value={"results": []}
        ) as reader:
            cmd_search(["--", "-oAPT::Update::Pre-Invoke=id"])
        self.assertEqual(reader.call_args.args[1], [
            "__package_query", "search", "-oAPT::Update::Pre-Invoke=id", "25",
        ])


# ---------------------------------------------------------------------------
# cmd_show
# ---------------------------------------------------------------------------

class CmdShowTests(unittest.TestCase):
    def test_empty_args(self):
        result = cmd_show([])
        self.assertIn("error", result)

    def test_returns_structured_metadata(self):
        response = {
            "name": "imagemagick", "found": True, "version": "8:6.9.11.60",
            "section": "graphics", "homepage": "https://imagemagick.org/",
            "installed_size": "100", "depends": "libc6, libmagickcore",
            "summary": "image manipulation programs -- binaries",
            "description": "ImageMagick is a collection of tools for creating images.",
        }
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value=response
        ) as reader:
            result = cmd_show(["imagemagick"])
        self.assertEqual(result, response)
        self.assertEqual(reader.call_args.args[1], ["__package_query", "show", "imagemagick"])

    def test_unknown_package_returns_not_found(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            return_value={"name": "nope", "found": False, "error": "no package found"},
        ):
            result = cmd_show(["nope"])
        self.assertFalse(result["found"])
        self.assertEqual(result["name"], "nope")
        self.assertIn("no package", result["error"])

    def test_os_reader_missing(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            side_effect=main.kernel.KernelUnavailable("no package reader"),
        ):
            result = cmd_show(["foo"])
        self.assertFalse(result["found"])
        self.assertIn("no package reader", result["error"])

    def test_installed_snapshot_keeps_versions_and_does_not_parse_local_dpkg(self):
        response = {"packages": ["fixture-one"], "versions": {"fixture-one": "2.0"}}
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value=response
        ) as reader, mock.patch.object(main.subprocess, "run") as local:
            self.assertEqual(main.cmd_list([]), response)
        self.assertEqual(reader.call_args.args[1], ["__package_query", "installed"])
        local.assert_not_called()
        available = {
            "name": "FixtureCommand", "available": True,
            "type": "command", "details": "found at /usr/bin/FixtureCommand",
        }
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary", return_value=available
        ) as reader, mock.patch.object(main.subprocess, "run") as local, mock.patch.object(
            main.shutil, "which"
        ) as lookup:
            self.assertEqual(main.cmd_has(["FixtureCommand"]), available)
        self.assertEqual(reader.call_args.args[1], ["__package_query", "available", "FixtureCommand"])
        local.assert_not_called()
        lookup.assert_not_called()


# ---------------------------------------------------------------------------
# run() dispatcher
# ---------------------------------------------------------------------------

class RunDispatcherTests(unittest.TestCase):
    def test_unknown_command(self):
        result = run("flarp", [])
        self.assertIn("error", result)

    def test_search_dispatch(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            return_value={"count": 1, "results": [{"name": "abc", "summary": "a thing"}]},
        ):
            result = run("search", ["abc"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["name"], "abc")

    def test_show_dispatch(self):
        with _allow_policy(), mock.patch.object(
            main.kernel, "call_json_with_stdin_binary",
            return_value={"name": "abc", "found": True, "version": "1", "summary": "thing"},
        ):
            result = run("show", ["abc"])
        self.assertTrue(result["found"])
        self.assertEqual(result["name"], "abc")


@pytest.mark.parametrize(("command", "arguments", "handler", "positionals"), [
    ("need", {"packages": ["curl", "git"]}, "cmd_need", ["curl", "git"]),
    ("has", {"name": "curl"}, "cmd_has", ["curl"]),
    ("list", {}, "cmd_list", []),
    ("search", {"query": ["text", "editor"], "limit": 3}, "cmd_search", ["text", "editor"]),
    ("show", {"name": "curl"}, "cmd_show", ["curl"]),
    ("remove", {"package": "curl"}, "_single_package_action", ["curl"]),
    ("purge", {"package": "curl"}, "_single_package_action", ["curl"]),
    ("upgrade", {"package": "curl"}, "_single_package_action", ["curl"]),
    ("hold", {"package": "curl"}, "_single_package_action", ["curl"]),
    ("unhold", {"package": "curl"}, "_single_package_action", ["curl"]),
    ("install-version", {"package": "curl", "version": "1.2-3"},
     "cmd_install_version", ["curl", "1.2-3"]),
    ("update", {}, "cmd_update", []),
    ("upgrade-all", {}, "cmd_upgrade_all", []),
])
def test_relocated_server_dispatches_all_manifest_operations(
    command, arguments, handler, positionals
):
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {"COS_APP_MANIFEST": str(APP_DIR / "app.json")}
    ), mock.patch.object(mcp.App, "serve", autospec=True) as serve:
        load_local_module(APP_DIR / "server.py", "claw_test_pkg_server")
    app = serve.call_args.args[0]
    manifest = json.loads((APP_DIR / "app.json").read_text(encoding="utf-8"))
    listed = app._handle_request("tools/list", {}, True)
    assert {tool["name"] for tool in listed["tools"]} == {
        f"pkg.{operation}" for operation in manifest["operations"]
    }
    with mock.patch.object(main, handler, return_value={"operation": command}) as target:
        result = app._handle_request(
            "tools/call",
            authenticated_mcp_params({"name": f"pkg.{command}", "arguments": arguments}),
            True,
        )
    assert result["structuredContent"] == {"operation": command}
    target.assert_called_once()
    if handler == "_single_package_action":
        target.assert_called_once_with(command, positionals)
    elif command == "search":
        assert _parse_search_args(target.call_args.args[0]) == ("text editor", 3)
    else:
        target.assert_called_once_with(positionals)


if __name__ == "__main__":
    unittest.main()
