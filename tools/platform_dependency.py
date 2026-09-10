"""Fetch the digest-pinned public App platform artifact, never an OS checkout."""

import errno
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ABI = 1
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_SECONDS = 180


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = _module("app_shared_stage", "stage.py")
artifact = _module("app_platform_archive", "platform_archive.py")


def _https(url):
    if (
        not isinstance(url, str) or len(url) > 8192
        or any(ord(char) <= 32 or ord(char) == 127 for char in url)
    ):
        raise ValueError("App platform URL must be HTTPS")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.fragment
    ):
        raise ValueError("App platform URL and redirects must be HTTPS without credentials/fragments")
    if parsed.port is not None and not 0 < parsed.port < 65536:
        raise ValueError("Invalid App platform HTTPS port")
    return url


def validate_lock(lock):
    """Validate the same public pin contract for preparation and release callers."""
    required = {"version", "url", "sha256", "runtime_abi"}
    if not isinstance(lock, dict) or set(lock) not in (required, required | {"schema"}):
        raise ValueError(
            "platform.lock.json must pin a published artifact with version, url, sha256 and "
            "runtime_abi; legacy OS Git/source fields are not supported"
        )
    if lock.get("schema", artifact.SCHEMA) != artifact.SCHEMA:
        raise ValueError("Unsupported App platform lock schema")
    if not isinstance(lock["version"], str) or not artifact.SEMVER.fullmatch(lock["version"]):
        raise ValueError("App platform version must be an explicit release version")
    if type(lock["runtime_abi"]) is not int or lock["runtime_abi"] != RUNTIME_ABI:
        raise ValueError("Unsupported App platform runtime ABI")
    if not isinstance(lock["sha256"], str) or not artifact.SHA256.fullmatch(lock["sha256"]):
        raise ValueError("App platform SHA-256 must be exactly 64 hexadecimal characters")
    _https(lock["url"])
    return {**lock, "sha256": lock["sha256"].lower()}


def read_lock():
    with (ROOT / "platform.lock.json").open("rb") as source:
        data = source.read(16 * 1024 + 1)
    if len(data) > 16 * 1024:
        raise ValueError("App platform lock is oversized")
    return validate_lock(artifact.read_json(data))


class _HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url, destination):
    request = urllib.request.Request(
        _https(url), headers={"Accept-Encoding": "identity", "User-Agent": "clawos-app-platform/1"},
    )
    opener = urllib.request.build_opener(_HTTPSRedirect())
    started = time.monotonic()
    with opener.open(request, timeout=DOWNLOAD_TIMEOUT) as response:
        _https(response.geturl())
        if response.status != 200:
            raise ValueError("App platform download requires an HTTP 200 response")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            if not declared.isascii() or not declared.isdecimal() or not 0 <= int(declared) <= artifact.MAX_ARCHIVE_BYTES:
                raise ValueError("App platform download size limit exceeded")
            declared = int(declared)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            total = 0
            while True:
                chunk = response.read(artifact.CHUNK)
                if time.monotonic() - started > DOWNLOAD_SECONDS:
                    raise TimeoutError("App platform download time limit exceeded")
                if not chunk:
                    break
                total += len(chunk)
                if total > artifact.MAX_ARCHIVE_BYTES:
                    raise ValueError("App platform download size limit exceeded")
                output.write(chunk)
            if declared is not None and total != declared:
                raise ValueError("App platform download is truncated")


def _cache_base():
    base = ROOT / "build" / "platform-artifacts"
    for path in (ROOT / "build", base):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("Invalid App platform cache directory")
        path.mkdir(mode=0o700, exist_ok=True)
    return base


def _cache_layout(cache):
    if cache.is_symlink() or not cache.is_dir() or stat.S_IMODE(cache.stat().st_mode) != 0o700:
        raise ValueError("Invalid App platform cache root")
    if {path.name for path in cache.iterdir()} != {"archive.tar.gz", "payload"}:
        raise ValueError("App platform cache has missing or extra entries")
    payload = cache / "payload"
    if payload.is_symlink() or not payload.is_dir():
        raise ValueError("Invalid App platform cache payload")
    with artifact.regular_file(cache / "archive.tar.gz", mode=0o600):
        pass


def prepare_exports(*, download=True):
    """Resolve named library exports only after archive and cache verification."""
    lock = read_lock()
    base = _cache_base()
    cache = base / lock["sha256"]
    existing = cache.exists() or cache.is_symlink()
    if existing:
        _cache_layout(cache)
    elif not download:
        raise FileNotFoundError("Run tools/platform_dependency.py to prepare the pinned App platform artifact")
    with tempfile.TemporaryDirectory(prefix=".platform-", dir=base) as temporary:
        temporary = Path(temporary)
        ready = temporary / "ready"
        ready.mkdir(mode=0o700)
        verified = ready / "archive.tar.gz"
        if existing:
            artifact.copy_verified_archive(cache / "archive.tar.gz", verified, lock["sha256"])
        else:
            received = temporary / "download"
            _download(lock["url"], received)
            artifact.copy_verified_archive(received, verified, lock["sha256"])
        payload = cache / "payload" if existing else ready / "payload"
        with artifact.inspected_archive(
            verified, temporary, lock["version"], lock["runtime_abi"], payload,
        ) as (archive, manifest, expected):
            if not existing:
                artifact.extract_payload(archive, payload, expected)
            artifact.validate_payload(payload, expected)
        if not existing:
            try:
                os.rename(ready, cache)
            except OSError as error:
                if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
                return prepare_exports(download=False)
        return {name: cache / "payload" / path for name, path in manifest["exports"].items()}


def prepare(*, download=True):
    shared = stage.shared_python_root(ROOT)
    exports = prepare_exports(download=download)
    return [exports["python-sdk"], exports["python-runtime"], shared]


def manifest_schema_path(*, download=True):
    exports = prepare_exports(download=download)
    schema = exports["python-sdk"].parents[1] / "wire/v1/manifest.schema.json"
    if not schema.is_file():
        raise ValueError("App platform artifact lacks its public SDK manifest schema")
    return schema


def prepare_native():
    return prepare_exports()["ui-toolkit"]


if __name__ == "__main__":
    for path in prepare():
        print(path)
