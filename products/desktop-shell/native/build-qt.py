#!/usr/bin/env python3
"""Build and stage the Desktop Shell's pinned Qt runtime."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "qt.lock.json"
INSTALL_DIR = Path("usr/share/claw-desktop-shell")
QT = "https://download.qt.io/official_releases/qt"


def run(*args, cwd=None, capture=False):
    return subprocess.run(
        args, cwd=cwd, check=True, text=True, capture_output=capture,
    ).stdout


def fetch(directory, url, filename, expected):
    path = directory / filename
    with tempfile.TemporaryDirectory(dir=directory) as incoming:
        candidate = Path(incoming) / filename
        if not path.is_file():
            run("curl", "--proto", "=https", "--proto-redir", "=https", "--fail",
                "--location", "--silent", "--show-error", "--retry", "3",
                "--output", candidate, url)
        else:
            candidate = path
        with candidate.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Incorrect pinned Qt source digest: {filename}")
        if candidate != path:
            candidate.rename(path)
    return path


def build(cache, jobs):
    lock = json.loads(LOCK.read_bytes())
    version = lock["version"]
    line = version.rsplit(".", 1)[0]
    release = f"{QT}/{line}"
    options = [
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DQT_BUILD_TESTS=OFF", "-DQT_BUILD_EXAMPLES=OFF",
    ]
    base_options = [
        "-release", "-shared", "-opensource", "-confirm-license",
        "-nomake", "examples", "-nomake", "tests",
        "-no-xcb", "-no-eglfs", "-no-linuxfb", "-no-feature-vnc",
        "-opengl", "desktop", "-sql-sqlite", "-system-sqlite",
    ]
    module_options = {
        "qtmultimedia": ["-DFEATURE_ffmpeg=OFF", "-DFEATURE_gstreamer=ON"],
        "qtimageformats": ["-DFEATURE_system_webp=ON", "-DINPUT_tiff=no"],
    }
    configuration = json.dumps([base_options, options, module_options]).encode()
    digest = hashlib.sha256(LOCK.read_bytes() + configuration).hexdigest()[:16]
    work = (cache / f"qt-{version}-{digest}").resolve()
    downloads = cache / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    prefix = work / "prefix"
    for module, expected in lock["modules"].items():
        name = f"{module}-everywhere-src-{version}.tar.xz"
        archive = fetch(downloads, f"{release}/{version}/submodules/{name}", name, expected)
        source = work / "src" / module
        output = work / "build" / module
        complete = output / "installed"
        if complete.is_file():
            continue
        if not source.is_dir():
            with tempfile.TemporaryDirectory(dir=work.parent) as incoming:
                run("tar", "-xf", archive, "-C", incoming, "--strip-components=1",
                    "--no-same-owner")
                if module == "qtbase":
                    for patch, sha in lock["qtbase_corrections"].items():
                        patch_file = fetch(downloads, f"{release}/{patch}", patch, sha)
                        # The advisory also patches upstream tests whose fixtures
                        # postdate this archive. Apply every non-test hunk strictly.
                        run("git", "apply", "--exclude=tests/**", patch_file, cwd=incoming)
                source.parent.mkdir(parents=True, exist_ok=True)
                # The build tree persists after an interrupted compile, not a partial source extraction.
                Path(incoming).rename(source)
        output.mkdir(parents=True, exist_ok=True)
        if module == "qtbase":
            run(source / "configure", "-prefix", prefix, *base_options,
                "--", "-G", "Ninja", *options, cwd=output)
        else:
            run(prefix / "bin/qt-configure-module", source, "--", "-G", "Ninja",
                *options, *module_options.get(module, ()), cwd=output)
        run("cmake", "--build", output, "--parallel", str(jobs))
        run("cmake", "--install", output)
        complete.touch()
    (prefix / "claw-qt-source").write_text(str(work / "src") + "\n")
    return prefix


def stage(prefix, destination):
    lock = json.loads(LOCK.read_bytes())
    base = destination / INSTALL_DIR
    qt = base / "qt"
    (qt / "lib").mkdir(parents=True)
    for library in sorted((prefix / "lib").glob("libQt6*.so." + lock["version"])):
        if library.name.startswith(("libQt6Test.so.", "libQt6QuickTest.so.",
                                    "libQt6QuickTestUtilsPrivate.so.")):
            continue
        names = re.findall(r"\(SONAME\).*\[([^/\]]+)\]", run("readelf", "-d", library, capture=True))
        if len(names) != 1:
            raise ValueError(f"Missing Qt SONAME: {library.name}")
        shutil.copyfile(library, qt / "lib" / names[0])

    build_artifacts = shutil.ignore_patterns(
        "*.a", "*.o", "*.prl", "*.debug", "*.pdb", "objects-*", "CMakeLists.txt",
    )

    def ignore_runtime_copy(directory, names):
        ignored = set(build_artifacts(directory, names))
        if Path(directory) == prefix / "qml":
            ignored.add("QtTest")
        elif Path(directory) == prefix / "qml" / "Qt":
            ignored.add("test")
        return ignored

    for name in ("plugins", "qml"):
        shutil.copytree(prefix / name, qt / name, ignore=ignore_runtime_copy)
    for required in ("lib/libQt6Core.so.6", "plugins/sqldrivers/libqsqlite.so",
                     "plugins/imageformats/libqwebp.so",
                     "qml/QtQuick/qmldir", "qml/QtQuick/Controls/qmldir"):
        if not (qt / required).is_file():
            raise ValueError(f"Private Qt runtime is incomplete: {required}")
    if not any((qt / "plugins/platforms").glob("libqwayland*.so")):
        raise ValueError("Private Qt runtime does not include a Wayland platform plugin")

    notices = base / "licenses/qt"
    notices.mkdir(parents=True)
    shutil.copyfile(LOCK, notices / LOCK.name)
    source = Path((prefix / "claw-qt-source").read_text().strip())
    for module in lock["modules"]:
        shutil.copytree(source / module / "LICENSES", notices / module)

    caelestia = base / "qml/Caelestia"
    for resource in sorted(base.rglob("*")):
        if resource.is_symlink():
            raise ValueError(f"Native stage must contain owned files, not links: {resource}")
        if resource.is_dir():
            resource.chmod(0o755)
            continue
        if not resource.is_file():
            continue
        resource.chmod(0o644)
        with resource.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        search = ["$ORIGIN", f"$ORIGIN/{os.path.relpath(qt / 'lib', resource.parent)}"]
        if resource.is_relative_to(caelestia):
            search.append(f"$ORIGIN/{os.path.relpath(caelestia / 'lib', resource.parent)}")
        run("patchelf", "--set-rpath", ":".join(search), resource)
        run("strip", "--strip-unneeded", resource)
    binary = destination / "usr/bin/claw-desktop-shell"
    run("patchelf", "--set-rpath",
        "$ORIGIN/../resources/usr/share/claw-desktop-shell/qt/lib", binary)
    run("strip", "--strip-unneeded", binary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("cache", type=Path)
    builder.add_argument("jobs", type=int)
    builder.add_argument("--prefix-file", type=Path)
    stager = commands.add_parser("stage")
    stager.add_argument("prefix", type=Path)
    stager.add_argument("destination", type=Path)
    options = parser.parse_args()
    if options.command == "build":
        if options.jobs < 1:
            parser.error("Qt requires a positive job count")
        cache = options.cache.resolve()
        cache.mkdir(parents=True, exist_ok=True)
        with (cache / ".build.lock").open("a") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            prefix = build(cache, options.jobs)
        if options.prefix_file:
            options.prefix_file.write_text(str(prefix))
        else:
            print(prefix, flush=True)
    else:
        stage(options.prefix, options.destination)


if __name__ == "__main__":
    main()
