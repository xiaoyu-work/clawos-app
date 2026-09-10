import json
import os
from pathlib import Path
import subprocess

APP = Path(__file__).resolve().parent


def test_launcher_executes_only_its_standalone_native_binary(tmp_path):
    binary = tmp_path / "claw-applet-widget-rail"
    binary.write_text("#!/bin/sh\nprintf '%s:%s\\n' \"${0##*/}\" \"$#\"\n")
    binary.chmod(0o755)
    result = subprocess.run([str(APP / "main.sh")], check=True, capture_output=True,
                            text=True, env={**os.environ, "PATH": str(tmp_path)})
    assert result.stdout.splitlines() == ["claw-applet-widget-rail:0"]


def test_identity_and_independent_original_grants():
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "widget-rail"
    assert manifest["runtime"] == "shell"
    assert manifest["entry"] == "main.sh"
    assert "mcp" not in manifest
    assert list(manifest["operations"]) == ["open"]
    needs = manifest["operations"]["open"]["needs"]
    assert [(need["verb"], need["scope"]) for need in needs] == [
        ("data.db.read", {"kind": "fixed", "scope": {"kind": "name", "value": "calendar"}}),
        ("sys.observe", {"kind": "wild"}),
        ("agent.observe", {"kind": "fixed", "scope": {"kind": "name", "value": "tasks"}}),
    ]
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert manifest["icon"] == "view-grid-symbolic"
    assert (APP / "main.sh").stat().st_mode & 0o111
