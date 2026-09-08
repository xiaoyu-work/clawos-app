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


def test_native_staging_preserves_complete_ui_backend_and_license(tmp_path):
    stage = module(ROOT / "tools/stage_native.py")
    assert stage.stage("clipboard", tmp_path) == ["claw-applet-clipboard"]
    output = tmp_path / "claw-applet-clipboard"
    for source in (NATIVE / "claw-applet-clipboard").rglob("*"):
        if source.is_file():
            assert (output / source.relative_to(NATIVE / "claw-applet-clipboard")).read_bytes() == source.read_bytes()
    assert (output / "LICENSE").read_bytes() == (NATIVE / "LICENSE").read_bytes()
    entry = (output / "data/com.clawos.AppletClipboard.desktop").read_text()
    assert "cos app panel-clipboard open" in entry
    assert "Icon=edit-paste-symbolic" in entry


def test_native_build_has_no_app_or_authority_dependency(tmp_path):
    builder = module(ROOT / "tools/native_build.py")
    builder.prepare("clipboard", tmp_path / "platform/desktop/toolkit", tmp_path / "build")
    manifest = tomllib.loads((tmp_path / "build/Cargo.toml").read_text())
    assert not any("path" in value for value in manifest["dependencies"].values()
                   if isinstance(value, dict))
    patch = manifest["patch"]["https://github.com/pop-os/libcosmic"]
    assert len(patch) == 17
    assert all(str(tmp_path / "platform/desktop/toolkit") in value["path"]
               for value in patch.values())
    assert manifest["package"]["autobins"] is False


def test_history_panel_stages_independently_of_selection_app(tmp_path):
    stage = module(ROOT / "tools/stage.py")
    assert stage.stage("clipboard", tmp_path, ["panel-clipboard"]) == ["panel-clipboard"]
    assert not (tmp_path / "usr/lib/cos/apps/clipboard-manager").exists()
    assert not (tmp_path / "usr/lib/cos/apps/panel-clipboard/test_main.py").exists()
