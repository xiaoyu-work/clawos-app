# SPDX-License-Identifier: GPL-3.0-only

import json
from pathlib import Path
import subprocess
import sys


def desktop_file(profile):
    if profile not in ("debug", "release"):
        raise ValueError("desktop metadata requires debug or release")
    root = Path(__file__).resolve().parent
    metadata = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--locked", "--format-version", "1", "--no-deps"],
        cwd=root,
    ))
    package = next(package for package in metadata["packages"]
                   if Path(package["manifest_path"]).resolve() == root / "Cargo.toml")
    command = ["cargo", "build", "--locked", "--package", package["id"], "--message-format=json"]
    if profile == "release":
        command.append("--release")
    output = subprocess.check_output(command, cwd=root, text=True)
    paths = []
    for line in output.splitlines():
        message = json.loads(line)
        if message.get("reason") == "build-script-executed" and message["package_id"] == package["id"]:
            paths.append(Path(message["out_dir"]) / "com.clawos.PanelCalendarButton.desktop")
    if len(paths) != 1 or not paths[0].is_file():
        raise RuntimeError("Cargo did not report this Calendar build's generated desktop entry")
    return paths[0]


if __name__ == "__main__":
    print(desktop_file(sys.argv[1]))
