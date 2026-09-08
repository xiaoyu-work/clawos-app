"""Native Settings keeps only page discovery and its own fixed launch grant."""

import json
from pathlib import Path
from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]


def test_native_identity_and_exact_grants():
    manifest = json.loads(Path(__file__).with_name("app.json").read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == ("cosmic-settings", "binary", 2)
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-settings"
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"settings.list_pages", "settings.search", "settings.open"}
    assert tools["settings.list_pages"]["args"] == []
    assert tools["settings.list_pages"]["needs"] == tools["settings.search"]["needs"] == []
    assert tools["settings.search"]["args"][1]["default"] == 5
    assert tools["settings.open"]["needs"][0]["verb"] == "proc.spawn"
    assert tools["settings.open"]["needs"][0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "cosmic-settings"},
    }
    assert len(tools["settings.open"]["needs"]) == 1


def test_twelve_app_identities_remain_independent(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "settings_stage")
    installed = stage.stage("settings", tmp_path)
    assert len(installed) == 12 and len(set(installed)) == 12
    app = tmp_path / "usr/lib/cos/apps/cosmic-settings"
    assert {path.name for path in app.iterdir()} == {"app.json"}
    assert json.loads((app / "app.json").read_text())["id"] == "cosmic-settings"
