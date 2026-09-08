import json
import os
import pathlib
import sys
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module


APP_DIR = pathlib.Path(__file__).parent
main = load_local_module(
    APP_DIR / "main.py",
    "claw_test_accessibility_manager_main",
    clear_modules=("_shared",),
)


def test_magnifier_uses_accessibility_control_scope():
    completed = mock.Mock(
        returncode=0,
        stdout=json.dumps({"changed": True}),
        stderr="",
    )
    with mock.patch.dict(os.environ, {"COS_BIN": "/usr/local/bin/cos"}), mock.patch.object(
        main.policy, "require"
    ) as require, mock.patch.object(main.subprocess, "run", return_value=completed) as run:
        result = main.set_toggle("magnifier", "on")
    require.assert_called_once_with("ui.accessibility", name="control")
    assert run.call_args.args[0] == [
        "/usr/local/bin/cos",
        "__accessibility",
        "magnifier",
        "--value",
        "on",
    ]
    assert result["changed"] is True


def test_invalid_filter_is_rejected_before_policy():
    with mock.patch.object(main.policy, "require") as require:
        with pytest.raises(ValueError, match="filter requires one of"):
            main.set_filter("custom")
    require.assert_not_called()


@pytest.mark.parametrize(("toggle", "state"), [
    ("unknown", "on"),
    ("magnifier", "enabled"),
])
def test_invalid_toggle_is_rejected_before_policy(toggle, state):
    with mock.patch.object(main.policy, "require") as require, mock.patch.object(
        main, "_broker"
    ) as broker:
        with pytest.raises(ValueError):
            main.set_toggle(toggle, state)
    require.assert_not_called()
    broker.assert_not_called()


@pytest.mark.parametrize(("action", "arguments", "value"), [
    ("status", {}, None),
    *[(toggle, {"state": state}, state)
      for toggle in sorted(main.TOGGLES) for state in ("on", "off")],
    *[("filter", {"filter": value}, value) for value in sorted(main.FILTERS)],
])
def test_relocated_sdk_preserves_choices_and_accessibility_scope(action, arguments, value):
    manifest = json.loads((APP_DIR / "app.json").read_text(encoding="utf-8"))
    assert "operations" not in manifest
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {
        f"accessibility-manager.{name}"
        for name in ("status", "screen-reader", "magnifier", "invert", "filter")
    }
    tool = tools[f"accessibility-manager.{action}"]
    verb, scope = (
        ("sys.observe", "accessibility") if action == "status"
        else ("ui.accessibility", "control")
    )
    assert len(tool["needs"]) == 1
    assert tool["needs"][0]["verb"] == verb
    assert tool["needs"][0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": scope},
    }
    if action != "status":
        choices = main.FILTERS if action == "filter" else {"on", "off"}
        assert set(tool["args"][0]["choices"]) == choices
    completed = mock.Mock(returncode=0, stdout=json.dumps({"action": action}), stderr="")
    with mock.patch.dict(sys.modules, {"main": main}), mock.patch.dict(
        os.environ, {
            "COS_APP_MANIFEST": str(APP_DIR / "app.json"),
            "COS_BIN": "/usr/local/bin/cos",
        }
    ):
        server = load_local_module(APP_DIR / "server.py", "claw_test_accessibility_manager_server")
        listed = server.app._handle_request("tools/list", {}, True)
        assert {tool["name"] for tool in listed["tools"]} == set(tools)
        with mock.patch.object(main.policy, "require") as require, mock.patch.object(
            main.subprocess, "run", return_value=completed
        ) as run:
            result = server.app._handle_request(
                "tools/call",
                authenticated_mcp_params({
                    "name": f"accessibility-manager.{action}", "arguments": arguments,
                }),
                True,
            )
        assert result["structuredContent"] == {"action": action}
        require.assert_called_once_with(verb, name=scope)
        tail = [] if value is None else ["--value", value]
        assert run.call_args.args[0] == ["/usr/local/bin/cos", "__accessibility", action, *tail]
        assert run.call_args.kwargs["stdin"] is main.subprocess.DEVNULL
        assert run.call_args.kwargs["timeout"] == main.TIMEOUT_SECS
