"""Retain the attached-browser extension's manifest and source inputs."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parent


def test_extension_identity_permissions_and_resources_are_preserved():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    app = json.loads((ROOT.parent / "apps/browser-attached/app.json").read_text())
    assert manifest["manifest_version"] == 3
    assert manifest["version"] == app["version"]
    assert manifest["permissions"] == ["tabs", "scripting", "activeTab", "nativeMessaging"]
    assert manifest["host_permissions"] == ["<all_urls>"]
    assert (ROOT / manifest["background"]["service_worker"]).is_file()
    assert (ROOT / manifest["action"]["default_popup"]).is_file()
    for script in manifest["content_scripts"]:
        assert script["all_frames"] is False
        for resource in script["js"]:
            assert (ROOT / resource).is_file()
    assert (ROOT / "popup.js").is_file()


@pytest.mark.parametrize("script", ["background.js", "content.js", "popup.js"])
def test_extension_javascript_parses(script):
    subprocess.run(["node", "--check", str(ROOT / script)], check=True, timeout=20)
