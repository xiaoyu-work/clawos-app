"""Capture descriptor, complete native source graph and installed identity."""

import json
from pathlib import Path
import tomllib

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]
MANIFEST = Path(__file__).with_name("app.json")
NATIVE = PRODUCT / "native/cosmic-screenshot"


def test_manifest_keeps_identity_and_separates_capture_write_and_clipboard():
    manifest = json.loads(MANIFEST.read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == (
        "cosmic-screenshot", "binary", 2,
    )
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-screenshot"
    tool, = manifest["mcp"]["tools"]
    assert tool["name"] == "screenshot.capture"
    args = {arg["name"]: arg for arg in tool["args"]}
    assert set(args) == {"interactive", "modal", "save_dir"}
    assert args["interactive"]["default"] is False
    assert args["interactive"]["choices"] == [False]
    assert args["modal"]["default"] is True
    assert args["save_dir"]["default"] == "~/Pictures"
    capture, write = tool["needs"]
    assert capture["verb"] == "desktop.capture"
    assert capture["scope"] == {"kind": "fixed", "scope": {"kind": "name", "value": "screen"}}
    assert write["verb"] == "fs.write"
    assert write["scope"] == {"kind": "from-arg", "arg": "save_dir"}
    assert write["when"] == {"kind": "arg-equals", "arg": "interactive", "value": False}
    assert all(not need["verb"].startswith("clipboard.") for need in tool["needs"])


def test_complete_native_graph_and_resources_are_staged_without_os_implementation(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "capture_stage")
    native = load_local_module(ROOT / "tools/stage_native.py", "capture_native_stage")
    assert stage.stage("capture", tmp_path / "installed") == ["cosmic-screenshot"]
    installed = tmp_path / "installed/usr/lib/cos/apps/cosmic-screenshot"
    assert (installed / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert not (installed / "test_main.py").exists()
    assert native.stage("capture", tmp_path / "native") == ["cosmic-screenshot"]
    target = tmp_path / "native/cosmic-screenshot"
    for source in NATIVE.rglob("*"):
        if source.is_file():
            staged = target / source.relative_to(NATIVE)
            assert staged.read_bytes() == source.read_bytes()
            assert staged.stat().st_mode & 0o777 == source.stat().st_mode & 0o777
    assert (target / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert len(list((target / "i18n").glob("*/cosmic_screenshot.ftl"))) == 72
    assert len(list((target / "resources/icons").rglob("com.clawos.Screenshot.*"))) == 8
    assert "Exec=cosmic-screenshot" in (target / "resources/com.clawos.Screenshot.desktop").read_text()
    assert not (tmp_path / "installed/usr/bin").exists()
    assert not (target / "core").exists()
    assert not (target / "toolkit").exists()


def test_native_build_keeps_the_original_portal_graph_and_only_rewrites_runtime(tmp_path):
    native = load_local_module(ROOT / "tools/native_build.py", "capture_native_build")
    native.prepare("capture", tmp_path / "platform/desktop/toolkit", tmp_path / "native")
    manifest = tomllib.loads((tmp_path / "native/Cargo.toml").read_text())
    for library in ("claw-os-sdk", "cos-runtime"):
        assert manifest["dependencies"][library]["path"] == str(tmp_path / "platform" / library / "rust")
    assert "libcosmic" not in manifest["dependencies"]
    assert "patch" not in manifest
    assert "features" not in manifest
    assert manifest["dependencies"]["ashpd"] == {
        "version": "0.12", "default-features": False, "features": ["tokio"],
    }
    assert manifest["profile"]["release"]["lto"] == "fat"
    assert (tmp_path / "native/Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    production = "\n".join(path.read_text() for path in (NATIVE / "src").glob("*.rs"))
    assert "cos_runtime::fs::" not in production
    assert "cos_runtime::exec::" not in production
    assert 'cos_runtime::capture::screenshot' in production
    package = json.loads((PRODUCT / "package.json").read_text())
    assert package["native_process_test"] == "native/test_process.py"
    assert package["native_examples"] == ["capture-portal-fixture"]
