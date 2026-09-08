"""Product packaging must keep the established installed App contract."""

import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_stage", ROOT / "tools" / "stage.py")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


def test_mail_stage_contains_matching_app_and_ui_without_os_runtime(tmp_path):
    assert stage.stage("mail", tmp_path) == ["mail-ai"]
    app = tmp_path / "usr/lib/cos/apps/mail-ai"
    assert (app / "server.py").is_file()
    assert (app / "native_host.py").is_file()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/lib/cos/claw-mail-ai-host").exists()
    manifest = json.loads((app / "app.json").read_text())
    xpi = tmp_path / "usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi"
    with zipfile.ZipFile(xpi) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == manifest["version"]
        assert "test_contract.py" not in archive.namelist()
    with pytest.raises(FileExistsError):
        stage.stage("mail", tmp_path)
