import importlib.util
from pathlib import Path
import tomllib

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
    assert "cos app panel-calendar open" in (
        output / "data/com.clawos.PanelCalendarButton.desktop"
    ).read_text()


def test_native_build_uses_pinned_toolkit_and_no_other_app(tmp_path):
    builder = module(NATIVE / "build.py")
    builder.prepare(tmp_path / "platform/desktop/toolkit", tmp_path / "build")
    manifest = tomllib.loads((tmp_path / "build/Cargo.toml").read_text())
    assert "claw-applet-widget-rail" not in manifest["dependencies"]
    patch = manifest["patch"]["https://github.com/pop-os/libcosmic"]
    assert len(patch) == 17
    assert all(str(tmp_path / "platform/desktop/toolkit") in value["path"]
               for value in patch.values())
    assert manifest["package"]["autobins"] is False


def test_desktop_identity_can_be_staged_without_calendar_backend(tmp_path):
    stage = module(ROOT / "tools/stage.py")
    assert stage.stage("calendar", tmp_path, ["panel-calendar"]) == ["panel-calendar"]
    assert not (tmp_path / "usr/lib/cos/apps/calendar").exists()
    assert not (tmp_path / "usr/lib/cos/apps/panel-calendar/test_main.py").exists()
