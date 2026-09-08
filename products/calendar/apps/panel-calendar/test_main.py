import json
import os
from pathlib import Path
import subprocess

APP = Path(__file__).resolve().parent


def test_launcher_preserves_the_native_dispatch_and_arguments(tmp_path):
    binary = tmp_path / "cosmic-applets"
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    binary.chmod(0o755)
    result = subprocess.run([str(APP / "main.sh")], check=True, capture_output=True, text=True,
                            env={**os.environ, "PATH": str(tmp_path)})
    assert result.stdout.splitlines() == ["claw-applet-calendar"]


def test_identity_and_narrow_calendar_grant_are_preserved():
    manifest = json.loads((APP / "app.json").read_text())
    assert manifest["id"] == "panel-calendar"
    assert manifest["runtime"] == "shell"
    assert manifest["entry"] == "main.sh"
    assert list(manifest["operations"]) == ["open"]
    needs = manifest["operations"]["open"]["needs"]
    assert len(needs) == 1
    assert needs[0]["verb"] == "data.db.read"
    assert needs[0]["scope"] == {
        "kind": "fixed", "scope": {"kind": "name", "value": "calendar"},
    }
    assert manifest["desktop"]["single_instance"] is True
    assert manifest["desktop"]["panel_applet"] is True
    assert (APP / "main.sh").stat().st_mode & 0o111
