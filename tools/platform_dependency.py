"""Fetch immutable development libraries, never a sibling checkout."""

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def prepare():
    lock = json.loads((ROOT / "platform.lock.json").read_text())
    revision = lock["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Platform dependency requires a full immutable Git revision")
    sources = lock["python_sources"]
    if sources != ["claw-os-sdk/python/src", "cos-runtime/python/src"]:
        raise ValueError("Platform dependency may contain only the SDK and first-party runtime")
    packages = lock["python_packages"]
    if packages != ["apps/_shared"]:
        raise ValueError("Platform packages may contain only the shared App library")
    destination = ROOT / "build" / "platform" / revision
    if not destination.exists():
        destination.mkdir(parents=True)
        git = ["git", "-C", str(destination)]
        subprocess.run([*git, "init", "--quiet"], check=True)
        subprocess.run([*git, "remote", "add", "origin", lock["repository"]], check=True)
        subprocess.run([*git, "sparse-checkout", "init", "--cone"], check=True)
        subprocess.run([*git, "sparse-checkout", "set", *sources, *packages], check=True)
        subprocess.run([*git, "fetch", "--quiet", "--depth=1", "--filter=blob:none",
                        "origin", revision], check=True)
        subprocess.run([*git, "checkout", "--quiet", "--detach", revision], check=True)
    git = ["git", "-C", str(destination)]
    actual = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    if actual != revision:
        raise RuntimeError("Cached platform dependency has the wrong revision")
    dirty = subprocess.check_output(
        [*git, "status", "--porcelain", "--untracked-files=normal"], text=True
    )
    if dirty:
        raise RuntimeError(f"Cached platform dependency is modified: {destination}")
    paths = [destination / source for source in sources]
    package_paths = [destination / package for package in packages]
    if not all(path.is_dir() for path in [*paths, *package_paths]) or not (
        destination / "apps/canonical_argv.py"
    ).is_file():
        raise RuntimeError("Cached platform dependency is incomplete")
    return [*paths, *(path.parent for path in package_paths)]


if __name__ == "__main__":
    for path in prepare():
        print(path)
