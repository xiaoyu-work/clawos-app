import json
from pathlib import Path

APP = Path(__file__).resolve().parent


def test_identity_and_independent_original_grants():
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "widget-rail"
    assert manifest["runtime"] == "binary"
    assert manifest["entry"] == manifest["mcp"]["entry"] == "bin/claw-applet-widget-rail"
    assert manifest["mcp"]["transport"] == "stdio"
    assert manifest["mcp"]["lifecycle"] == "lazy"
    assert list(manifest["operations"]) == ["open"]
    needs = manifest["operations"]["open"]["needs"]
    assert [(need["verb"], need["scope"]) for need in needs] == [
        ("data.db.read", {"kind": "fixed", "scope": {"kind": "name", "value": "calendar"}}),
        ("sys.observe", {"kind": "fixed", "scope": {"kind": "name", "value": "resources"}}),
        ("agent.observe", {"kind": "fixed", "scope": {"kind": "name", "value": "tasks"}}),
    ]
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert manifest["icon"] == "view-grid-symbolic"
    assert manifest["desktop"]["exec"] == "open"


def test_read_tools_have_separate_needs_not_the_gui_grant_union():
    manifest = json.loads((APP / "app.json").read_text())
    original = {need["verb"]: need for need in manifest["operations"]["open"]["needs"]}
    tools = manifest["mcp"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "widget-rail.calendar", "widget-rail.tasks", "widget-rail.system",
    ]
    assert [tool["needs"] for tool in tools] == [
        [original["data.db.read"]], [original["agent.observe"]], [original["sys.observe"]],
    ]
    for tool in tools:
        assert tool["args"] == []
        assert [effect["kind"] for effect in tool["effects"]] == ["read"]
