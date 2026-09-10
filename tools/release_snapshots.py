"""Package authenticated App directories without installing or activating them."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from release_common import digest, run, version, work_path, write_json
from release_development import tar_entry
from release_payload import MAX_BYTES, MAX_ENTRIES
from release_signing import Signing

SCHEMA = "claw.app-snapshot-catalog/v1"
MAX_METADATA = 8 * 1024 * 1024
CATALOG_FILES = {"catalog.json", "catalog.json.asc", "SHA256SUMS", "SHA256SUMS.asc"}
ROOT_HOOKS = {"preinst", "postinst", "prerm", "postrm"}
RUNTIME_ENTRIES = {
    "python": ("main.py", "server.py"),
    "node": ("main.js", "server.js"),
    "shell": ("main.sh", "server.sh"),
    "binary": ("main", "server"),
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Non-finite JSON number is not part of the App contract: {value}")


def read_metadata_snapshot(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA:
        raise ValueError(f"Expected bounded regular metadata: {path.name}")
    with path.open("rb") as stream:
        data = stream.read(MAX_METADATA + 1)
    if len(data) > MAX_METADATA:
        raise ValueError(f"Expected bounded regular metadata: {path.name}")
    value = json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return data, value


def read_metadata(path):
    return read_metadata_snapshot(path)[1]


def sha256_value(value, *, prefixed=False):
    if not isinstance(value, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}" if prefixed else r"[0-9a-f]{64}", value,
    ):
        raise ValueError("Expected an explicit SHA256 pin")
    return value


def app_path(value):
    if not isinstance(value, str):
        raise ValueError("App payload paths must be strings")
    path = PurePosixPath(value)
    if value in ("", ".", "..") or path.is_absolute() or str(path) != value or "\\" in value or (
        len(value) > 4096 or len(path.parts) > 64
        or any(part in (".", "..") or part.endswith((".", " ")) for part in path.parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"Unsafe App-relative path: {value!r}")
    if any(part in ("DEBIAN", ".git") for part in path.parts) or (
        len(path.parts) == 1 and value in ROOT_HOOKS
    ):
        raise ValueError(f"App snapshots cannot supply package-manager/root hooks: {value}")
    return path


def tree_inventory(root, architecture):
    if architecture not in ("all", "amd64", "arm64"):
        raise ValueError("Unsupported App snapshot architecture")
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o7022:
        raise ValueError("App snapshot root must not be a symlink or group/world-writable directory")
    records, folded = {}, set()
    total = 0
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        app_path(name)
        if name.casefold() in folded or len(records) >= MAX_ENTRIES:
            raise ValueError("Duplicate, case-colliding or excessive App payload paths")
        folded.add(name.casefold())
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o7000 or (not stat.S_ISLNK(info.st_mode) and mode & 0o022):
            raise ValueError(f"Unsafe App payload mode: {name}")
        if os.listxattr(path, follow_symlinks=False):
            raise ValueError(f"App snapshots cannot carry unauthenticated extended attributes: {name}")
        if stat.S_ISDIR(info.st_mode):
            record = {"type": "directory", "mode": mode}
        elif stat.S_ISLNK(info.st_mode):
            raise ValueError(f"claw.provenance/v1 cannot sign symlinks; prepare explicit owned files: {name}")
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise ValueError(f"App snapshots cannot use hardlinked files: {name}")
            total += info.st_size
            if total > MAX_BYTES:
                raise ValueError("App snapshot exceeds its expanded-size limit")
            with path.open("rb") as stream:
                header = stream.read(20)
                if header.startswith(b"\x7fELF") and (
                    len(header) < 20 or header[4:7] != b"\x02\x01\x01"
                    or int.from_bytes(header[18:20], "little") != {"amd64": 62, "arm64": 183}.get(architecture)
                ):
                    raise ValueError(f"ELF payload does not match snapshot architecture {architecture}: {name}")
                stream.seek(0)
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            record = {"type": "file", "mode": mode, "size": info.st_size, "sha256": checksum}
        else:
            raise ValueError(f"App snapshot contains a special file: {name}")
        records[name] = record
    return records


class Provenance:
    """Use the existing public verifier, including its ordinary trust roots."""

    def __init__(self, binary, binary_sha256, publisher_key_id):
        self.binary = Path(binary).resolve(strict=True)
        self.binary_sha256 = sha256_value(binary_sha256)
        self.publisher_key_id = sha256_value(publisher_key_id, prefixed=True)
        self.check_binary()

    def check_binary(self):
        if not self.binary.is_file() or not os.access(self.binary, os.X_OK) or (
            digest(self.binary) != self.binary_sha256
        ):
            raise ValueError("Public provenance CLI does not match its executable SHA256 pin")

    def verify(self, root):
        self.check_binary()
        result = run([self.binary, "provenance", "verify", "--kind", "app", "--path", root], check=False)
        if len(result.stdout) > MAX_METADATA or len(result.stderr) > MAX_METADATA:
            raise ValueError("Public provenance verifier returned excessive output")
        try:
            value = json.loads(result.stdout, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("Public provenance verifier did not return valid JSON") from error
        if result.returncode or not isinstance(value, dict) or value.get("verified") is not True:
            detail = value.get("error", "verification failed") if isinstance(value, dict) else "verification failed"
            raise ValueError(f"Public provenance verification failed: {detail}")
        package = value.get("package")
        if not isinstance(package, dict) or package.get("kind") != "app" or (
            package.get("trust") != "publisher" or package.get("publisher_key_id") != self.publisher_key_id
        ):
            raise ValueError("App snapshot requires its pinned package-signing publisher, not development trust")
        return value


def manifest_entries(manifest):
    runtime = manifest.get("runtime", "python")
    if not isinstance(runtime, str) or runtime not in RUNTIME_ENTRIES:
        raise ValueError("App entry binding requires a supported manifest runtime")
    operations = manifest.get("operations", {})
    if not isinstance(operations, dict):
        raise ValueError("App operations must be an object")
    if "desktop" in manifest and not isinstance(manifest["desktop"], dict):
        raise ValueError("App desktop surface must be an object")
    main, server = RUNTIME_ENTRIES[runtime]
    entries = []
    if "entry" in manifest or operations or "desktop" in manifest or "mcp" not in manifest:
        entries.append(("operation/GUI", manifest.get("entry", main)))
    if "mcp" in manifest:
        mcp = manifest["mcp"]
        if not isinstance(mcp, dict):
            raise ValueError("App MCP surface must be an object")
        if mcp.get("lifecycle", "lazy") not in ("lazy", "always-on", "while-app-running"):
            raise ValueError("App MCP lifecycle must use the public service contract")
        entries.append(("MCP/background", mcp.get("entry", server)))
    for _, entry in entries:
        app_path(entry)
    return entries


def validate_manifest_entries(root, manifest, entries):
    for surface, entry in manifest_entries(manifest):
        if entry not in entries:
            raise ValueError(f"App {surface} entry is not a declared signed package-local entrypoint: {entry}")
        path = root / entry
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f"App {surface} entry must be a regular package-owned file: {entry}")
        if manifest.get("runtime", "python") == "binary" and not path.stat().st_mode & 0o111:
            raise ValueError(f"App binary entry must be executable: {entry}")


def verified_binding(root, provenance):
    result = provenance.verify(root)
    envelope = read_metadata(root / ".provenance.json")
    manifest = read_metadata(root / "app.json")
    package, signature = envelope.get("package", {}), envelope.get("signature", {})
    verified = result["package"]
    if envelope.get("schema") != "claw.provenance/v1" or not isinstance(package, dict) or (
        not isinstance(signature, dict) or package.get("kind") != "app"
        or package.get("manifest_schema") != "cos.app-manifest/v1"
        or package.get("manifest_path") != "app.json" or result.get("manifest_path") != "app.json"
        or signature.get("algorithm") != "ed25519" or signature.get("key_id") != provenance.publisher_key_id
        or package.get("content_digest") != verified.get("content_digest")
    ):
        raise ValueError("App snapshot does not match the public App provenance contract")
    for field in ("id", "version"):
        if not isinstance(manifest.get(field), str) or not manifest[field] or (
            manifest[field] != package.get(field) or manifest[field] != verified.get(field)
        ):
            raise ValueError(f"Authenticated App manifest {field} differs from its envelope")
    entries = package.get("entrypoints")
    if not isinstance(entries, list) or not entries or result.get("entrypoints") != entries:
        raise ValueError("App snapshots require declared signed entrypoints")
    for entry in entries:
        app_path(entry)
    validate_manifest_entries(root, manifest, entries)
    manifest_record = {
        "path": "app.json", "size": (root / "app.json").stat().st_size, "sha256": digest(root / "app.json"),
    }
    files = package.get("files")
    if not isinstance(files, list):
        raise ValueError("App provenance has no signed file inventory")
    for _, entry in manifest_entries(manifest):
        selected = [item for item in files if isinstance(item, dict) and item.get("path") == entry]
        if len(selected) != 1 or selected[0].get("type") != "file" or (
            selected[0].get("size") != (root / entry).stat().st_size
            or selected[0].get("digest") != "sha256:" + digest(root / entry)
        ):
            raise ValueError(f"App selected entry is not bound to its signed file inventory: {entry}")
    bound = [item for item in files if isinstance(item, dict) and item.get("path") == "app.json"]
    if len(bound) != 1 or bound[0].get("type") != "file" or (
        bound[0].get("size") != manifest_record["size"]
        or bound[0].get("digest") != "sha256:" + manifest_record["sha256"]
    ):
        raise ValueError("App manifest bytes do not match their signed provenance inventory")
    return {
        "app_id": manifest["id"], "app_version": manifest["version"], "manifest": manifest_record,
        "provenance": {
            "path": ".provenance.json", "sha256": digest(root / ".provenance.json"),
            "content_digest": sha256_value(package["content_digest"], prefixed=True),
            "publisher_key_id": provenance.publisher_key_id,
        },
    }


def write_archive(root, inventory, destination):
    with destination.open("xb") as stream, gzip.GzipFile(
        filename="", mode="wb", fileobj=stream, mtime=0, compresslevel=6,
    ) as compressed, tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        for name, record in inventory.items():
            tar_entry(archive, root, name, record, 0)


def validate_archive_headers(source):
    # Extended headers are parsed before tarfile yields a member to its data filter.
    with gzip.open(source, "rb") as stream:
        count = total = 0
        pending_metadata = False
        while True:
            block = stream.read(tarfile.BLOCKSIZE)
            if len(block) != tarfile.BLOCKSIZE:
                raise ValueError("App tar stream has a truncated header")
            if block == b"\0" * tarfile.BLOCKSIZE:
                tail = stream.read(tarfile.RECORDSIZE + 1)
                if pending_metadata or len(tail) < tarfile.BLOCKSIZE or (
                    len(tail) > tarfile.RECORDSIZE or any(tail)
                ):
                    raise ValueError("App tar stream has incomplete or unindexed trailing data")
                return
            member = tarfile.TarInfo.frombuf(block, "utf-8", "strict")
            count += 1
            total += member.size
            if member.size < 0 or count > MAX_ENTRIES * 2 or total > MAX_BYTES:
                raise ValueError("App tar stream exceeds its bounded header or payload size")
            if member.type == tarfile.XHDTYPE:
                if pending_metadata or member.size > MAX_METADATA:
                    raise ValueError("App tar metadata is nested or exceeds its size limit")
                pending_metadata = True
            elif member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE):
                pending_metadata = False
            else:
                raise ValueError("App tar stream contains unsupported headers, links or special nodes")
            remaining = (member.size + tarfile.BLOCKSIZE - 1) // tarfile.BLOCKSIZE * tarfile.BLOCKSIZE
            while remaining:
                chunk = stream.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("App tar stream has a truncated member")
                remaining -= len(chunk)


def extract_archive(source, destination):
    validate_archive_headers(source)
    destination.mkdir(mode=0o755)
    nodes, folded = {}, set()
    total = 0
    with tarfile.open(source, mode="r|gz") as archive:
        for member in archive:
            path = app_path(member.name)
            if member.name in nodes or member.name.casefold() in folded or len(nodes) >= MAX_ENTRIES:
                raise ValueError("Duplicate, case-colliding or excessive App archive entries")
            if any(nodes.get(str(parent)) != "directory" for parent in path.parents
                   if parent != PurePosixPath(".")):
                raise ValueError("App archive entry has a missing or non-directory ancestor")
            total += member.size
            if member.size < 0 or total > MAX_BYTES or member.uid or member.gid or member.mode & 0o7000 or (
                not member.issym() and member.mode & 0o022
            ) or any(key != "path" for key in member.pax_headers):
                raise ValueError("Unsafe App archive size, ownership, modes or extended metadata")
            if member.isdir():
                kind = "directory"
            elif member.isfile():
                kind = "file"
            else:
                raise ValueError("claw.provenance/v1 App archives cannot contain links or special nodes")
            archive.extract(member, destination, filter="data")
            (destination / member.name).chmod(member.mode)
            nodes[member.name] = kind
            folded.add(member.name.casefold())


def checksum_bytes(directory, catalog):
    names = {"catalog.json", *(app["artifact"]["file"] for app in catalog["apps"])}
    return "".join(f"{digest(directory / name)}  {name}\n" for name in sorted(names)).encode()


def verify_frozen_catalog(directory, provenance, signing):
    directory = work_path(Path(directory))
    for name in CATALOG_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA:
            raise ValueError("App catalog metadata must be bounded regular files")
    signing.verify(directory / "catalog.json.asc", directory / "catalog.json")
    signing.verify(directory / "SHA256SUMS.asc", directory / "SHA256SUMS")
    catalog = read_metadata(directory / "catalog.json")
    if set(catalog) != {"schema", "release_version", "runtime_abi", "apps"} or (
        catalog.get("schema") != SCHEMA or type(catalog.get("runtime_abi")) is not int
        or catalog["runtime_abi"] != 1 or not isinstance(catalog.get("apps"), list) or not catalog["apps"]
        or len(catalog["apps"]) > 1000
    ):
        raise ValueError("Unsupported App snapshot catalog")
    version(catalog["release_version"])
    files, identities = set(CATALOG_FILES), set()
    with tempfile.TemporaryDirectory(prefix=".snapshot-verify-", dir=directory.parent) as scratch:
        for index, record in enumerate(catalog["apps"]):
            if not isinstance(record, dict) or set(record) != {
                "app_id", "app_version", "architecture", "artifact", "manifest", "provenance",
            }:
                raise ValueError("Invalid App catalog record")
            artifact = record["artifact"]
            if not isinstance(artifact, dict) or set(artifact) != {"file", "size", "sha256", "media_type"} or (
                artifact.get("media_type") != "application/gzip"
                or type(artifact.get("size")) is not int or not 0 < artifact["size"] <= MAX_BYTES
            ):
                raise ValueError("Invalid App snapshot artifact")
            checksum = sha256_value(artifact.get("sha256"))
            filename = f"claw-app-snapshot-{checksum}.tar.gz"
            if artifact.get("file") != filename:
                raise ValueError("App snapshot filename must bind its exact SHA256")
            path = directory / filename
            if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact["size"] or (
                digest(path) != checksum
            ):
                raise ValueError("App snapshot artifact digest or size mismatch")
            identity = (record.get("app_id"), record.get("architecture"))
            if not all(isinstance(value, str) for value in identity) or identity in identities:
                raise ValueError("Duplicate or invalid App identity/architecture in catalog")
            identities.add(identity)
            files.add(filename)
            root = Path(scratch) / str(index)
            extract_archive(path, root)
            tree_inventory(root, record["architecture"])
            expected = {**verified_binding(root, provenance), "architecture": record["architecture"],
                        "artifact": artifact}
            if record != expected:
                raise ValueError("App catalog does not bind the authenticated manifest and provenance")
    if {path.name for path in directory.iterdir()} != files:
        raise ValueError("App catalog directory contains missing or unindexed artifacts")
    if (directory / "SHA256SUMS").read_bytes() != checksum_bytes(directory, catalog):
        raise ValueError("App catalog checksums do not bind exactly its artifacts and manifest catalog")
    return catalog


def verify_catalog(directory, provenance, signing):
    directory = work_path(Path(directory))
    with tempfile.TemporaryDirectory(prefix=".snapshot-catalog-", dir=directory.parent) as scratch:
        frozen = Path(scratch) / "catalog"
        frozen.mkdir()
        total = 0
        for index, source in enumerate(directory.iterdir()):
            if index >= 1000 + len(CATALOG_FILES) or source.is_symlink() or not source.is_file() or (
                source.name not in CATALOG_FILES
                and not re.fullmatch(r"claw-app-snapshot-[0-9a-f]{64}\.tar\.gz", source.name)
            ):
                raise ValueError("App catalog contains an unexpected file, directory or symlink")
            size = source.stat().st_size
            total += size
            if total > MAX_BYTES or (source.name in CATALOG_FILES and size > MAX_METADATA):
                raise ValueError("App catalog exceeds its bounded metadata or total artifact size")
            shutil.copyfile(source, frozen / source.name)
            if (frozen / source.name).stat().st_size != size:
                raise ValueError("App catalog source changed while preparing its private snapshot")
        return verify_frozen_catalog(frozen, provenance, signing)


def build_catalog(app_directories, output, *, release_version, architecture, provenance, signing):
    release_version = version(release_version)
    output = work_path(Path(output))
    if not app_directories or len(app_directories) > 1000 or output.exists():
        raise ValueError("Select prepared App directories and a new immutable output directory")
    sources = [work_path(Path(path)) for path in app_directories]
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in sources):
        raise ValueError("App snapshot inputs and output must not overlap")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-build-", dir=output.parent) as scratch:
        scratch = Path(scratch)
        bundle = scratch / "bundle"
        bundle.mkdir()
        records, identities = [], set()
        for index, source in enumerate(sources):
            if not (source / ".provenance.json").is_file():
                raise ValueError("Unsigned App input: first use the public cos provenance sign command")
            before = tree_inventory(source, architecture)
            root = scratch / f"app-{index}"
            shutil.copytree(source, root, symlinks=True)
            inventory = tree_inventory(root, architecture)
            if inventory != before:
                raise ValueError("App source changed while preparing its private snapshot")
            binding = verified_binding(root, provenance)
            if binding["app_id"] in identities:
                raise ValueError("Selected App identities must remain separate and unique")
            identities.add(binding["app_id"])
            archive = scratch / f"app-{index}.tar.gz"
            write_archive(root, inventory, archive)
            checksum = digest(archive)
            name = f"claw-app-snapshot-{checksum}.tar.gz"
            archive.rename(bundle / name)
            records.append({
                **binding, "architecture": architecture,
                "artifact": {"file": name, "size": (bundle / name).stat().st_size,
                             "sha256": checksum, "media_type": "application/gzip"},
            })
        catalog = {"schema": SCHEMA, "release_version": release_version, "runtime_abi": 1,
                   "apps": sorted(records, key=lambda item: item["app_id"])}
        write_json(bundle / "catalog.json", catalog)
        (bundle / "SHA256SUMS").write_bytes(checksum_bytes(bundle, catalog))
        signing.sign(bundle / "catalog.json", bundle / "catalog.json.asc", armored=True)
        signing.sign(bundle / "SHA256SUMS", bundle / "SHA256SUMS.asc", armored=True)
        verify_catalog(bundle, provenance, signing)
        bundle.rename(output)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--app-directory", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-version")
    parser.add_argument("--architecture", choices=("all", "amd64", "arm64"), default="all")
    parser.add_argument("--cos", type=Path, required=True, help="Public provenance-capable CLI, not an OS checkout")
    parser.add_argument("--cos-sha256", required=True, help="Executable digest from the verified public tool artifact")
    parser.add_argument("--publisher-key-id", required=True, help="Checked-in Ed25519 package-signing key ID")
    arguments = parser.parse_args()
    provenance = Provenance(arguments.cos, arguments.cos_sha256, arguments.publisher_key_id)
    output = work_path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-signing-", dir=output.parent) as scratch:
        with Signing(Path(scratch) / "signing") as signing:
            if arguments.action == "build":
                if arguments.release_version is None:
                    parser.error("build requires --release-version")
                signing.import_environment()
                result = build_catalog(
                    arguments.app_directory, output, release_version=arguments.release_version,
                    architecture=arguments.architecture, provenance=provenance, signing=signing,
                )
            else:
                if arguments.app_directory or arguments.release_version:
                    parser.error("verify reads only the signed catalog and its indexed snapshots")
                result = verify_catalog(output, provenance, signing)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (EOFError, OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        raise SystemExit(1) from error
