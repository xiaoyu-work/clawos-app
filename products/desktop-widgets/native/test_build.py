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
    assert stage.stage("desktop-widgets", tmp_path) == ["claw-applet-widget-rail"]
    output = tmp_path / "claw-applet-widget-rail"
    source_root = NATIVE / "claw-applet-widget-rail"
    for source in source_root.rglob("*"):
        if source.is_file():
            assert (output / source.relative_to(source_root)).read_bytes() == source.read_bytes()
    assert (output / "LICENSE").read_bytes() == (NATIVE / "LICENSE").read_bytes()
    entry = (output / "data/com.clawos.AppletWidgetRail.desktop").read_text()
    assert "cos app widget-rail open" in entry
    assert "Icon=view-grid-symbolic" in entry


def test_native_build_has_only_toolkit_dependencies(tmp_path):
    builder = module(ROOT / "tools/native_build.py")
    builder.prepare("desktop-widgets", tmp_path / "platform/desktop/toolkit",
                    tmp_path / "build")
    manifest = tomllib.loads((tmp_path / "build/Cargo.toml").read_text())
    assert not any("path" in value for value in manifest["dependencies"].values()
                   if isinstance(value, dict))
    assert not any(name.startswith("claw-applet-") for name in manifest["dependencies"])
    patch = manifest["patch"]["https://github.com/pop-os/libcosmic"]
    assert len(patch) == 17
    assert all(str(tmp_path / "platform/desktop/toolkit") in value["path"]
               for value in patch.values())
    assert manifest["package"]["autobins"] is False


def test_desktop_identity_stages_without_tests(tmp_path):
    stage = module(ROOT / "tools/stage.py")
    assert stage.stage("desktop-widgets", tmp_path, ["widget-rail"]) == ["widget-rail"]
    output = tmp_path / "usr/lib/cos/apps/widget-rail"
    assert (output / "main.sh").stat().st_mode & 0o111
    assert not (output / "test_main.py").exists()
