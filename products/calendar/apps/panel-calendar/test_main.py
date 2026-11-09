import json
from pathlib import Path

APP = Path(__file__).resolve().parent


def test_identity_and_narrow_calendar_grant_are_preserved():
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "panel-calendar"
    assert manifest["runtime"] == "binary"
    assert manifest["entry"] == manifest["mcp"]["entry"] == "bin/claw-applet-calendar"
    assert manifest["mcp"]["transport"] == "stdio"
    assert manifest["mcp"]["lifecycle"] == "lazy"
    assert list(manifest["operations"]) == ["open"]
    needs = manifest["operations"]["open"]["needs"]
    assert len(needs) == 1
    assert needs[0]["verb"] == "data.db.read"
    assert needs[0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "calendar"},
    }
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert manifest["desktop"]["exec"] == "open"


def test_day_tool_is_read_only_and_uses_only_the_existing_calendar_scope():
    manifest = json.loads((APP / "app.json").read_text())
    tools = manifest["mcp"]["tools"]
    assert [tool["name"] for tool in tools] == ["panel-calendar.day"]
    assert tools[0]["needs"] == manifest["operations"]["open"]["needs"]
    assert [(arg["name"], arg["kind"], arg["required"]) for arg in tools[0]["args"]] == [
        ("date", "text", True),
    ]
    assert [effect["kind"] for effect in tools[0]["effects"]] == ["read"]
