"""Bind the signed official App Store to authenticated Debian release payloads."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from release_common import (
    compare_versions, config, digest, identity, package_record, run, version, work_path, write_json,
)
from release_payload import validate_install_tree
from release_signing import Signing
import release_snapshots as snapshots
from web_ui import DESCRIPTOR, read_descriptor


SCHEMA = "claw.app-store/v2"
INDEX = "index.json"
SIGNATURE = "index.json.asc"
RECORD_FIELDS = {
    "app_id", "app_version", "architecture", "artifact", "manifest", "provenance",
    "release_version", "release_tag", "display", "web_ui", "delivery",
}
PACKAGE_FIELDS = {"package", "version", "architecture", "size", "sha256", "apps"}
MAX_PACKAGE_BYTES = 1024**3


def app_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]*", value) is not None


def validate_packages(packages):
    if not isinstance(packages, list) or not packages or len(packages) > 10_000:
        raise ValueError("App Store requires its complete Debian package inventory")
    tuples, checksums, owners, assignments, latest = set(), {}, {}, set(), {}
    for package in packages:
        if not isinstance(package, dict) or set(package) != PACKAGE_FIELDS or (
            not isinstance(package["package"], str)
            or len(package["package"]) > 255
            or not re.fullmatch(r"claw-(?:app|cap|apps)-[a-z0-9][a-z0-9-]*", package["package"])
            or package["architecture"] not in ("all", "amd64", "arm64")
            or type(package["size"]) is not int or not 0 < package["size"] <= MAX_PACKAGE_BYTES
        ):
            raise ValueError("Invalid App Store Debian package record")
        version(package["version"])
        checksum = snapshots.sha256_value(package["sha256"])
        key = identity(package)
        if key in tuples or checksum in checksums:
            raise ValueError("Ambiguous App Store package tuple or digest reuse")
        tuples.add(key)
        checksums[checksum] = package
        owner_key = package["package"], package["architecture"]
        newest = latest.get(owner_key)
        if newest is None or compare_versions(package["version"], "gt", newest["version"]):
            latest[owner_key] = package
        apps = package["apps"]
        if not isinstance(apps, list) or len(apps) > 1000 or any(not app_id(value) for value in apps) or (
            apps != sorted(set(apps))
        ):
            raise ValueError("Package App IDs must be sorted and unique")
        for value in apps:
            owner = value, package["architecture"]
            assignment = *owner, package["version"]
            if assignment in assignments or owners.get(owner, package["package"]) != package["package"]:
                raise ValueError("Conflicting App/package assignments")
            assignments.add(assignment)
            owners[owner] = package["package"]
    for value, architecture in owners:
        if architecture != "all" and (value, "all") in owners:
            raise ValueError("Conflicting all/native App package assignments")
    return checksums, owners, latest


def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("App Store timestamps must be explicit UTC strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta():
        raise ValueError("App Store timestamps must be UTC")
    return parsed


def record_tag(record):
    display = record["display"]
    prefix = "app" if display["source_kind"] == "product" else "cap"
    return f"{prefix}-{display['source_name']}-v{record['release_version'].replace('~', '-')}"


def validate_index(index, *, now=None, allow_expired=False):
    settings = config()
    if not isinstance(index, dict) or set(index) != {
        "schema", "repository", "runtime_abi", "generation", "issued_at", "expires_at", "apps", "packages",
    } or index["schema"] != SCHEMA or index["repository"] != settings["repository"] or (
        type(index["runtime_abi"]) is not int or index["runtime_abi"] != 1
        or not isinstance(index["generation"], str)
        or not re.fullmatch(r"[1-9][0-9]{0,19}", index["generation"])
        or int(index["generation"]) > 2**64 - 1
        or not isinstance(index["apps"], list) or not index["apps"] or len(index["apps"]) > 1000
    ):
        raise ValueError("Invalid official App Store index")
    issued, expires = timestamp(index["issued_at"]), timestamp(index["expires_at"])
    now = now or datetime.now(timezone.utc)
    if issued > now + timedelta(minutes=5) or expires <= issued or (
        expires - issued > timedelta(days=settings["validity_days"])
    ) or not allow_expired and expires <= now:
        raise ValueError("App Store metadata is expired or has invalid freshness")
    packages, owners, latest = validate_packages(index["packages"])
    identities = set()
    for record in index["apps"]:
        if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
            raise ValueError("Invalid App Store record")
        identity = record["app_id"], record["architecture"]
        if not app_id(identity[0]) or (
            identity[1] not in ("all", "amd64", "arm64") or identity in identities
        ):
            raise ValueError("Duplicate or invalid App Store identity")
        identities.add(identity)
        version(record["release_version"])
        if not isinstance(record["app_version"], str) or not record["app_version"]:
            raise ValueError("App Store records must bind their authenticated App version")
        artifact = record["artifact"]
        if not isinstance(artifact, dict) or set(artifact) != {"file", "size", "sha256", "media_type"} or (
            type(artifact["size"]) is not int or not 0 < artifact["size"] <= snapshots.MAX_BYTES
            or artifact["media_type"] != "application/gzip"
        ):
            raise ValueError("Invalid App Store artifact")
        checksum = snapshots.sha256_value(artifact["sha256"])
        if artifact["file"] != f"claw-app-snapshot-{checksum}.tar.gz":
            raise ValueError("App Store downloads must be immutable SHA256-named snapshots")
        display, web = record["display"], record["web_ui"]
        if not isinstance(display, dict) or set(display) != {
            "name", "description", "source_kind", "source_name",
        } or display["source_kind"] not in ("product", "capability") or (
            not isinstance(display["source_name"], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]*", display["source_name"])
            or not isinstance(display["name"], str) or not 0 < len(display["name"]) <= 256
            or not isinstance(display["description"], str) or len(display["description"]) > 4096
        ):
            raise ValueError("Invalid App Store presentation metadata")
        if record["release_tag"] != record_tag(record):
            raise ValueError("App Store artifact must belong to its owning source's official release")
        if not isinstance(web, dict) or set(web) != {"path", "sha256", "entry"} or (
            web["path"] != DESCRIPTOR or web["entry"] != "web/index.html"
        ):
            raise ValueError("App Store entries require signed, package-local product Web interfaces")
        snapshots.sha256_value(web["sha256"])
        manifest, provenance = record["manifest"], record["provenance"]
        if not isinstance(manifest, dict) or set(manifest) != {"path", "size", "sha256"} or (
            manifest["path"] != "app.json" or type(manifest["size"]) is not int
            or not 0 < manifest["size"] <= snapshots.MAX_METADATA
        ):
            raise ValueError("Invalid App Store manifest binding")
        snapshots.sha256_value(manifest["sha256"])
        if not isinstance(provenance, dict) or set(provenance) != {
            "path", "sha256", "content_digest", "publisher_key_id",
        } or provenance["path"] != ".provenance.json":
            raise ValueError("Invalid App Store package provenance")
        snapshots.sha256_value(provenance["sha256"])
        snapshots.sha256_value(provenance["content_digest"], prefixed=True)
        snapshots.sha256_value(provenance["publisher_key_id"], prefixed=True)
        delivery = record["delivery"]
        if not isinstance(delivery, dict) or set(delivery) != {"kind", "package_sha256"} or (
            delivery["kind"] != "apt"
        ):
            raise ValueError("Official App Store delivery must be an exact APT package binding")
        checksum = snapshots.sha256_value(delivery["package_sha256"])
        package = packages.get(checksum)
        if package is None or package["architecture"] != record["architecture"] or (
            record["app_id"] not in package["apps"] or package["version"] != record["release_version"]
        ):
            raise ValueError("App Store delivery has no matching containing Debian package")
        if latest[package["package"], package["architecture"]]["sha256"] != checksum:
            raise ValueError("App Store cannot downgrade or split an installed package's App bundle")
    if identities != set(owners):
        raise ValueError("App Store package inventory contains Apps without catalog records")
    return index


def verified_index(directory, signing, *, now=None, allow_expired=False):
    directory = work_path(Path(directory))
    if {path.name for path in directory.iterdir()} != {INDEX, SIGNATURE}:
        raise ValueError("App Store metadata directory contains unindexed files")
    for name in (INDEX, SIGNATURE):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > snapshots.MAX_METADATA:
            raise ValueError("App Store metadata must be bounded regular files")
    signing.verify(directory / SIGNATURE, directory / INDEX)
    return validate_index(snapshots.read_metadata(directory / INDEX), now=now, allow_expired=allow_expired)


def label(value, default):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("en", value[sorted(value)[0]] if value else default)
    return default


def snapshot_records(directory, provenance, signing, *, inventories=None):
    directory = work_path(Path(directory))
    catalog = snapshots.verify_catalog(directory, provenance, signing)
    result = []
    with tempfile.TemporaryDirectory(prefix=".store-inspect-", dir=directory.parent) as temporary:
        for index, record in enumerate(catalog["apps"]):
            root = Path(temporary) / str(index)
            snapshots.extract_archive(directory / record["artifact"]["file"], root)
            manifest = snapshots.read_metadata(root / "app.json")
            descriptor = read_descriptor(root, manifest)
            if descriptor is None:
                raise ValueError(f"Released App {record['app_id']} has no product-owned Web interface")
            published = {
                **record, "release_version": catalog["release_version"],
                "display": {
                    "name": label(descriptor["title"], record["app_id"]),
                    "description": label(descriptor["description"], ""),
                    "source_kind": descriptor["source_kind"], "source_name": descriptor["source_name"],
                },
                "web_ui": {"path": DESCRIPTOR, "sha256": digest(root / DESCRIPTOR),
                           "entry": descriptor["entry"]},
            }
            published["release_tag"] = record_tag(published)
            if inventories is not None:
                identity = record["app_id"], record["architecture"]
                if identity in inventories:
                    raise ValueError("Repeated App snapshot identity in Store inputs")
                inventories[identity] = snapshots.tree_inventory(root, record["architecture"])
            result.append(published)
    return result


def debian_apps(root, record):
    base = root / "usr/lib/cos/apps"
    apps = {}
    for path in sorted(base.rglob("app.json")):
        manifest = snapshots.read_metadata(path)
        value = manifest.get("id")
        if not app_id(value) or value != "-".join(path.parent.relative_to(base).parts) or value in apps:
            raise ValueError("Debian App identity conflicts with its installed layout")
        snapshots.tree_inventory(path.parent, record["architecture"])
        apps[value] = path.parent
    declared = record["control"].get("X-Claw-App-Ids", "")
    selected = declared.split(", ") if declared else []
    if any(not app_id(value) for value in selected) or len(set(selected)) != len(selected) or (
        set(selected) != set(apps)
    ):
        raise ValueError("Debian control App IDs differ from the actual containing payload")
    return apps


def package_binding(record, apps):
    return {**{field: record[field] for field in PACKAGE_FIELDS - {"apps"}}, "apps": sorted(apps)}


def compose(directories, output, provenance, signing, *, packages, previous=None, now=None):
    output = work_path(Path(output))
    if output.exists() or not packages:
        raise ValueError("Select final Debian payloads and a new App Store output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    prior = verified_index(previous, signing, now=now, allow_expired=True) if previous else None
    records = {(item["app_id"], item["architecture"]): item for item in prior["apps"]} if prior else {}
    retained = {identity(item): item for item in prior["packages"]} if prior else {}
    additions, inventories = {}, {}
    for directory in directories:
        for record in snapshot_records(directory, provenance, signing, inventories=inventories):
            additions[record["app_id"], record["architecture"]] = record
    tuples, bound = set(), set()
    with tempfile.TemporaryDirectory(prefix=".store-packages-", dir=output.parent) as scratch:
        for index, package in enumerate(packages):
            record = package_record(Path(package))
            key = identity(record)
            if key in tuples:
                raise ValueError("Repeated Debian package tuple in App Store input")
            tuples.add(key)
            root = Path(scratch) / str(index)
            run(["dpkg-deb", "--extract", package, root])
            apps = debian_apps(root, record)
            candidate = package_binding(record, apps)
            if key in retained and retained[key] != candidate:
                raise ValueError("Immutable App Store package tuple collision")
            if any(item["package"] == record["package"] and
                   compare_versions(item["version"], "gt", record["version"])
                   for item in retained.values()):
                raise ValueError("App Store cannot downgrade Debian packages")
            retained[key] = candidate
            for value, app_root in apps.items():
                app_key = value, record["architecture"]
                selected = additions.get(app_key)
                if selected is None or app_key in bound:
                    raise ValueError("Debian App has no unique authenticated snapshot binding")
                binding = snapshots.verified_binding(app_root, provenance)
                if any(selected[field] != expected for field, expected in binding.items()) or (
                    selected["release_version"] != record["version"]
                    or inventories[app_key] != snapshots.tree_inventory(app_root, record["architecture"])
                ):
                    raise ValueError("Snapshot bytes differ from the final authenticated Debian App")
                display = selected["display"]
                if record["control"].get("X-Claw-Product") != display["source_name"] or (
                    record["control"].get("X-Claw-Source-Kind") != display["source_kind"]
                ):
                    raise ValueError("App snapshot and Debian package source ownership disagree")
                selected["delivery"] = {"kind": "apt", "package_sha256": record["sha256"]}
                bound.add(app_key)
            if Path(package).stat().st_size != record["size"] or digest(Path(package)) != record["sha256"]:
                raise ValueError("Debian package changed during App Store inspection")
            shutil.rmtree(root)
    if bound != set(additions):
        raise ValueError("App snapshot has no containing final Debian package")
    for app_key, record in additions.items():
        existing = records.get(app_key)
        if existing and (
            compare_versions(record["release_version"], "lt", existing["release_version"]) or (
                compare_versions(record["release_version"], "eq", existing["release_version"])
                and record != existing
            )
        ):
            raise ValueError("App Store cannot downgrade or replace immutable release bytes")
        records[app_key] = record
    generation = max(int(now.timestamp()), int(prior["generation"]) + 1 if prior else 1)
    index = {
        "schema": SCHEMA, "repository": config()["repository"], "runtime_abi": 1,
        "generation": str(generation), "issued_at": utc(now),
        "expires_at": utc(now + timedelta(days=config()["validity_days"])),
        "apps": sorted(records.values(), key=lambda item: (item["app_id"], item["architecture"])),
        "packages": sorted(retained.values(), key=identity),
    }
    validate_index(index, now=now)
    output.mkdir(parents=True)
    write_json(output / INDEX, index)
    signing.sign(output / INDEX, output / SIGNATURE, armored=True)
    verified_index(output, signing, now=now)
    return index


def refresh(directory, signing, *, now=None):
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    index = verified_index(directory, signing, now=now, allow_expired=True)
    index.update(
        generation=str(max(int(now.timestamp()), int(index["generation"]) + 1)),
        issued_at=utc(now), expires_at=utc(now + timedelta(days=config()["validity_days"])),
    )
    write_json(Path(directory) / INDEX, index)
    signing.sign(Path(directory) / INDEX, Path(directory) / SIGNATURE, armored=True)
    return verified_index(directory, signing, now=now)


def payload_inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        mode = stat.S_IMODE(path.lstat().st_mode)
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = ("symlink", mode, os.readlink(path))
        elif path.is_dir():
            result[name] = ("directory", mode)
        elif path.is_file():
            result[name] = ("file", mode, path.stat().st_size, digest(path))
        else:
            raise ValueError(f"Unexpected Debian payload node: {name}")
    return result


def prepare_release_snapshots(plan, packages, output, provenance, signing, key):
    """Return final signed .debs and snapshots derived only from those .deb bytes."""
    output = work_path(Path(output))
    if output.exists():
        raise ValueError("Authenticated release output must be a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = {(entry["package"], entry["architecture"]): entry for entry in plan["packages"]}
    originals = [package_record(Path(package)) for package in packages]
    if len(expected) != len(plan["packages"]) or len(originals) != len(expected) or {
        (record["package"], record["architecture"]) for record in originals
    } != set(expected) or any(record["version"] != plan["version"] for record in originals):
        raise ValueError("Authenticated release must cover the exact tested Debian plan")
    groups, final_records = {}, []
    with tempfile.TemporaryDirectory(prefix=".store-release-", dir=output.parent) as scratch:
        scratch = Path(scratch)
        prepared = scratch / "prepared"
        final_packages = prepared / "packages"
        final_packages.mkdir(parents=True)
        for index, (package, record) in enumerate(zip(packages, originals, strict=True)):
            entry = expected[(record["package"], record["architecture"])]
            root = scratch / f"stage-{index}"
            run(["dpkg-deb", "--raw-extract", package, root])
            validate_install_tree(root)
            apps = debian_apps(root, record)
            if len(set(entry["apps"])) != len(entry["apps"]) or set(apps) != set(entry["apps"]):
                raise ValueError("App Store input differs from the tested Debian App selection")
            before = payload_inventory(root)
            envelopes = {
                (path / ".provenance.json").relative_to(root).as_posix() for path in apps.values()
            }
            for path in apps.values():
                if provenance is None or key is None:
                    raise ValueError("App release requires the pinned public provenance signer and signing key")
                manifest = snapshots.read_metadata(path / "app.json")
                provenance.check_binary()
                arguments = [
                    provenance.binary, "provenance", "sign", "--kind", "app",
                    "--id", manifest["id"], "--version", manifest["version"],
                    "--path", path, "--key", key,
                ]
                for _, selected in snapshots.manifest_entries(manifest):
                    arguments.extend(("--entrypoint", selected))
                arguments.extend(("--resource", DESCRIPTOR, "--resource", "web/index.html"))
                snapshots.run(arguments)
                snapshots.verified_binding(path, provenance)
            validate_install_tree(root)
            after = payload_inventory(root)
            if {name: value for name, value in before.items() if name not in envelopes} != {
                name: value for name, value in after.items() if name not in envelopes
            }:
                raise ValueError("Public App signer changed payload bytes other than provenance")
            final = final_packages / Path(package).name
            if apps:
                sums = root / "DEBIAN/md5sums"
                if sums.exists():
                    mode = stat.S_IMODE(sums.stat().st_mode)
                    sums.unlink()
                    sums.write_text("".join(
                        f"{digest(path, 'md5')}  {path.relative_to(root).as_posix()}\n"
                        for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()
                        and not path.is_relative_to(root / "DEBIAN")
                    ))
                    sums.chmod(mode)
                run(["dpkg-deb", "--root-owner-group", "--uniform-compression", "--threads-max=1",
                     "-Zxz", "-z9", "--build", root, final],
                    env={"SOURCE_DATE_EPOCH": str(plan["source_date_epoch"])})
            else:
                shutil.copy2(package, final)
            authenticated = package_record(final)
            if authenticated["control"] != record["control"]:
                raise ValueError("Authenticated Debian package control metadata differs from its build input")
            final_root = scratch / f"final-{index}"
            run(["dpkg-deb", "--raw-extract", final, final_root])
            validate_install_tree(final_root)
            if payload_inventory(final_root) != payload_inventory(root):
                raise ValueError("Final Debian payload lost bytes, modes, links or control metadata")
            final_apps = debian_apps(final_root, authenticated)
            for path in final_apps.values():
                snapshots.verified_binding(path, provenance)
            if Path(package).stat().st_size != record["size"] or digest(Path(package)) != record["sha256"]:
                raise ValueError("Original Debian build input changed during release authentication")
            final_records.append(authenticated)
            if final_apps:
                relative = Path(entry["selection"].replace(":", "-")) / entry["architecture"]
                directory = prepared / relative
                snapshots.build_catalog(
                    list(final_apps.values()), directory,
                    release_version=plan["version"], architecture=entry["architecture"],
                    provenance=provenance, signing=signing,
                )
                groups.setdefault(entry["selection"], []).append(output / relative)
            shutil.rmtree(root)
            shutil.rmtree(final_root)
        write_json(prepared / "release-record.json", {
            "format": "claw.app-authenticated-release/v1", "plan": plan,
            "build_packages": sorted(originals, key=identity),
            "packages": sorted(final_records, key=identity),
        })
        prepared.rename(output)
    return [output / "packages" / Path(package).name for package in packages], groups


def release_files(directories, target):
    records = []
    for directory in directories:
        catalog = snapshots.read_metadata(directory / "catalog.json")
        architecture = catalog["apps"][0]["architecture"]
        for name in ("catalog.json", "catalog.json.asc"):
            source = directory / name
            shutil.copy2(source, target / name.replace("catalog", f"app-catalog-{architecture}"))
        for record in catalog["apps"]:
            source = directory / record["artifact"]["file"]
            destination = target / source.name
            if destination.exists() and digest(destination) != record["artifact"]["sha256"]:
                raise ValueError("Immutable App snapshot asset collision")
            if not destination.exists():
                shutil.copy2(source, destination)
            records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--snapshot-directory", type=Path, action="append", default=[])
    parser.add_argument("--package", type=Path, action="append", default=[],
                        help="Final authenticated Debian payload; repeat for every selected package")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--cos", type=Path)
    parser.add_argument("--cos-sha256")
    parser.add_argument("--publisher-key-id")
    options = parser.parse_args()
    workspace = work_path(options.output).parent / ".store-signing"
    with Signing(workspace) as signing:
        if options.action == "verify":
            result = verified_index(options.output, signing)
        else:
            if not all((options.cos, options.cos_sha256, options.publisher_key_id)):
                parser.error("build requires the existing public provenance CLI and its exact pins")
            provenance = snapshots.Provenance(
                options.cos, options.cos_sha256, options.publisher_key_id,
            )
            signing.import_environment()
            result = compose(
                options.snapshot_directory, options.output, provenance, signing,
                packages=options.package, previous=options.previous,
            )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
