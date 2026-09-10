"""Validate and extract the public claw.app-platform/v1 library artifact."""

from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tarfile


SCHEMA = "claw.app-platform/v1"
EXPORTS = {
    "python-sdk": "claw-os-sdk/python/src",
    "python-runtime": "cos-runtime/python/src",
    "rust-sdk": "claw-os-sdk/rust",
    "rust-runtime": "cos-runtime/rust",
    "ui-toolkit": "desktop/toolkit",
    "launcher-client": "desktop/launcher-backend",
}
SOURCE_ROOTS = ("claw-os-sdk", "cos-runtime", "desktop/toolkit", "desktop/launcher-backend")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 50_000
CHUNK = 1024 * 1024
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA256 = re.compile(r"[0-9a-fA-F]{64}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate App platform JSON field")
        result[key] = value
    return result


def read_json(data):
    return json.loads(data, object_pairs_hook=_unique_object)


def _public_path(path):
    return any(path == root or path.startswith(root + "/") for root in SOURCE_ROOTS)


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or "\\" in value:
        raise ValueError("Invalid App platform path")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or str(path) != value or value == "."
        or ".." in path.parts or len(path.parts) > 64
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Noncanonical App platform path")
    return path


def _mode(kind, mode):
    if type(mode) is not int or not 0 <= mode <= 0o777:
        raise ValueError("Invalid App platform mode")
    if kind == "symlink":
        if mode != 0o777:
            raise ValueError("Invalid App platform symlink mode")
    elif mode & 0o022 or (kind == "directory" and mode & 0o700 != 0o700):
        raise ValueError("Unsafe App platform mode")


def _manifest(data, version, runtime_abi):
    manifest = read_json(data)
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "version", "runtime_abi", "source_revision", "exports", "files",
    }:
        raise ValueError("Invalid App platform manifest fields")
    if manifest["schema"] != SCHEMA or manifest["version"] != version:
        raise ValueError("App platform schema/version mismatch")
    if type(manifest["runtime_abi"]) is not int or manifest["runtime_abi"] != runtime_abi:
        raise ValueError("App platform runtime ABI mismatch")
    revision = manifest["source_revision"]
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid App platform source revision")
    if manifest["exports"] != EXPORTS:
        raise ValueError("App platform named exports do not match the public contract")
    files = manifest["files"]
    if not isinstance(files, list) or not files or len(files) > MAX_ENTRIES:
        raise ValueError("Invalid App platform inventory size")
    nodes = {}
    previous = ""
    total = 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Invalid App platform inventory entry")
        path = _path(item.get("path"))
        name = str(path)
        kind = item.get("kind")
        keys = {"path", "mode", "kind", "size"}
        if kind == "file":
            keys.add("sha256")
        elif kind == "symlink":
            keys.add("target")
        elif kind != "directory":
            raise ValueError("Unsupported App platform inventory kind")
        if set(item) != keys or name <= previous or not _public_path(name):
            raise ValueError("Invalid, unsorted or private App platform inventory")
        previous = name
        _mode(kind, item["mode"])
        size = item["size"]
        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES or (kind != "file" and size):
            raise ValueError("Invalid App platform file size")
        total += size
        if total > MAX_EXPANDED_BYTES:
            raise ValueError("App platform expanded size limit exceeded")
        if kind == "file":
            if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
                raise ValueError("Invalid App platform file digest")
        elif kind == "symlink":
            target = item["target"]
            if (
                not isinstance(target, str) or not target or len(target) > 4096
                or "\\" in target or PurePosixPath(target).is_absolute()
                or any(ord(char) < 32 or ord(char) == 127 for char in target)
                or posixpath.normpath(target) != target
            ):
                raise ValueError("Unsafe App platform symlink")
            resolved = posixpath.normpath(posixpath.join(str(path.parent), target))
            _path(resolved)
            if not _public_path(resolved):
                raise ValueError("App platform symlink escapes public library roots")
        nodes[name] = item
    implicit = {}
    for name in nodes:
        for parent in _path(name).parents:
            if str(parent) == ".":
                continue
            if str(parent) in nodes:
                if nodes[str(parent)]["kind"] != "directory":
                    raise ValueError("App platform entry has a nondirectory ancestor")
            else:
                implicit[str(parent)] = {
                    "path": str(parent), "kind": "directory", "mode": 0o755, "size": 0,
                }
                if len(nodes) + len(implicit) > MAX_ENTRIES:
                    raise ValueError("App platform directory limit exceeded")
    expected = {**implicit, **nodes}
    for path in EXPORTS.values():
        if path not in expected or expected[path]["kind"] != "directory":
            raise ValueError("Missing App platform named export")
    for name, item in nodes.items():
        if item["kind"] != "symlink":
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), item["target"]))
        seen = {name}
        while True:
            parts = PurePosixPath(target).parts
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                linked = expected.get(prefix)
                if linked is not None and linked["kind"] == "symlink":
                    if prefix in seen or len(seen) >= 40:
                        raise ValueError("Cyclic or excessive App platform symlinks")
                    seen.add(prefix)
                    target = posixpath.normpath(posixpath.join(
                        posixpath.dirname(prefix), linked["target"], *parts[index:],
                    ))
                    break
            else:
                if target not in expected or not _public_path(target):
                    raise ValueError("Missing or unsafe App platform symlink target")
                break
    return manifest, expected, set(implicit)


@contextmanager
def regular_file(path, *, size=None, mode=None, limit=MAX_ARCHIVE_BYTES):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode) or info.st_size > limit
            or (size is not None and info.st_size != size)
            or (mode is not None and stat.S_IMODE(info.st_mode) != mode)
        ):
            raise ValueError("App platform regular file type/size/mode mismatch")
        yield stream


