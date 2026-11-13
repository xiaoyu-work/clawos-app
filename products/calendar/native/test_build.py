import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[3]
NATIVE = Path(__file__).resolve().parent


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_native_staging_preserves_complete_ui_and_license(tmp_path):
    stage = module(ROOT / "tools/stage_native.py")
    assert stage.stage("calendar", tmp_path) == ["claw-applet-calendar"]
    output = tmp_path / "claw-applet-calendar"
    for source in (NATIVE / "claw-applet-calendar").rglob("*"):
        if source.is_file():
            assert (output / source.relative_to(NATIVE / "claw-applet-calendar")).read_bytes() == source.read_bytes()
    assert (output / "LICENSE").read_bytes() == (NATIVE / "LICENSE").read_bytes()
    assert (output / "Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    assert (output / "app.json").read_bytes() == (
        NATIVE.parent / "apps/panel-calendar/app.json"
    ).read_bytes()
    assert "Exec=claw-applet-calendar" in (
        output / "data/com.clawos.PanelCalendarButton.desktop"
    ).read_text()


def test_native_build_uses_pinned_toolkit_and_no_other_app(tmp_path):
    builder = module(NATIVE / "build.py")
    builder.prepare(tmp_path / "platform/desktop/toolkit", tmp_path / "build")
    manifest = tomllib.loads((tmp_path / "build/Cargo.toml").read_text())
    assert "claw-applet-widget-rail" not in manifest["dependencies"]
    assert manifest["dependencies"]["claw-os-sdk"]["path"] == str(
        tmp_path / "platform/claw-os-sdk/rust"
    )
    assert {name for name, value in manifest["dependencies"].items()
            if isinstance(value, dict) and "path" in value} == {"claw-os-sdk"}
    patch = manifest["patch"]["https://github.com/pop-os/libcosmic"]
    assert len(patch) == 17
    assert all(str(tmp_path / "platform/desktop/toolkit") in value["path"]
               for value in patch.values())
    assert manifest["bin"] == [{"name": "claw-applet-calendar", "path": "src/main.rs"}]
    assert manifest["profile"]["release"]["opt-level"] == 1
    assert (tmp_path / "build/Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()


def test_desktop_identity_can_be_staged_without_calendar_backend(tmp_path):
    stage = module(ROOT / "tools/stage.py")
    assert stage.stage("calendar", tmp_path, ["panel-calendar"]) == ["panel-calendar"]
    assert not (tmp_path / "usr/lib/cos/apps/calendar").exists()
    assert not (tmp_path / "usr/lib/cos/apps/panel-calendar/test_main.py").exists()


def test_install_requires_explicit_build_staging_not_live_root(tmp_path):
    just = shutil.which("just")
    if just is None:
        pytest.skip("native package staging requires just")
    probe = tmp_path / "unexpected-install"
    installer = tmp_path / "install"
    installer.write_text('#!/bin/sh\nprintf called > "$INSTALL_PROBE"\nexit 99\n')
    installer.chmod(0o700)
    generation = tmp_path / "unexpected-generation"
    python = tmp_path / "python3"
    python.write_text('#!/bin/sh\nprintf called > "$GENERATION_PROBE"\nprintf "%s\\n" "$DESKTOP_PROBE"\n')
    python.chmod(0o700)
    env = {
        "PATH": f"{tmp_path}{os.pathsep}{os.defpath}", "INSTALL_PROBE": str(probe),
        "GENERATION_PROBE": str(generation), "DESKTOP_PROBE": str(tmp_path / "generated.desktop"),
        "CLAW_NATIVE_DESKTOP_METADATA": str(ROOT / "tools/native_desktop_metadata.py"),
    }
    command = [just, "--justfile", str(NATIVE / "claw-applet-calendar/justfile")]
    for root in ["", "/", "//", "/usr/.."]:
        result = subprocess.run(command + [f"rootdir={root}", "install"],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert not probe.exists(), result.stderr
        assert not generation.exists(), result.stderr
    result = subprocess.run(command + [f"rootdir={tmp_path / 'stage'}", "install"],
                            env=env, capture_output=True, text=True, timeout=10)
    assert probe.read_text() == "called", result.stderr


@pytest.mark.parametrize("product,component,desktop_id", [
    ("calendar", "claw-applet-calendar", "com.clawos.PanelCalendarButton"),
    ("desktop-widgets", "claw-applet-widget-rail", "com.clawos.AppletWidgetRail"),
    ("clipboard", "claw-applet-clipboard", "com.clawos.AppletClipboard"),
])
def test_desktop_install_uses_only_this_packages_cargo_reported_output(
    tmp_path, product, component, desktop_id,
):
    helper = module(ROOT / "tools/native_desktop_metadata.py")
    root = ROOT / "products" / product / "native" / component
    package_id = f"opaque-{product}-package-id"
    metadata = {"packages": [{
        "id": package_id, "manifest_path": str(root / "Cargo.toml"),
    }]}
    generated = tmp_path / "new-cargo-layout/intermediate/package/out"
    generated.mkdir(parents=True)
    desktop = generated / f"{desktop_id}.desktop"
    desktop.write_text("original localized build output")
    messages = [
        {"reason": "build-script-executed", "package_id": "unrelated-dependency", "out_dir": str(tmp_path)},
        {"reason": "build-script-executed", "package_id": package_id, "out_dir": str(generated)},
    ]
    with mock.patch.object(helper.subprocess, "check_output", side_effect=[
        json.dumps(metadata), "\n".join(map(json.dumps, messages)),
    ]) as cargo:
        assert helper.desktop_file("release", desktop_id, root) == desktop
    assert "--release" in cargo.call_args.args[0]
    for records in [messages[:1], messages + [messages[-1]]]:
        with mock.patch.object(helper.subprocess, "check_output", side_effect=[
            json.dumps(metadata), "\n".join(map(json.dumps, records)),
        ]), pytest.raises(RuntimeError, match="Cargo did not report"):
            helper.desktop_file("release", desktop_id, root)
