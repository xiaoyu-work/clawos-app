"""Build the signed official Web App Store from authenticated App snapshots."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile

from release_common import compare_versions, config, digest, version, work_path, write_json
from release_signing import Signing
import release_snapshots as snapshots
from web_ui import DESCRIPTOR, read_descriptor


SCHEMA = "claw.app-store/v1"
INDEX = "index.json"
SIGNATURE = "index.json.asc"
RECORD_FIELDS = {
    "app_id", "app_version", "architecture", "artifact", "manifest", "provenance",
    "release_version", "release_tag", "display", "web_ui",
}


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
        "schema", "repository", "runtime_abi", "generation", "issued_at", "expires_at", "apps",
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
    identities = set()
    for record in index["apps"]:
        if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
            raise ValueError("Invalid App Store record")
        identity = record["app_id"], record["architecture"]
        if not isinstance(identity[0], str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", identity[0]) or (
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


def snapshot_records(directory, provenance, signing):
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
            result.append(published)
    return result


def compose(directories, output, provenance, signing, *, previous=None, now=None):
    output = work_path(Path(output))
    if output.exists() or not directories:
        raise ValueError("Select authenticated App snapshots and a new App Store output directory")
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    prior = verified_index(previous, signing, now=now, allow_expired=True) if previous else None
    records = {(item["app_id"], item["architecture"]): item for item in prior["apps"]} if prior else {}
    for directory in directories:
        for record in snapshot_records(directory, provenance, signing):
            identity = record["app_id"], record["architecture"]
            existing = records.get(identity)
            if existing:
                if compare_versions(record["release_version"], "lt", existing["release_version"]) or (
                    compare_versions(record["release_version"], "eq", existing["release_version"])
                    and record != existing
                ):
                    raise ValueError("App Store cannot downgrade or replace immutable release bytes")
            records[identity] = record
    generation = max(int(now.timestamp()), int(prior["generation"]) + 1 if prior else 1)
    index = {
        "schema": SCHEMA, "repository": config()["repository"], "runtime_abi": 1,
        "generation": str(generation), "issued_at": utc(now),
        "expires_at": utc(now + timedelta(days=config()["validity_days"])),
        "apps": sorted(records.values(), key=lambda item: (item["app_id"], item["architecture"])),
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


def prepare_release_snapshots(plan, packages, output, provenance, signing, key):
    """Use the public signer on the exact already-validated Debian App payloads."""
    output = work_path(Path(output))
    output.mkdir(parents=True, exist_ok=False)
    expected = {(entry["package"], entry["architecture"]): entry for entry in plan["packages"]}
    groups = {}
    with tempfile.TemporaryDirectory(prefix=".store-release-", dir=output.parent) as scratch:
        for index, package in enumerate(packages):
            from release_common import package_record, run
            record = package_record(package)
            entry = expected[(record["package"], record["architecture"])]
            if not entry["apps"]:
                continue
            root = Path(scratch) / str(index)
            root.mkdir()
            run(["dpkg-deb", "--extract", package, root])
            directories = sorted((root / "usr/lib/cos/apps").rglob("app.json"))
            manifests = [snapshots.read_metadata(path) for path in directories]
            if {manifest["id"] for manifest in manifests} != set(entry["apps"]):
                raise ValueError("App Store input differs from the tested Debian App selection")
            for path, manifest in zip(directories, manifests, strict=True):
                provenance.check_binary()
                arguments = [
                    provenance.binary, "provenance", "sign", "--kind", "app",
                    "--id", manifest["id"], "--version", manifest["version"],
                    "--path", path.parent, "--key", key,
                ]
                for _, selected in snapshots.manifest_entries(manifest):
                    arguments.extend(("--entrypoint", selected))
                arguments.extend(("--resource", DESCRIPTOR, "--resource", "web/index.html"))
                snapshots.run(arguments)
                provenance.verify(path.parent)
            directory = output / entry["selection"].replace(":", "-") / entry["architecture"]
            snapshots.build_catalog(
                [path.parent for path in directories], directory,
                release_version=plan["version"], architecture=entry["architecture"],
                provenance=provenance, signing=signing,
            )
            groups.setdefault(entry["selection"], []).append(directory)
    return groups


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
                previous=options.previous,
            )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
