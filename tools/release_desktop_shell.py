"""Build and authenticate the Desktop Shell input to claw-os-desktop, not an App .deb."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import native_payload
import release_snapshots as snapshots
from platform_dependency import _download
from release import scan_native_payload
from release_common import ROOT, config, digest, run, write_json
from release_publish import GitHub, existing_release, require_publication_contract


WORK = ROOT / "build/desktop-shell-release"
APP = "desktop-shell"
ENTRY = "bin/claw-desktop-shell"
SHELL_QML = "resources/usr/share/claw-desktop-shell/shell.qml"
BUILD_FORMAT = "yuos.desktop-shell-build/v1"


def source_revision():
    return run(["git", "rev-parse", "HEAD"]).stdout.decode().strip()


def build(architecture, version):
    if "VERSION_CODENAME=trixie" not in Path("/etc/os-release").read_text().splitlines() or (
        run(["dpkg", "--print-architecture"]).stdout.decode().strip() != architecture
    ):
        raise ValueError("Desktop Shell must be built natively on the selected Debian 13 architecture")
    revision = source_revision()
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=WORK) as scratch:
        root = Path(scratch) / APP
        subprocess.run([
            sys.executable, ROOT / "tools/native_build.py", APP, "build", "--release", "--app-root", root,
        ], check=True, cwd=ROOT)
        selected = native_payload.plan(APP)
        dependencies = scan_native_payload(root, "claw-os-desktop", architecture, root / "bin", [
            root / "resources" / path for path in selected.private_resources
        ])
        write_json(root / "build.json", {
            "format": BUILD_FORMAT, "architecture": architecture, "release_version": version,
            "source_revision": revision, "depends": dependencies,
        })
        snapshots.write_archive(root, snapshots.tree_inventory(root, architecture),
                                WORK / f"unsigned-{architecture}.tar.gz")


def seal(root, output, provenance, key, *, architecture, version, revision):
    manifest = snapshots.read_metadata(root / "app.json")
    build = snapshots.read_metadata(root / "build.json")
    if (
        build["format"], build["architecture"], build["release_version"], build["source_revision"]
    ) != (BUILD_FORMAT, architecture, version, revision):
        raise ValueError("Desktop Shell build input is not from this release matrix")
    if manifest["id"] != APP or manifest["runtime"] != "binary" or (
        manifest.get("desktop", {}).get("exec") != "--gui"
        or {"mcp", "operations", "web_ui"}.intersection(manifest)
        or snapshots.manifest_entries(manifest) != [("operation/GUI", ENTRY)]
        or (root / ".provenance.json").exists()
    ):
        raise ValueError("Desktop Shell must have its unchanged unsigned GUI-only App layout")
    native_payload.validate_elf(root / ENTRY, architecture)
    provenance.check_binary()
    run([
        provenance.binary, "provenance", "sign", "--kind", "app", "--id", APP,
        "--version", manifest["version"], "--path", root, "--key", key,
        "--entrypoint", ENTRY, "--resource", SHELL_QML,
    ])
    (root / ".provenance.json").chmod(0o644)
    snapshots.verified_binding(root, provenance)
    snapshots.write_archive(root, snapshots.tree_inventory(root, architecture), output)


def publish(version, url, sha256, key_id):
    signing_material = os.environ.pop("CLAW_APPS_PROVENANCE_SIGNING_PRIVATE_KEY")
    require_publication_contract(config())
    github = GitHub()
    github.preflight()
    tag = f"desktop-shell-v{version}"
    revision = source_revision()
    if existing_release(github, tag, revision):
        raise ValueError("Desktop Shell release is already immutable")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith(
        "/xiaoyu-work/claw-os/releases/download/"
    ):
        raise ValueError("Use the owner-approved published Claw OS provenance CLI")
    snapshots.sha256_value(sha256)
    with tempfile.TemporaryDirectory(prefix="publish-", dir=WORK) as scratch:
        scratch = Path(scratch)
        tool = scratch / "yu"
        _download(url, tool)
        if digest(tool) != sha256:
            raise ValueError("Public provenance tool SHA256 mismatch")
        tool.chmod(0o755)
        provenance = snapshots.Provenance(tool, sha256, key_id)
        publisher = scratch / "publisher.json"
        publisher.write_text(os.environ["PROVENANCE_PUBLISHER"])
        run([tool, "provenance", "trust", "add", "--file", publisher])
        key = scratch / "key.json"
        with os.fdopen(os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(signing_material)
        assets = []
        try:
            for architecture in config()["architectures"]:
                root = scratch / architecture
                snapshots.extract_archive(WORK / f"unsigned-{architecture}.tar.gz", root)
                archive = scratch / f"desktop-shell-linux-{architecture}.tar.gz"
                seal(root, archive, provenance, key, architecture=architecture, version=version,
                     revision=revision)
                assets.append(archive)
        finally:
            key.unlink()
        github.api("git/refs", method="POST",
                   data={"ref": f"refs/tags/{tag}", "sha": revision}, allowed=(201,))
        _, draft = github.api("releases", method="POST", allowed=(201,), data={
            "tag_name": tag, "target_commitish": revision, "draft": True, "name": tag,
            "body": f"Signed Desktop Shell build inputs for claw-os-desktop. Source commit: {revision}.",
        })
        run(["gh", "release", "upload", tag, "--repo", github.repository, *assets])
        _, published = github.api(f"releases/{draft['id']}", method="PATCH",
                                  data={"draft": False, "make_latest": "false"})
        if published.get("immutable") is not True:
            raise ValueError("Desktop Shell release was not published immutably")
        existing_release(github, tag, revision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    native = commands.add_parser("build")
    native.add_argument("--architecture", choices=["amd64", "arm64"], required=True)
    release = commands.add_parser("publish")
    release.add_argument("--cos-url", required=True)
    release.add_argument("--cos-sha256", required=True)
    release.add_argument("--publisher-key-id", required=True)
    for action in (native, release):
        action.add_argument("--version", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.version):
        parser.error("Use an explicit MAJOR.MINOR.PATCH Desktop Shell release version")
    if args.command == "build":
        build(args.architecture, args.version)
    else:
        publish(args.version, args.cos_url, args.cos_sha256, args.publisher_key_id)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        detail = error.stderr or error.stdout
        raise SystemExit(detail.decode(errors="replace").strip() if detail else str(error))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"Desktop Shell release failed: {error}")
