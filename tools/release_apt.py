"""Create or refresh the signed App APT repository without discarding prior releases."""

import argparse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
import gzip
import json
import lzma
from pathlib import Path
import re
import shutil

from release_common import (
    ROOT, compare_versions, control_bytes, digest, fields, identity, package_record,
    relative_path, work_path, write_json,
)
from release_signing import Signing

INDEX = b"<!doctype html><title>Claw OS Applications</title><h1>Claw OS Applications APT</h1>\n"


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def hash_record(path):
    return {"size": path.stat().st_size, "sha256": digest(path), "sha512": digest(path, "sha512")}


def check_hash(root, name, expected):
    path = root / relative_path(name)
    if path.is_symlink() or not path.is_file() or hash_record(path) != {
        key: expected[key] for key in ("size", "sha256", "sha512")
    }:
        raise ValueError(f"Repository content digest mismatch: {name}")
    return path


def package_index(records, architecture):
    paragraphs = []
    for record in sorted(records, key=identity):
        if record["architecture"] not in ("all", architecture):
            continue
        preferred = ["Package", "Version", "Architecture"]
        control = record["control"]
        ordered = {name: control[name] for name in [
            *preferred, *sorted(set(control) - set(preferred)),
        ]}
        paragraphs.append(control_bytes({
            **ordered, "Filename": record["filename"], "Size": str(record["size"]),
            "SHA256": record["sha256"], "SHA512": record["sha512"],
        }))
    return b"\n".join(paragraphs) + (b"\n" if paragraphs else b"")


def release_hashes(release, algorithm):
    result = {}
    for line in release[algorithm].splitlines():
        if not line.strip():
            continue
        parts = line.split()
        length = 64 if algorithm == "SHA256" else 128
        if len(parts) != 3 or not re.fullmatch(f"[0-9a-f]{{{length}}}", parts[0]) or not parts[1].isdigit():
            raise ValueError("Malformed signed Release digest index")
        checksum, size, path = parts
        relative_path(path)
        if path in result:
            raise ValueError("Duplicate signed Release digest path")
        result[path] = (int(size), checksum)
    return result


def verify_repository(root, signing, *, now=None):
    root = Path(root).resolve()
    settings = signing.settings
    dist = root / "dists" / settings["suite"]
    current = now or now_utc()
    for path in root.rglob("*"):
        if path.relative_to(root).parts[0] == ".git":
            continue
        if path.is_symlink():
            raise ValueError("Repository snapshots cannot contain symlinks")
    signed = signing.verify_clear(dist / "InRelease")
    if signed != (dist / "Release").read_bytes():
        raise ValueError("InRelease and Release disagree")
    signing.verify(dist / "Release.gpg", dist / "Release")
    release = fields(signed.decode().strip())
    for key, expected in {
        "Origin": "Claw OS Applications", "Label": "Claw OS Applications",
        "Suite": settings["suite"], "Codename": settings["suite"],
        "Architectures": " ".join(settings["architectures"]),
        "Components": settings["component"], "Acquire-By-Hash": "yes",
    }.items():
        if release.get(key) != expected:
            raise ValueError(f"Unexpected signed repository identity: {key}")
    created = parsedate_to_datetime(release["Date"])
    expires = parsedate_to_datetime(release["Valid-Until"])
    if created.tzinfo is None or expires.tzinfo is None or not (
        created <= current + timedelta(minutes=5) and current < expires and created < expires
        and expires - created <= timedelta(days=settings["validity_days"])
    ):
        raise ValueError("APT metadata is stale, future-dated or has unbounded validity")
    sha256, sha512 = release_hashes(release, "SHA256"), release_hashes(release, "SHA512")
    expected_indexes = {"catalog.json"} | {
        f"{settings['component']}/binary-{architecture}/Packages{suffix}"
        for architecture in settings["architectures"] for suffix in ("", ".gz", ".xz")
    }
    if set(sha256) != expected_indexes or set(sha512) != expected_indexes:
        raise ValueError("Signed Release is missing required indexes")
    for name in expected_indexes:
        if sha256[name][0] != sha512[name][0]:
            raise ValueError("Signed index sizes disagree")
        check_hash(dist, name, {"size": sha256[name][0], "sha256": sha256[name][1], "sha512": sha512[name][1]})
    catalog = json.loads((dist / "catalog.json").read_text())
    if catalog.get("format") != "claw.app-apt/v1" or catalog.get("repository") != settings["repository"]:
        raise ValueError("Unexpected signed package catalog")
    records = catalog["packages"]
    if not isinstance(records, list) or len({identity(record) for record in records}) != len(records):
        raise ValueError("Duplicate or invalid catalog packages")
    for record in records:
        path = check_hash(root, record["filename"], record)
        if package_record(path) != record:
            raise ValueError("Signed catalog does not describe the real Debian package")
    for name, expected in catalog["indexes"].items():
        match = re.fullmatch(
            rf"{re.escape(settings['component'])}/binary-(?:amd64|arm64)/by-hash/(SHA256|SHA512)/([0-9a-f]+)",
            name,
        )
        if not match or match[2] != expected[match[1].lower()]:
            raise ValueError("Invalid retained by-hash index")
        check_hash(dist, name, expected)
    for architecture in settings["architectures"]:
        directory = dist / settings["component"] / f"binary-{architecture}"
        packages = directory / "Packages"
        if packages.read_bytes() != package_index(records, architecture):
            raise ValueError("APT Packages differs from its signed catalog")
        if gzip.decompress((directory / "Packages.gz").read_bytes()) != packages.read_bytes() or (
            lzma.decompress((directory / "Packages.xz").read_bytes()) != packages.read_bytes()
        ):
            raise ValueError("Compressed APT indexes disagree")
        for suffix in ("", ".gz", ".xz"):
            path = directory / f"Packages{suffix}"
            for algorithm in ("SHA256", "SHA512"):
                hashed = path.parent / "by-hash" / algorithm / digest(path, algorithm.lower())
                name = hashed.relative_to(dist).as_posix()
                if name not in catalog["indexes"] or hashed.read_bytes() != path.read_bytes():
                    raise ValueError("Current by-hash index is missing")
    if (root / "archive-key.asc").read_bytes() != signing.public_key.read_bytes() or (
        root / "index.html"
    ).read_bytes() != INDEX or (root / ".nojekyll").read_bytes() != b"":
        raise ValueError("Unexpected repository bootstrap assets")
    prefix = f"dists/{settings['suite']}/"
    allowed = {
        ".nojekyll", "index.html", "archive-key.asc",
        *(prefix + name for name in ("Release", "Release.gpg", "InRelease")),
        *(prefix + name for name in expected_indexes),
        *(prefix + name for name in catalog["indexes"]),
        *(record["filename"] for record in records),
    }
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).parts[0] != ".git"
    }
    if actual != allowed:
        raise ValueError("Unindexed files in authenticated repository snapshot")
    return catalog


