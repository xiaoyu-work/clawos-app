"""Web App contracts independent of the native browser engine."""

import json
from pathlib import Path
from unittest import mock

import pytest

from cos_runtime import mcp
from test_support import authenticated_mcp_params, load_local_module


APP_DIR = Path(__file__).parent
web = load_local_module(
    APP_DIR / "main.py",
    "claw_test_web_main",
    clear_modules=("_shared",),
)


def test_web_normalizes_the_launched_url_before_policy_and_network_use():
    assert (
        web._normalize_url("https://exam\u00adple.com/path")
        == "https://example.com/path"
    )


@pytest.mark.parametrize("command,arguments,positionals", [
    ("read", {"url": "https://example.com"}, ["https://example.com"]),
    ("scrape", {"urls": ["https://example.com", "https://example.org"]},
     ["https://example.com", "https://example.org"]),
    ("screenshot", {"url": "https://example.com", "output": "/tmp/web-test.png"},
     ["https://example.com"]),
    ("submit", {"url": "https://example.com", "data": '{"q":"hello"}'},
     ["https://example.com"]),
    ("summarize", {"url": "https://example.com"}, ["https://example.com"]),
])
def test_manifest_mcp_tools_dispatch_to_existing_handlers(command, arguments, positionals):
    with mock.patch.object(mcp.App, "serve", autospec=True) as serve:
        mcp.serve_manifest_operations(web.run, APP_DIR / "app.json")
    app = serve.call_args.args[0]
    with mock.patch.object(web, f"_cmd_{command}", return_value={"operation": command}) as handler:
        result = app._handle_request(
            "tools/call",
            authenticated_mcp_params({"name": f"web.{command}", "arguments": arguments}),
            True,
        )
    assert result["structuredContent"] == {"operation": command}
    handler.assert_called_once()
    assert handler.call_args.args[0][:len(positionals)] == positionals


def test_read_passes_the_canonical_url_to_policy_and_browser():
    payload = {"title": "Example", "text": "Page text", "links": []}
    with mock.patch.object(web, "_has_cos_browser", return_value=True), mock.patch.object(
        web, "_run_cos_browser", return_value=(json.dumps(payload), "", 0, None)
    ) as browser, mock.patch.object(web.policy, "require") as require:
        result = web.run("read", ["https://exam\u00adple.com/path", "--timeout=7"])
    require.assert_called_once_with("net.dial", host="example.com:443")
    assert browser.call_args.args[0][:5] == [
        "fetch", "https://example.com/path", "--quiet", "--timeout", "7",
    ]
    assert browser.call_args.args[1] == 7
    assert result == {"url": "https://example.com/path", **payload, "engine": "cos-browser"}


def test_plain_read_preserves_the_existing_missing_engine_path():
    with mock.patch.object(web, "_has_cos_browser", return_value=False), mock.patch.object(
        web, "_urllib_fallback", return_value={"engine": "urllib-fallback"}
    ) as fallback, mock.patch.object(web.policy, "require"):
        result = web.run("read", ["https://example.com", "--max-length=100"])
    fallback.assert_called_once_with("https://example.com", 100)
    assert result == {"engine": "urllib-fallback"}


@pytest.mark.parametrize("option", ["--html", "--eval=1+1"])
def test_engine_specific_reads_do_not_use_the_urllib_path(option):
    with mock.patch.object(web, "_has_cos_browser", return_value=False), mock.patch.object(
        web, "_urllib_fallback"
    ) as fallback, mock.patch.object(web.policy, "require"):
        result = web.run("read", ["https://example.com", option])
    assert "cos-browser is required" in result["error"]
    fallback.assert_not_called()


def test_summarize_requires_ai_authority_before_loading_external_content():
    with mock.patch.object(
        web.policy, "require", side_effect=web.policy.PolicyUnavailable("fixture unavailable")
    ) as require, mock.patch.object(web, "_cmd_read") as read:
        result = web.run("summarize", ["https://example.com"])
    require.assert_called_once_with("ai.chat.untrusted", wild=True)
    read.assert_not_called()
    assert "capability check failed" in result["error"]
