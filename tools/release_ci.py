"""Provision declared release dependencies only on disposable GitHub Actions runners."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from release_common import ROOT
from release import load_plan

BASE = ["ca-certificates", "git", "gnupg", "gpgv", "dpkg-dev", "apt-utils", "xz-utils", "binutils"]
NATIVE = [
    "build-essential", "curl", "pkg-config", "cmake", "just",
    "libfontconfig-dev", "libfreetype-dev", "libwayland-dev", "libxkbcommon-dev",
    "libudev-dev", "libinput-dev", "libdbus-1-dev", "libsystemd-dev", "libegl-dev", "libgbm-dev",
]
EXTRA_NATIVE = {
    "editor": ["libglib2.0-dev"], "files": ["libglib2.0-dev"], "terminal": ["libglib2.0-dev"],
    "store": ["libflatpak-dev"],
    "media-player": ["libgstreamer1.0-dev", "libgstreamer-plugins-base1.0-dev", "libglib2.0-dev"],
    "settings": ["libpipewire-0.3-dev", "libpulse-dev", "libxkbregistry-dev", "libclang-dev",
                 "gettext", "libglib2.0-dev"],
}


def dependencies(plan, mode, architecture):
    result = list(BASE)
    if mode == "test":
        result.extend(["ripgrep", "bubblewrap", "dbus-daemon"])
    elif architecture != "all":
        result.extend(NATIVE)
        for selection in plan["selections"]:
            result.extend(EXTRA_NATIVE.get(selection, []))
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["test", "build"])
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--architecture", choices=["all", "amd64", "arm64"], default="all")
    options = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("CI provisioning is forbidden on a developer's host")
    scratch = ROOT / "build/ci-work"
    scratch.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "TMPDIR": str(scratch), "DEBIAN_FRONTEND": "noninteractive"}
    plan = load_plan(options.plan) if options.plan else {"selections": []}
    sources = next((path for path in [
        Path("/etc/apt/sources.list.d/debian.sources"),
        Path("/etc/apt/sources.list.d/ubuntu.sources"),
    ] if path.is_file() and path.stat().st_size), None)
    if sources is None:
        raise ValueError("The runner has no declared Debian/Ubuntu distribution sources")
    sudo = [] if os.geteuid() == 0 else ["sudo"]
    apt = [*sudo, "apt-get", "-o", f"Dir::Etc::sourcelist={sources}", "-o", "Dir::Etc::sourceparts=-"]
    subprocess.run([*apt, "update", "-qq"], check=True, env=environment)
    subprocess.run([*apt, "install", "--no-install-recommends", "-y",
                    *dependencies(plan, options.mode, options.architecture)], check=True, env=environment)
    if options.mode == "test":
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"],
                       check=True, cwd=ROOT, env=environment)
        if set(plan["selections"]).intersection({"files", "capability:document-engine"}):
            subprocess.run([sys.executable, "-m", "pip", "install",
                            "pymupdf", "python-docx", "openpyxl", "python-pptx"], check=True, env=environment)
        # This is an ephemeral runner's nested process fixture, never an installed OS gate.
        setting = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        if "notifications" in plan["selections"] and setting.exists():
            subprocess.run([*sudo, "sysctl", "-w", "kernel.apparmor_restrict_unprivileged_userns=0"], check=True)


if __name__ == "__main__":
    main()