def digest_stream(stream):
    digest = hashlib.sha256()
    while chunk := stream.read(CHUNK):
        digest.update(chunk)
    return digest.hexdigest()


def copy_verified_archive(source, destination, digest):
    with regular_file(source, limit=MAX_ARCHIVE_BYTES) as incoming:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            checksum = hashlib.sha256()
            total = 0
            while chunk := incoming.read(CHUNK):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("App platform download size limit exceeded")
                checksum.update(chunk)
                output.write(chunk)
            if checksum.hexdigest() != digest:
                raise ValueError("App platform SHA-256 mismatch")


class _MetadataBoundedReader(io.BufferedReader):
    def read(self, size=-1):
        if size < 0 or size > MAX_METADATA_BYTES:
            raise ValueError("App platform tar metadata size limit exceeded")
        return super().read(size)


@contextmanager
def inspected_archive(path, workspace, version, runtime_abi, destination):
    # Bound expansion before tarfile parses even hidden GNU/PAX metadata.
    expanded = workspace / "expanded.tar"
    total = 0
    with gzip.open(path, "rb") as incoming, expanded.open("xb") as output:
        while chunk := incoming.read(CHUNK):
            total += len(chunk)
            if total > MAX_EXPANDED_BYTES:
                raise ValueError("App platform expanded size limit exceeded")
            output.write(chunk)
    with _MetadataBoundedReader(expanded.open("rb", buffering=0)) as stream:
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            members = {}
            for member in archive:
                name = str(_path(member.name))
                if name in members or len(members) >= MAX_ENTRIES + 256:
                    raise ValueError("Duplicate or excessive App platform tar entries")
                if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE, tarfile.SYMTYPE}:
                    raise ValueError("Unsupported App platform tar entry")
                if member.sparse is not None or not 0 <= member.size <= MAX_FILE_BYTES:
                    raise ValueError("Unsupported or oversized App platform tar entry")
                if name == "platform.json" and (not member.isfile() or member.size > MAX_METADATA_BYTES):
                    raise ValueError("Invalid App platform manifest entry")
                members[name] = member
            metadata = members.get("platform.json")
            if metadata is None or metadata.mode != 0o644:
                raise ValueError("Missing or invalid App platform manifest")
            with archive.extractfile(metadata) as source:
                data = source.read(MAX_METADATA_BYTES + 1)
            manifest, expected, implicit = _manifest(data, version, runtime_abi)
            expected["platform.json"] = {
                "path": "platform.json", "kind": "file", "mode": 0o644,
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            }
            if set(members) - set(expected) or set(expected) - set(members) - implicit:
                raise ValueError("App platform tar does not match its inventory")
            for name, member in members.items():
                item = expected[name]
                kind = "file" if member.isfile() else "directory" if member.isdir() else "symlink"
                _mode(kind, member.mode)
                if name in implicit:
                    expected[name] = item = {**item, "mode": member.mode}
                if (kind, member.mode, member.size) != (item["kind"], item["mode"], item["size"]):
                    raise ValueError("App platform tar type/size/mode differs from inventory")
                filtered = tarfile.data_filter(member, str(destination))
                if kind == "file":
                    if filtered.mode != member.mode:
                        raise ValueError("Unsupported App platform file permissions")
                    with archive.extractfile(member) as source:
                        if digest_stream(source) != item["sha256"].lower():
                            raise ValueError("App platform file digest differs from inventory")
                elif kind == "symlink" and (
                    member.linkname != item["target"] or filtered.linkname != item["target"]
                ):
                    raise ValueError("App platform symlink differs from inventory")
            yield archive, manifest, expected


def extract_payload(archive, destination, expected):
    destination.mkdir(mode=0o700)
    archive.extractall(destination, filter="data")
    # data_filter intentionally leaves directory modes to the extractor's umask.
    for name, item in sorted(expected.items(), key=lambda pair: len(PurePosixPath(pair[0]).parts), reverse=True):
        if item["kind"] == "directory":
            path = destination / name
            if path.is_symlink() or not path.is_dir():
                raise ValueError("Invalid extracted App platform directory")
            path.chmod(item["mode"])


def validate_payload(destination, expected):
    if destination.is_symlink() or not destination.is_dir() or stat.S_IMODE(destination.stat().st_mode) != 0o700:
        raise ValueError("Invalid App platform payload root")
    seen = set()
    pending = [destination]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                name = path.relative_to(destination).as_posix()
                item = expected.get(name)
                if item is None:
                    raise ValueError(f"Unexpected App platform cache entry: {name!r}")
                seen.add(name)
                mode = entry.stat(follow_symlinks=False).st_mode
                kind = (
                    "symlink" if stat.S_ISLNK(mode) else
                    "directory" if stat.S_ISDIR(mode) else
                    "file" if stat.S_ISREG(mode) else "unsupported"
                )
                if (kind, stat.S_IMODE(mode)) != (item["kind"], item["mode"]):
                    raise ValueError(f"App platform cache type/mode mismatch: {name!r}")
                if kind == "directory":
                    pending.append(path)
                elif kind == "symlink":
                    if os.readlink(path) != item["target"]:
                        raise ValueError(f"App platform cache symlink mismatch: {name!r}")
                else:
                    with regular_file(path, size=item["size"], mode=item["mode"], limit=MAX_FILE_BYTES) as source:
                        if digest_stream(source) != item["sha256"].lower():
                            raise ValueError(f"App platform cache digest mismatch: {name!r}")
    if seen != set(expected):
        raise ValueError("Missing App platform cache entries")
