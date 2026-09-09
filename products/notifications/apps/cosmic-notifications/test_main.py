"""Complete native source, explicit shared libraries and durable OS intent."""

import json
from pathlib import Path
import tomllib

import pytest

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-notifications"
MANIFEST = Path(__file__).with_name("app.json")


def test_manifest_retains_identity_and_grant_with_explicit_durable_id_compatibility():
    manifest = json.loads(MANIFEST.read_text())
    assert (manifest["id"], manifest["runtime"], manifest["version"]) == (
        "cosmic-notifications", "binary", "0.2.0",
    )
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-notifications"
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {"notify.post", "notify.close"}
    for tool in tools.values():
        assert len(tool["needs"]) == 1
        assert tool["needs"][0]["verb"] == "ui.notify"
        assert tool["needs"][0]["scope"] == {"kind": "wild"}
        assert tool["needs"][0]["why"]["en"]
    assert tools["notify.close"]["args"][0]["kind"] == "text"
    assert {arg["name"] for arg in tools["notify.post"]["args"]} == {
        "summary", "body", "app_name", "icon", "expire_ms", "transient", "dedupe_key",
    }
    assert "desktop" in tools["notify.close"]["summary"]["en"]


def test_staging_preserves_complete_native_tree_license_modes_and_library_identity(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "notifications_stage")
    native = load_local_module(ROOT / "tools/stage_native.py", "notifications_native")
    assert stage.stage("notifications", tmp_path / "installed") == ["cosmic-notifications"]
    installed = tmp_path / "installed/usr/lib/cos/apps/cosmic-notifications"
    assert (installed / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert not (installed / "test_main.py").exists()
    assert not (tmp_path / "installed/usr/bin").exists()
    assert native.stage("notifications", tmp_path / "native") == ["cosmic-notifications"]
    target = tmp_path / "native/cosmic-notifications"
    for source in NATIVE.rglob("*"):
        if source.is_file():
            copied = target / source.relative_to(NATIVE)
            assert copied.read_bytes() == source.read_bytes()
            assert copied.stat().st_mode & 0o777 == source.stat().st_mode & 0o777
    assert (target / "LICENSE").read_bytes() == (NATIVE / "LICENSE.md").read_bytes()
    for relative in (
        ".cargo/config.toml", ".cargo/config.default", "Cargo.lock", "build.rs",
        "debian/rules", "debian/install", "flake.nix", "flake.lock", "hooks/pre-commit.hook",
        "src/glass.rs", "src/app.rs", "src/subscriptions/notifications.rs",
        "cosmic-notifications-util/src/image.rs", "cosmic-notifications-util/src/markup.rs",
        "cosmic-notifications-config/src/lib.rs", "examples/notification-presentation-fixture.rs",
    ):
        assert (target / relative).is_file(), relative
    package = json.loads((PRODUCT / "package.json").read_text())
    assert native.library_paths(PRODUCT, package) == {
        name: Path("cosmic-notifications") / name
        for name in ("cosmic-notifications-config", "cosmic-notifications-util")
    }
    assert package["native_packages"] == [
        "cosmic-notifications", "cosmic-notifications-config", "cosmic-notifications-util",
    ]
    assert not (target / "core").exists()
    assert not (target / "toolkit").exists()


@pytest.mark.parametrize("name,export", [
    ("cosmic-notifications-util", {"component": "other-app", "path": "util"}),
    ("cosmic-notifications-util", {"component": "cosmic-notifications", "path": "../other"}),
    ("cosmic-notifications-util", {"component": "cosmic-notifications", "path": "/private"}),
    ("cosmic-notifications-util", {"component": [], "path": "util"}),
    ("wrong-identity", {"component": "cosmic-notifications", "path": "cosmic-notifications-util"}),
])
def test_public_library_declarations_refuse_other_components_escape_and_wrong_identity(name, export):
    native = load_local_module(ROOT / "tools/stage_native.py", "notifications_libraries")
    package = json.loads((PRODUCT / "package.json").read_text())
    package["native_libraries"] = {name: export}
    with pytest.raises(ValueError):
        native.library_paths(PRODUCT, package)


def test_original_default_and_optional_graph_remain_separate_from_os_applet_renderer(tmp_path):
    build = load_local_module(ROOT / "tools/native_build.py", "notifications_build")
    build.prepare("notifications", tmp_path / "platform/desktop/toolkit", tmp_path / "prepared")
    cargo = tomllib.loads((tmp_path / "prepared/Cargo.toml").read_text())
    assert cargo["dependencies"]["claw-os-sdk"]["path"] == str(tmp_path / "platform/claw-os-sdk/rust")
    assert cargo["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic"
    assert cargo["dependencies"]["libcosmic"]["default-features"] is False
    assert {"autosize", "dbus-config", "a11y", "winit", "multi-window", "wayland", "tokio"} <= set(
        cargo["dependencies"]["libcosmic"]["features"]
    )
    assert cargo["dependencies"]["cosmic-panel-config"]["git"] == "https://github.com/pop-os/cosmic-panel"
    assert cargo["features"] == {"systemd": ["dep:tracing-journald"], "default": ["systemd"]}
    assert cargo["workspace"]["members"] == ["cosmic-notifications-util", "cosmic-notifications-config"]
    assert "patch" not in cargo
    assert (tmp_path / "prepared/Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()


def test_mcp_is_fixed_os_intent_and_never_an_authoritative_state_or_bus_owner():
    mcp = (NATIVE / "src/mcp.rs").read_text()
    assert '"/usr/local/bin/cos"' in mcp
    assert "cos_call_json_async_with_stdin_binary" in mcp
    assert '"__notifications"' in mcp
    assert "context.cancelled()" in mcp
    for forbidden in ("Connection::session", "notifications.json", "rusqlite", "COS_DATA_DIR", "cos app"):
        assert forbidden not in mcp
    package = json.loads((PRODUCT / "package.json").read_text())
    assert package["apps"] == ["apps/cosmic-notifications"]
    assert package["native_kind"] == "binary"
    assert package["native_process_test"] == "native/test_process.py"
    assert (PRODUCT / "native/test_process.py").is_file()
    assert "products/notifications" in (ROOT / "README.md").read_text()
    assert "`products/notifications/`" in (ROOT / "ARCHITECTURE.md").read_text()
    assert "Legacy `notify`" in (PRODUCT / "README.md").read_text()
    assert "f7ffabf329ab8e1ec46e131ddd1ed2800060d13a" in (PRODUCT / "PROVENANCE.md").read_text()
    workflow = (ROOT / ".github/workflows/test.yml").read_text()
    assert "if: matrix.product == 'notifications'" in workflow
    assert "python3 products/notifications/native/test_process.py" in workflow
