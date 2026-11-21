"""Web App contracts independent of the native browser engine."""

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
    with mock.patch.object(
        web.browser_bridge, "request", return_value={"result": payload},
    ) as browser, mock.patch.object(web.policy, "require") as require:
        result = web.run("read", ["https://exam\u00adple.com/path", "--timeout=7"])
    require.assert_called_once_with("net.dial", host="example.com:443")
    browser.assert_called_once_with(
        "render", url="https://example.com/path", timeout_secs=7,
        output={"kind": "eval", "expression": web._EXTRACT_JS},
        selector=None, user_agent=None,
    )
    assert result == {"url": "https://example.com/path", **payload, "engine": "helium"}


def test_missing_renderer_does_not_fall_back_to_direct_network():
    with mock.patch.object(
        web.browser_bridge, "request", side_effect=web.browser_bridge.BrowserUnavailable("renderer unavailable"),
    ), mock.patch.object(web, "open_url") as direct, mock.patch.object(web.policy, "require"):
        assert web.run("read", ["https://example.com"]) == {"error": "renderer unavailable"}
    direct.assert_not_called()


def test_summarize_requires_ai_authority_before_loading_external_content():
    with mock.patch.object(
        web.policy, "require", side_effect=web.policy.PolicyUnavailable("fixture unavailable")
    ) as require, mock.patch.object(web, "_cmd_read") as read:
        result = web.run("summarize", ["https://example.com"])
    require.assert_called_once_with("ai.chat.untrusted", wild=True)
    read.assert_not_called()
    assert "capability check failed" in result["error"]
