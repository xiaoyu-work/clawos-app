"""Build/test the native UI against the immutable Claw OS toolkit, not upstream styling."""

import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent


def prepare(toolkit: Path, destination: Path):
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(SOURCE / "claw-applet-calendar", destination)
    shutil.copy2(SOURCE / "Cargo.lock", destination / "Cargo.lock")
    patches = (SOURCE / "patches.toml").read_text()
    patches = patches.replace('"../toolkit', '"' + toolkit.as_posix())
    with (destination / "Cargo.toml").open("a") as manifest:
        manifest.write("\n" + patches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test", "check", "build"], default="test", nargs="?")
    options = parser.parse_args()
    specification = importlib.util.spec_from_file_location(
        "platform_dependency", ROOT / "tools/platform_dependency.py"
    )
    platform = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(platform)
    toolkit = platform.prepare_native()
    destination = ROOT / "build/calendar-native"
    prepare(toolkit, destination)
    subprocess.run(
        ["cargo", options.command, "--locked", "--manifest-path", str(destination / "Cargo.toml"),
         "--target-dir", str(ROOT / "build/calendar-target"), "--lib"],
        check=True, cwd=ROOT,
    )


if __name__ == "__main__":
    main()
