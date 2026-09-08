"""Preserve the native Store's independent, read-only package contract."""

import json
from pathlib import Path
from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]


def test_native_identity_and_grants():
    manifest = json.loads(Path(__file__).with_name("app.json").read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == ("cosmic-store", "binary", 2)
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-store"
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"store.search", "store.installed", "store.show", "store.open"}
    for name in ("store.search", "store.installed", "store.show"):
        assert [need["verb"] for need in tools[name]["needs"]] == ["sys.observe"]
    assert tools["store.show"]["needs"][0]["scope"] == {"kind": "from-arg", "arg": "name"}
    assert tools["store.open"]["needs"][0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "cosmic-store"},
    }
    assert tools["store.open"]["needs"][0]["verb"] == "proc.spawn"


def test_staging_keeps_pkg_and_store_independent(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "store_stage")
    assert set(stage.stage("store", tmp_path)) == {"pkg", "cosmic-store"}
    installed = tmp_path / "usr/lib/cos/apps"
    assert {path.name for path in (installed / "cosmic-store").iterdir()} == {"app.json"}
    assert (installed / "pkg/main.py").read_bytes() == (PRODUCT / "apps/pkg/main.py").read_bytes()
