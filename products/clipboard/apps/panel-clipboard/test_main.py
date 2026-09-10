import json
import os
from pathlib import Path
import subprocess

APP = Path(__file__).resolve().parent


def test_launcher_executes_only_its_standalone_native_binary(tmp_path):
    binary = tmp_path / "claw-applet-clipboard"
    binary.write_text("#!/bin/sh\nprintf '%s:%s\\n' \"${0##*/}\" \"$#\"\n")
    binary.chmod(0o755)
    result = subprocess.run([str(APP / "main.sh")], check=True, capture_output=True, text=True,
                            env={**os.environ, "PATH": str(tmp_path)})
    assert result.stdout.splitlines() == ["claw-applet-clipboard:0"]


def test_identity_and_separate_history_grants_are_preserved():
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "panel-clipboard"
    assert manifest["runtime"] == "shell"
    assert manifest["entry"] == "main.sh"
    assert "mcp" not in manifest
    assert list(manifest["operations"]) == ["open"]
    needs = manifest["operations"]["open"]["needs"]
    assert [need["verb"] for need in needs] == ["clipboard.read", "clipboard.write"]
    assert all(need["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "history"},
    } for need in needs)
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert manifest["icon"] == "edit-paste-symbolic"
    assert (APP / "main.sh").stat().st_mode & 0o111
