"""Historical Notifications archive helpers, disconnected from active releases."""

import argparse
import gzip
from pathlib import Path
import shutil
import tarfile
import tempfile

from release_common import ROOT, digest, version, work_path
from release_development import (
    copy_source, interface_roots, inventory, read_archive, source_closure, tar_entry, validate_interface,
)

FORMAT = "claw.app-interfaces/v1"
COMPONENT = "cosmic-notifications"
EXPORTS = {"cosmic-notifications-config", "cosmic-notifications-util"}
INTEGRATION_STATUS = "compatibility-only-pending-generic-contract"


def required_selections(plan):
    if "notifications" not in plan["selections"]:
        return set()
    return {"notifications"} if interface_roots(source_closure("notifications")) else set()


def declarations():
    roots = interface_roots(source_closure("notifications"))
    if set(roots) != EXPORTS:
        raise ValueError("No supported compatibility export is declared; do not export product libraries implicitly")
    interfaces = {}
    for name, (root, owner) in roots.items():
        item = validate_interface(name, root, roots)
        interfaces[name] = {**item, "path": f"{COMPONENT}/{name}", "owner": owner}
    return roots, interfaces


def prepare_sources(root, plan):
    roots, interfaces = declarations()
    license_file = ROOT / "products/notifications/native/LICENSE"
    for name, (source, _) in roots.items():
        destination = root / interfaces[name]["path"]
        copy_source(source, destination, boundary=source)
        if not any(path.name.upper().startswith("LICENSE") for path in destination.iterdir()):
            copy_source(license_file, destination / "LICENSE", boundary=license_file.parent)
    copy_source(license_file, root / COMPONENT / "LICENSE", boundary=license_file.parent)
    return {
        "format": FORMAT, "selection": "notifications", "version": plan["version"],
        "source_revision": plan["source_revision"], "source_date_epoch": plan["source_date_epoch"],
        "purpose": "os-build-interfaces-only", "native_interfaces": interfaces, "files": inventory(root),
    }


def build_interfaces(plan, selection, output):
    if selection != "notifications":
        return None
    version(plan["version"])
    output = work_path(output)
    output.mkdir(parents=True, exist_ok=True)
    root = output / ".notification-interfaces"
    root.mkdir()
    filename = f"claw-app-interfaces-{plan['version']}.tar.gz"
    target = output / filename
    try:
        manifest = prepare_sources(root, plan)
        if target.exists():
            raise ValueError("Refusing to overwrite a versioned interface archive")
        with target.open("xb") as stream, gzip.GzipFile(
            fileobj=stream, filename="", mode="wb", mtime=0, compresslevel=9,
        ) as compressed, tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, item in manifest["files"].items():
                tar_entry(archive, root, name, item, plan["source_date_epoch"])
        record = {
            "format": FORMAT, "selection": selection, "version": plan["version"],
            "integration_status": INTEGRATION_STATUS,
            "source_revision": plan["source_revision"], "filename": filename,
            "sha256": digest(target), "size": target.stat().st_size,
        }
        verify_interfaces(target, record, plan)
        return record
    finally:
        shutil.rmtree(root)


def verify_interfaces(path, record, plan):
    if record.get("integration_status") != INTEGRATION_STATUS or record["format"] != FORMAT or (
        record["selection"] != "notifications"
    ) or record["filename"] != (
        f"claw-app-interfaces-{plan['version']}.tar.gz"
    ):
        raise ValueError("Invalid OS interface archive identity")
    with tempfile.TemporaryDirectory(prefix="interface-check-", dir=ROOT / "build") as temporary:
        expected = prepare_sources(Path(temporary), plan)
        manifest = read_archive(path, record, plan, compression="gz", expected_manifest=expected)
    _, interfaces = declarations()
    if manifest.get("purpose") != "os-build-interfaces-only" or manifest.get("native_interfaces") != interfaces:
        raise ValueError("OS interface archive does not match its declared pure libraries")
    for name in manifest["files"]:
        if name in (COMPONENT, f"{COMPONENT}/LICENSE"):
            continue
        if not any(name == item["path"] or name.startswith(item["path"] + "/") for item in interfaces.values()):
            raise ValueError("OS interface archive contains product implementation or unrelated sources")
    for name, item in interfaces.items():
        if not all(f"{item['path']}/{filename}" in manifest["files"] for filename in ("Cargo.toml", "src/lib.rs", "LICENSE")):
            raise ValueError(f"Incomplete OS interface crate: {name}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/app-interfaces-release")
    parser.parse_args()
    parser.error(
        "Notifications config/util release exports are retired; consume the published presentation SDK instead"
    )


if __name__ == "__main__":
    main()
