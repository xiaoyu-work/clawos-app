"""Editor descriptor, native inputs and installed identity contracts."""

import json
from pathlib import Path
import tomllib

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]
MANIFEST = Path(__file__).with_name("app.json")


def test_manifest_preserves_exact_authority_and_ai_identity():
    manifest = json.loads(MANIFEST.read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == (
        "cosmic-edit", "binary", 2,
    )
    assert manifest["entry"] == manifest["mcp"]["entry"] == "bin/cosmic-edit"
    assert manifest["desktop"]["exec"] == "--gui"
    assert manifest["ai"] == {
        "budget": {"monthly_units": 200000},
        "safety": "strict", "origins": ["external-content"],
    }
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {f"edit.{name}" for name in (
        "read", "write", "replace_range", "open", "summarize", "explain", "rewrite",
    )}
    for tool in tools.values():
        for need in tool["needs"]:
            if need["verb"].startswith("fs."):
                assert need["scope"] == {"kind": "from-arg", "arg": "path"}
    assert [need["verb"] for need in tools["edit.replace_range"]["needs"]] == [
        "fs.read", "fs.write",
    ]
    launch, read = tools["edit.open"]["needs"]
    assert launch["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "com.clawos.Edit"},
    }
    assert read["when"] == {"kind": "arg-present", "arg": "path"}


def test_stages_complete_native_source_separately_from_descriptor(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "editor_stage")
    native = load_local_module(ROOT / "tools/stage_native.py", "editor_native_stage")
    assert stage.stage("editor", tmp_path / "installed") == ["cosmic-edit"]
    installed = tmp_path / "installed/usr/lib/cos/apps/cosmic-edit"
    assert {path.name for path in installed.iterdir()} == {"app.json"}
    assert (installed / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert native.stage("editor", tmp_path / "native") == ["cosmic-edit"]
    staged = tmp_path / "native/cosmic-edit"
    source = PRODUCT / "native/cosmic-edit"
    for path in source.rglob("*"):
        if path.is_file():
            assert (staged / path.relative_to(source)).read_bytes() == path.read_bytes()
    assert (staged / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert "Exec=cosmic-edit %F" in (staged / "res/com.clawos.Edit.desktop").read_text()


def test_standalone_build_rewrites_only_shared_runtime_paths(tmp_path):
    native = load_local_module(ROOT / "tools/native_build.py", "editor_native_build")
    toolkit = tmp_path / "platform/desktop/toolkit"
    destination = tmp_path / "native"
    native.prepare("editor", toolkit, destination)
    cargo = tomllib.loads((destination / "Cargo.toml").read_text())
    for library in ("claw-os-sdk", "cos-runtime"):
        assert cargo["dependencies"][library]["path"] == str(
            tmp_path / "platform" / library / "rust",
        )
    assert cargo["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic.git"
    assert cargo["dependencies"]["cosmic-files"]["default-features"] is False
    assert "patch" not in cargo
    assert (destination / "Cargo.lock").read_bytes() == (
        PRODUCT / "native/cosmic-edit/Cargo.lock"
    ).read_bytes()
    assert (destination / "app.json").read_bytes() == MANIFEST.read_bytes()