def compose(packages, output, signing, *, previous=None, initialize=False, now=None):
    output = work_path(Path(output))
    settings = signing.settings
    current = now or now_utc()
    if previous is None:
        if not initialize:
            raise ValueError("Initial publication requires explicit, verified initialization")
        old = {"packages": [], "indexes": {}}
    else:
        if initialize:
            raise ValueError("Cannot initialize over a previous repository")
        old = verify_repository(previous, signing, now=current)
    if output.exists():
        raise ValueError("Refusing to overwrite a repository output directory")
    additions = [package_record(Path(path)) for path in packages]
    if len({identity(record) for record in additions}) != len(additions):
        raise ValueError("Repeated package identity in publication input")
    existing = {identity(record): record for record in old["packages"]}
    for record in additions:
        key = identity(record)
        if key in existing and existing[key] != record:
            raise ValueError(f"Immutable package version collision: {record['package']}")
        for prior in existing.values():
            if prior["package"] == record["package"] and (
                compare_versions(prior["version"], "gt", record["version"])
            ):
                raise ValueError(f"Package version regression: {record['package']}")
        existing[key] = record
    if previous:
        shutil.copytree(previous, output, ignore=shutil.ignore_patterns(".git"))
    else:
        output.mkdir(parents=True)
    for path, record in zip(packages, additions):
        destination = output / record["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(path, destination)
    records = sorted(existing.values(), key=identity)
    indexes = dict(old["indexes"])
    dist = output / "dists" / settings["suite"]
    dist.mkdir(parents=True, exist_ok=True)
    release_paths = []
    for architecture in settings["architectures"]:
        directory = dist / settings["component"] / f"binary-{architecture}"
        directory.mkdir(parents=True, exist_ok=True)
        data = package_index(records, architecture)
        for suffix, payload in (("", data), (".gz", gzip.compress(data, mtime=0)),
                                (".xz", lzma.compress(data))):
            path = directory / f"Packages{suffix}"
            path.write_bytes(payload)
            release_paths.append(path)
            expected = hash_record(path)
            for algorithm in ("SHA256", "SHA512"):
                hashed = directory / "by-hash" / algorithm / expected[algorithm.lower()]
                hashed.parent.mkdir(parents=True, exist_ok=True)
                if hashed.exists() and hashed.read_bytes() != payload:
                    raise ValueError("Immutable by-hash index collision")
                hashed.write_bytes(payload)
                indexes[hashed.relative_to(dist).as_posix()] = expected
    write_json(dist / "catalog.json", {
        "format": "claw.app-apt/v1", "repository": settings["repository"],
        "packages": records, "indexes": indexes,
    })
    release_paths.append(dist / "catalog.json")
    release = {
        "Origin": "Claw OS Applications", "Label": "Claw OS Applications",
        "Suite": settings["suite"], "Codename": settings["suite"],
        "Date": format_datetime(current, usegmt=True),
        "Valid-Until": format_datetime(current + timedelta(days=settings["validity_days"]), usegmt=True),
        "Architectures": " ".join(settings["architectures"]), "Components": settings["component"],
        "Acquire-By-Hash": "yes", "Description": "Independently released Claw OS applications",
    }
    for algorithm in ("SHA256", "SHA512"):
        release[algorithm] = "".join(
            f"\n {digest(path, algorithm.lower())} {path.stat().st_size} {path.relative_to(dist).as_posix()}"
            for path in sorted(release_paths)
        )
    (dist / "Release").write_bytes(control_bytes(release))
    signing.sign(dist / "Release", dist / "InRelease", clear=True)
    signing.sign(dist / "Release", dist / "Release.gpg", armored=True)
    shutil.copy2(signing.public_key, output / "archive-key.asc")
    (output / ".nojekyll").write_bytes(b"")
    (output / "index.html").write_bytes(INDEX)
    verify_repository(output, signing, now=current)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verification = commands.add_parser("verify")
    verification.add_argument("--repository", type=Path, required=True)
    assembly = commands.add_parser("compose")
    assembly.add_argument("--packages", type=Path, nargs="*", default=[])
    assembly.add_argument("--previous", type=Path)
    assembly.add_argument("--initialize", action="store_true")
    assembly.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    with Signing(ROOT / "build/apt-signing") as signing:
        if options.command == "verify":
            verify_repository(options.repository, signing)
        else:
            signing.import_environment()
            compose(options.packages, options.output, signing, previous=options.previous,
                    initialize=options.initialize)


if __name__ == "__main__":
    main()
