"""Public SDK artifact transport is pinned, bounded and independent of OS sources."""

from copy import deepcopy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("platform_dependency", ROOT / "tools/platform_dependency.py")
platform = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(platform)
EXPORTS = {
    "python-sdk": "claw-os-sdk/python/src", "python-runtime": "cos-runtime/python/src",
    "rust-sdk": "claw-os-sdk/rust", "rust-runtime": "cos-runtime/rust",
    "ui-toolkit": "desktop/toolkit", "launcher-client": "desktop/launcher-backend",
}
URL = "https://releases.example.invalid/app-platform-v1.0.0/platform.tar.gz"
SDK_FILE = "claw-os-sdk/python/src/claw_os_sdk/__init__.py"
FILES = {
    SDK_FILE: b"VALUE = 'public SDK'\n",
    "cos-runtime/python/src/cos_runtime/__init__.py": b"VALUE = 'public runtime'\n",
    "claw-os-sdk/wire/v1/manifest.schema.json": b'{"$id":"public manifest schema"}\n',
    **{path + "/Cargo.toml": b"[workspace]\n" for name, path in EXPORTS.items() if not name.startswith("python")},
}


def public_archive(*, files=None, links=None, mutate=None, tar_change=None):
    files = dict(FILES if files is None else files)
    links = dict(links or {})
    nodes = {}
    bodies = {}
    for path, data in files.items():
        nodes[path] = {
            "path": path, "kind": "file", "mode": 0o644, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        bodies[path] = data
    for path, target in links.items():
        nodes[path] = {"path": path, "kind": "symlink", "mode": 0o777, "size": 0, "target": target}
    for path in [*nodes]:
        for parent in PurePosixPath(path).parents:
            if str(parent) not in {".", "desktop"}:
                name = str(parent)
                nodes.setdefault(name, {"path": name, "kind": "directory", "mode": 0o755, "size": 0})
    manifest = {
        "schema": "claw.app-platform/v1", "version": "1.0.0", "runtime_abi": 1,
        "source_revision": "a" * 40, "exports": EXPORTS.copy(),
        "files": sorted(nodes.values(), key=lambda item: item["path"]),
    }
    original = deepcopy(manifest)
    if mutate:
        mutate(manifest)
    metadata = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    members = []
    header = tarfile.TarInfo("platform.json")
    header.mode = 0o644
    header.size = len(metadata)
    members.append((header, metadata))
    for item in original["files"]:
        header = tarfile.TarInfo(item["path"])
        header.mode, header.size = item["mode"], item["size"]
        if item["kind"] == "directory":
            header.type = tarfile.DIRTYPE
        elif item["kind"] == "symlink":
            header.type, header.linkname = tarfile.SYMTYPE, item["target"]
        members.append((header, bodies.get(item["path"])))
    if tar_change:
        tar_change(members)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for member, body in members:
            archive.addfile(member, io.BytesIO(body) if body is not None else None)
    return output.getvalue()


@pytest.fixture
def dependency(tmp_path, monkeypatch):
    root = tmp_path / "clawos-app"
    root.mkdir()
    shared = root / "shared/python"
    for name in ["_shared", "gateway", "gateway/_shared"]:
        directory = shared / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("")
    (shared / "canonical_argv.py").write_text("VALUE = 'App-owned'\n")
    state = SimpleNamespace(root=root, data=public_archive(), calls=[])
    state.lock = {
        "version": "1.0.0", "url": URL, "runtime_abi": 1,
        "sha256": hashlib.sha256(state.data).hexdigest(),
    }

    def repin(data):
        state.data = data
        state.lock["sha256"] = hashlib.sha256(data).hexdigest()
        write_lock(state)

    state.repin = repin
    write_lock(state)
    monkeypatch.setattr(platform, "ROOT", root)

    def download(url, destination):
        assert url == URL
        assert not destination.exists()
        assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
        assert destination.is_relative_to(root / "build/platform-artifacts")
        state.calls.append(url)
        destination.write_bytes(state.data)

    monkeypatch.setattr(platform, "_download", download)
    return state


def write_lock(state):
    (state.root / "platform.lock.json").write_text(json.dumps(state.lock))


def cache(state):
    return state.root / "build/platform-artifacts" / state.lock["sha256"].lower()


def assert_unpublished(state):
    assert not cache(state).exists()
    base = state.root / "build/platform-artifacts"
    assert not base.exists() or not list(base.iterdir())


def test_named_exports_share_one_verified_artifact_and_keep_app_support_local(dependency):
    state = dependency
    paths = platform.prepare()
    payload = cache(state) / "payload"
    assert paths == [payload / EXPORTS["python-sdk"], payload / EXPORTS["python-runtime"],
                     state.root / "shared/python"]
    assert platform.prepare_exports() == {name: payload / path for name, path in EXPORTS.items()}
    toolkit = platform.prepare_native()
    assert toolkit == payload / "desktop/toolkit"
    assert toolkit.parents[1] == payload
    assert platform.manifest_schema_path() == payload / "claw-os-sdk/wire/v1/manifest.schema.json"
    assert platform.prepare(download=False) == paths
    assert state.calls == [URL]
    assert not (payload / "core").exists()
    assert not (payload / "apps").exists()
    assert not (state.root.parent / "claw-os").exists()
    assert stat.S_IMODE(cache(state).stat().st_mode) == 0o700
    assert stat.S_IMODE((cache(state) / "archive.tar.gz").stat().st_mode) == 0o600
    assert stat.S_IMODE((payload / "desktop").stat().st_mode) == 0o755


@pytest.fixture
def development(dependency):
    data = public_archive(mutate=lambda manifest: manifest.update(version="0.1.0"))
    path = dependency.root.parent / "development.tar.gz"
    path.write_bytes(data)
    return platform.DevelopmentArtifact(path, "0.1.0", hashlib.sha256(data).hexdigest())


def development_cache(state, selected):
    return state.root / "build/platform-development" / selected.sha256


def test_local_input_is_explicit_and_preserves_the_production_pin(dependency, development):
    original_lock = (dependency.root / "platform.lock.json").read_bytes()
    published = platform.prepare_exports()
    selected = platform.prepare_exports(development=development)
    expected = development_cache(dependency, development) / "payload"
    assert selected == {name: expected / path for name, path in EXPORTS.items()}
    assert platform.prepare_native(development=development) == expected / "desktop/toolkit"
    assert platform.manifest_schema_path(development=development) == expected / "claw-os-sdk/wire/v1/manifest.schema.json"
    assert platform.prepare_exports(download=False) == published
    assert platform.read_lock() == dependency.lock
    assert (dependency.root / "platform.lock.json").read_bytes() == original_lock
    assert dependency.calls == [URL]
    assert stat.S_IMODE(development_cache(dependency, development).stat().st_mode) == 0o700


def test_local_input_needs_no_production_lock_or_network(dependency, development):
    (dependency.root / "platform.lock.json").unlink()
    paths = platform.prepare(development=development)
    assert paths[:2] == [
        development_cache(dependency, development) / "payload" / EXPORTS[name]
        for name in ("python-sdk", "python-runtime")
    ]
    assert dependency.calls == []
    assert not (dependency.root / "build/platform-artifacts").exists()


def test_local_cache_is_never_an_automatic_production_fallback(dependency, development):
    platform.prepare(development=development)
    with pytest.raises(FileNotFoundError, match="pinned App platform"):
        platform.prepare(download=False)
    assert dependency.calls == []


@pytest.mark.parametrize("field", ["archive", "development"])
def test_local_selection_cannot_be_embedded_in_a_production_pin(dependency, development, field):
    with pytest.raises(ValueError, match="must pin a published artifact"):
        platform.validate_lock({**dependency.lock, field: str(development.archive)})


def test_local_hash_precedes_archive_inspection(dependency, development, monkeypatch):
    wrong = platform.DevelopmentArtifact(development.archive, development.version, "0" * 64)
    monkeypatch.setattr(
        platform.artifact, "inspected_archive",
        lambda *args: pytest.fail("unverified local bytes reached the tar reader"),
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        platform.prepare(development=wrong)
    assert not development_cache(dependency, wrong).exists()
    assert dependency.calls == []


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_local_input_requires_a_regular_file(dependency, development, kind):
    path = dependency.root / "invalid-local-source"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(development.archive)
    else:
        os.mkfifo(path)
    selected = platform.DevelopmentArtifact(path, development.version, development.sha256)
    with pytest.raises((ValueError, OSError)):
        platform.prepare(development=selected)
    assert not development_cache(dependency, development).exists()
    assert dependency.calls == []


@pytest.mark.parametrize("change", [
    {"version": "0.2.0"}, {"runtime_abi": 2}, {"runtime_abi": True},
])
def test_local_metadata_must_match_the_explicit_version_and_supported_abi(dependency, change):
    data = public_archive(mutate=lambda manifest: manifest.update({"version": "0.1.0", **change}))
    path = dependency.root / "wrong-metadata.tar.gz"
    path.write_bytes(data)
    selected = platform.DevelopmentArtifact(path, "0.1.0", hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError, match="mismatch"):
        platform.prepare(development=selected)
    assert not development_cache(dependency, selected).exists()
    assert dependency.calls == []


def test_local_input_keeps_the_public_export_boundary(dependency):
    data = public_archive(
        files={**FILES, "core/private-provider.rs": b"not an App SDK export"},
        mutate=lambda manifest: manifest.update(version="0.1.0"),
    )
    path = dependency.root / "private-provider.tar.gz"
    path.write_bytes(data)
    selected = platform.DevelopmentArtifact(path, "0.1.0", hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError):
        platform.prepare(development=selected)
    assert not development_cache(dependency, selected).exists()


def test_a_mutated_local_input_cannot_fall_back_to_its_good_cache(dependency, development):
    platform.prepare(development=development)
    cached = development_cache(dependency, development) / "archive.tar.gz"
    original = cached.read_bytes()
    development.archive.write_bytes(b"changed local input")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        platform.prepare(download=False, development=development)
    assert cached.read_bytes() == original
    assert dependency.calls == []


@pytest.mark.parametrize("entry", ["archive.tar.gz", "payload/" + SDK_FILE])
def test_a_local_source_does_not_repair_a_tampered_cache(dependency, development, entry):
    platform.prepare(development=development)
    target = development_cache(dependency, development) / entry
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        platform.prepare(development=development)
    assert target.read_bytes() == b"tampered"
    assert dependency.calls == []


def test_local_publication_revalidates_a_concurrent_winner(dependency, development, monkeypatch):
    final = development_cache(dependency, development)

    def winner(source, destination):
        assert destination == final
        shutil.copytree(source, destination, symlinks=True)
        raise FileExistsError(17, "local fixture concurrent publication")

    monkeypatch.setattr(platform.os, "rename", winner)
    assert platform.prepare_native(development=development) == final / "payload/desktop/toolkit"
    assert dependency.calls == []


@pytest.mark.parametrize("supplied", [0, 1, 2])
def test_development_flags_are_required_together(development, supplied):
    values = [None, None, None]
    values[supplied] = (development.archive, development.version, development.sha256)[supplied]
    options = SimpleNamespace(**dict(zip((
        "development_platform", "development_platform_version", "development_platform_sha256",
    ), values)))
    with pytest.raises(ValueError, match="together"):
        platform.development_from_args(options)


def copy_development_tools(root):
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    for name in ("platform_dependency.py", "platform_archive.py", "stage.py",
                 "stage_native.py", "native_build.py"):
        shutil.copy2(ROOT / "tools" / name, tools / name)


def test_local_cli_prepares_an_unpublished_artifact_without_network(dependency, development):
    copy_development_tools(dependency.root)
    driver = (
        "import runpy, sys, urllib.request\n"
        "def forbidden(*args, **kwargs): raise AssertionError('no development download')\n"
        "urllib.request.build_opener = forbidden\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", driver,
         str(dependency.root / "tools/platform_dependency.py"), *development.arguments()],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "production pin unchanged" in result.stderr
    assert str(development_cache(dependency, development)) in result.stdout
    assert not cache(dependency).exists()


def test_pytest_helpers_use_only_the_explicit_development_selection(dependency, development):
    copy_development_tools(dependency.root)
    platform.prepare(development=development)
    tests = dependency.root / "tests"
    tests.mkdir()
    for name in ("test_support.py", "conftest.py"):
        shutil.copy2(ROOT / "tests" / name, tests / name)
    (tests / "test_selected.py").write_text(
        "from test_support import platform_dependency\n"
        "def test_selected():\n"
        "    platform = platform_dependency()\n"
        "    exports = platform.prepare_exports(download=False)\n"
        "    assert 'platform-development' in str(exports['python-sdk'])\n"
        "    assert platform.manifest_schema_path(download=False).is_file()\n"
    )
    command = [sys.executable, "-B", "-m", "pytest", "-q", str(tests / "test_selected.py")]
    environment = {**os.environ, "PYTHONPATH": str(tests)}
    selected = subprocess.run(
        [*command, *development.arguments()], cwd=dependency.root,
        env=environment, capture_output=True, text=True, timeout=30,
    )
    assert selected.returncode == 0, selected.stdout + selected.stderr
    default = subprocess.run(
        command, cwd=dependency.root, env=environment,
        capture_output=True, text=True, timeout=30,
    )
    assert default.returncode != 0
    assert "prepare the pinned App platform artifact" in default.stdout + default.stderr
    assert not cache(dependency).exists()


@pytest.mark.parametrize("app_id", ["pkg", "mail-ai", "user-owned-example"])
def test_artifact_interfaces_need_no_bundled_app_sources_or_special_identity(dependency, monkeypatch, app_id):
    shutil.rmtree(dependency.root / "shared")
    monkeypatch.setenv("COS_APP_ID", app_id)
    exports = platform.prepare_exports()
    assert set(exports) == set(EXPORTS)
    assert exports == platform.prepare_exports(download=False)
    assert not (dependency.root / "shared").exists()
    assert not (cache(dependency) / "payload/apps").exists()
    assert dependency.calls == [URL]


def test_archive_is_verified_before_tar_is_opened(dependency, monkeypatch):
    dependency.lock["sha256"] = "0" * 64
    write_lock(dependency)
    monkeypatch.setattr(platform.artifact.tarfile, "open", lambda *args, **kwargs: pytest.fail("unverified tar opened"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        platform.prepare()
    assert_unpublished(dependency)


@pytest.mark.parametrize("field,value", [
    ("version", "main"), ("version", "../1.0.0"), ("version", 1),
    ("url", "http://example.test/artifact"), ("url", "file:///not-read"),
    ("url", "https://user:secret@example.test/archive"), ("url", "https://example.test/a#fragment"),
    ("url", "https:///missing-host"), ("url", "https://example.test:0/a"),
    ("url", "https://example.test/\nheader"), ("url", None),
    ("sha256", ""), ("sha256", "a" * 63), ("sha256", "z" * 64), ("sha256", 1),
    ("runtime_abi", 2), ("runtime_abi", True), ("runtime_abi", "1"),
    ("schema", "claw.app-platform/v2"), ("repository", "ignored Git source"),
    ("revision", "a" * 40), ("python_sources", ["claw-os-sdk/python/src"]),
])
def test_lock_cannot_select_git_unpinned_or_unsupported_inputs(dependency, field, value):
    dependency.lock[field] = value
    write_lock(dependency)
    with pytest.raises(ValueError):
        platform.prepare()
    assert not dependency.calls
    assert not (dependency.root / "build").exists()


def test_explicit_v1_schema_and_uppercase_hex_pin_are_accepted(dependency):
    dependency.lock.update(schema="claw.app-platform/v1", sha256=dependency.lock["sha256"].upper())
    write_lock(dependency)
    assert platform.prepare_native().is_dir()


def test_release_callers_can_validate_the_same_lock_without_io(dependency):
    lock = {**dependency.lock, "sha256": dependency.lock["sha256"].upper()}
    assert platform.validate_lock(lock)["sha256"] == dependency.lock["sha256"]
    assert lock["sha256"] == dependency.lock["sha256"].upper()
    assert not dependency.calls
    with pytest.raises(ValueError, match="published artifact"):
        platform.validate_lock({"nested": {"sha256": "a" * 64}})


@pytest.mark.parametrize("missing", ["version", "url", "sha256", "runtime_abi"])
def test_missing_lock_field_fails_without_download(dependency, missing):
    del dependency.lock[missing]
    write_lock(dependency)
    with pytest.raises(ValueError):
        platform.prepare_native()
    assert not dependency.calls


def test_duplicate_lock_fields_are_not_ambiguous(dependency):
    raw = json.dumps(dependency.lock)
    (dependency.root / "platform.lock.json").write_text(
        raw.replace('"runtime_abi": 1', '"runtime_abi": 1, "runtime_abi": 1'),
    )
    with pytest.raises(ValueError, match="Duplicate"):
        platform.prepare()
    assert not dependency.calls


def test_old_git_lock_and_existing_git_cache_are_never_fallbacks(dependency, monkeypatch):
    old = dependency.root / "build/platform" / ("a" * 40) / "claw-os-sdk/python/src"
    old.mkdir(parents=True)
    (old / "decoy.py").write_text("must not be loaded")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Git/source process invoked"))
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: pytest.fail("Git/source process invoked"))
    assert platform.prepare()[0] != old
    dependency.lock = {"repository": "https://example.test/os", "revision": "a" * 40,
                       "python_sources": ["claw-os-sdk/python/src", "cos-runtime/python/src"]}
    write_lock(dependency)
    with pytest.raises(ValueError, match="legacy OS Git"):
        platform.prepare()
    assert (old / "decoy.py").read_text() == "must not be loaded"


def test_cache_only_bootstrap_never_downloads(dependency):
    with pytest.raises(FileNotFoundError, match="prepare the pinned"):
        platform.prepare(download=False)
    assert not dependency.calls


@pytest.mark.parametrize("missing", ["_shared/__init__.py", "gateway/_shared/__init__.py", "canonical_argv.py"])
def test_missing_app_support_is_not_supplied_by_os_artifact(dependency, missing):
    (dependency.root / "shared/python" / missing).unlink()
    with pytest.raises(ValueError, match="App shared Python"):
        platform.prepare()
    assert not dependency.calls


@pytest.mark.parametrize("field,value", [
    ("schema", "claw.app-platform/v2"), ("version", "1.0.1"),
    ("runtime_abi", 2), ("runtime_abi", True), ("source_revision", "main"),
    ("exports", {**EXPORTS, "python-sdk": "core/python"}),
    ("exports", {**EXPORTS, "other": "apps/other"}), ("files", []),
])
def test_archive_metadata_must_match_pin_and_public_contract(dependency, field, value):
    dependency.repin(public_archive(mutate=lambda manifest: manifest.update({field: value})))
    with pytest.raises(ValueError):
        platform.prepare_native()
    assert_unpublished(dependency)


@pytest.mark.parametrize("change", ["duplicate", "unsorted", "missing", "file-hash", "file-size", "mode", "private", "traversal"])
def test_inventory_is_exact_and_canonical(dependency, change):
    def mutate(manifest):
        files = manifest["files"]
        file = next(item for item in files if item["path"] == SDK_FILE)
        if change == "duplicate":
            files.append(deepcopy(files[-1]))
        elif change == "unsorted":
            files.reverse()
        elif change == "missing":
            files.remove(file)
        elif change == "file-hash":
            file["sha256"] = "0" * 64
        elif change == "file-size":
            file["size"] += 1
        elif change == "mode":
            file["mode"] = 0o666
        else:
            file["path"] = "core/private.py" if change == "private" else "../escape"
            files.sort(key=lambda item: item["path"])
    dependency.repin(public_archive(mutate=mutate))
    with pytest.raises(ValueError):
        platform.prepare()
    assert_unpublished(dependency)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "claw-os-sdk/../../escape",
                                  "claw-os-sdk\\escape", "core/private.py", "desktop/other-app/main.py",
                                  "DEBIAN/postinst", "etc/sudoers.d/app",
                                  "usr/share/polkit-1/rules.d/app.rules",
                                  "var/lib/cos/permissions.json"])
def test_uninventoried_or_unsafe_tar_paths_never_extract(dependency, name):
    def change(members):
        entry = tarfile.TarInfo(name)
        entry.size, entry.mode = 1, 0o644
        members.append((entry, b"x"))
    dependency.repin(public_archive(tar_change=change))
    with pytest.raises((ValueError, tarfile.FilterError)):
        platform.prepare()
    assert_unpublished(dependency)
    assert not (dependency.root.parent / "escape").exists()


@pytest.mark.parametrize("kind", [tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE])
def test_nonpublic_tar_node_types_are_rejected(dependency, kind):
    def change(members):
        entry = tarfile.TarInfo("claw-os-sdk/special")
        entry.type, entry.mode, entry.linkname = kind, 0o644, SDK_FILE
        members.append((entry, None))
    dependency.repin(public_archive(tar_change=change))
    with pytest.raises(ValueError, match="Unsupported"):
        platform.prepare()
    assert_unpublished(dependency)


def test_duplicate_tar_member_is_rejected(dependency):
    dependency.repin(public_archive(tar_change=lambda members: members.append(members[0])))
    with pytest.raises(ValueError, match="Duplicate"):
        platform.prepare()
    assert_unpublished(dependency)


def test_duplicate_manifest_fields_are_rejected(dependency):
    def change(members):
        member, body = members[0]
        body = body.replace(b'"runtime_abi": 1', b'"runtime_abi": 1, "runtime_abi": 1')
        member.size = len(body)
        members[0] = (member, body)
    dependency.repin(public_archive(tar_change=change))
    with pytest.raises(ValueError, match="Duplicate"):
        platform.prepare()
    assert_unpublished(dependency)


@pytest.mark.parametrize("target", ["/etc/not-read", "../../../escape", "../../core/private",
                                    "bad\\target", "bad\ntarget", "alias.py", "missing.py"])
def test_unsafe_cyclic_and_missing_symlink_targets_are_rejected(dependency, target):
    dependency.repin(public_archive(links={"claw-os-sdk/python/src/alias.py": target}))
    with pytest.raises((ValueError, tarfile.FilterError)):
        platform.prepare()
    assert_unpublished(dependency)


def test_safe_symlink_and_implicit_directory_are_verified_on_every_use(dependency):
    dependency.repin(public_archive(links={"claw-os-sdk/python/src/alias.py": "claw_os_sdk/__init__.py"}))
    platform.prepare()
    link = cache(dependency) / "payload/claw-os-sdk/python/src/alias.py"
    assert link.is_symlink() and os.readlink(link) == "claw_os_sdk/__init__.py"
    assert platform.prepare_native().is_dir()
    link.unlink()
    link.symlink_to("missing.py")
    with pytest.raises(ValueError, match="symlink mismatch"):
        platform.prepare()
    assert dependency.calls == [URL]


@pytest.mark.parametrize("change", ["bytes", "missing", "extra", "bytecode", "mode", "directory-mode",
                                   "symlink", "implicit-extra", "implicit-mode", "manifest",
                                   "archive", "archive-mode", "outer-extra", "payload-symlink"])
def test_modified_cache_is_rejected_without_redownload_or_repair(dependency, change):
    platform.prepare()
    root = cache(dependency)
    payload = root / "payload"
    file = payload / SDK_FILE
    if change == "bytes":
        file.write_bytes(b"changed")
    elif change == "missing":
        file.unlink()
    elif change in {"extra", "bytecode"}:
        (file.parent / ("extra.py" if change == "extra" else "extra.pyc")).write_bytes(b"unexpected")
    elif change == "mode":
        file.chmod(0o755)
    elif change == "directory-mode":
        file.parent.chmod(0o700)
    elif change == "symlink":
        file.unlink()
        file.symlink_to("missing")
    elif change == "implicit-extra":
        (payload / "desktop/other").mkdir()
    elif change == "implicit-mode":
        (payload / "desktop").chmod(0o700)
    elif change == "manifest":
        manifest = json.loads((payload / "platform.json").read_text())
        body = b"forged cache and matching extracted manifest"
        file.write_bytes(body)
        node = next(item for item in manifest["files"] if item["path"] == SDK_FILE)
        node.update(size=len(body), sha256=hashlib.sha256(body).hexdigest())
        (payload / "platform.json").write_text(json.dumps(manifest))
    elif change == "archive":
        (root / "archive.tar.gz").write_bytes(b"changed archive")
    elif change == "archive-mode":
        (root / "archive.tar.gz").chmod(0o644)
    elif change == "outer-extra":
        (root / "extra").write_text("unrelated evidence")
    else:
        original = dependency.root / "original-payload"
        payload.rename(original)
        payload.symlink_to(original, target_is_directory=True)
    before = file.read_bytes() if file.is_file() else None
    with pytest.raises((ValueError, OSError, tarfile.TarError)):
        platform.prepare()
    assert dependency.calls == [URL]
    if before is not None:
        assert file.read_bytes() == before


def test_standard_data_filter_is_used_and_umask_does_not_change_verified_modes(dependency, monkeypatch):
    original = tarfile.TarFile.extractall
    called = []
    def extract(self, *args, **kwargs):
        called.append(kwargs.get("filter"))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(tarfile.TarFile, "extractall", extract)
    old_umask = os.umask(0o077)
    try:
        platform.prepare()
    finally:
        os.umask(old_umask)
    assert called == ["data"]
    assert platform.prepare_native().is_dir()


@pytest.mark.parametrize("limit", ["MAX_ARCHIVE_BYTES", "MAX_EXPANDED_BYTES", "MAX_FILE_BYTES",
                                  "MAX_METADATA_BYTES", "MAX_ENTRIES"])
def test_archive_limits_fail_before_publication(dependency, monkeypatch, limit):
    monkeypatch.setattr(platform.artifact, limit, 1)
    with pytest.raises((ValueError, tarfile.TarError)):
        platform.prepare()
    assert_unpublished(dependency)


def test_huge_hidden_tar_metadata_is_bounded_before_parser_allocation(dependency):
    header = tarfile.TarInfo("././@LongLink")
    header.type = tarfile.GNUTYPE_LONGNAME
    header.size = platform.artifact.MAX_METADATA_BYTES + 1
    dependency.repin(gzip.compress(header.tobuf(format=tarfile.GNU_FORMAT) + bytes(1024)))
    with pytest.raises(ValueError, match="metadata size limit"):
        platform.prepare()
    assert_unpublished(dependency)


def test_failed_download_never_publishes_partial_cache(dependency, monkeypatch):
    def fail(url, destination):
        destination.write_bytes(b"partial")
        raise TimeoutError("synthetic timeout")
    monkeypatch.setattr(platform, "_download", fail)
    with pytest.raises(TimeoutError):
        platform.prepare()
    assert_unpublished(dependency)


@pytest.mark.parametrize("corrupt_winner", [False, True])
def test_atomic_publication_validates_a_concurrent_winner(dependency, monkeypatch, corrupt_winner):
    final = cache(dependency)
    def publish(source, destination):
        assert destination == final and not destination.exists()
        platform._cache_layout(source)
        assert (source / "payload" / SDK_FILE).read_bytes() == FILES[SDK_FILE]
        shutil.copytree(source, destination, symlinks=True)
        if corrupt_winner:
            (destination / "payload" / SDK_FILE).write_bytes(b"bad concurrent cache")
        raise FileExistsError(17, "fixture concurrent publication")
    monkeypatch.setattr(platform.os, "rename", publish)
    if corrupt_winner:
        with pytest.raises(ValueError, match="mismatch"):
            platform.prepare()
    else:
        assert platform.prepare_native() == final / "payload/desktop/toolkit"
    assert dependency.calls == [URL]


def test_cache_archive_symlink_is_never_followed(dependency):
    platform.prepare()
    stored = cache(dependency) / "archive.tar.gz"
    original = dependency.root / "original-archive"
    stored.rename(original)
    stored.symlink_to(original)
    with pytest.raises(OSError):
        platform.prepare()
    assert original.read_bytes() == dependency.data
    assert dependency.calls == [URL]


def test_symlink_cannot_be_an_inventory_parent(dependency):
    dependency.repin(public_archive(links={"claw-os-sdk/python": "../cos-runtime"}))
    with pytest.raises(ValueError, match="nondirectory ancestor"):
        platform.prepare()
    assert_unpublished(dependency)


def test_source_native_host_uses_only_verified_cached_exports(dependency):
    platform.prepare()
    tools = dependency.root / "tools"
    tools.mkdir()
    for name in ["platform_dependency.py", "platform_archive.py", "stage.py"]:
        shutil.copy2(ROOT / "tools" / name, tools / name)
    app = dependency.root / "products/mail/apps/mail-ai"
    app.mkdir(parents=True)
    shutil.copy2(ROOT / "products/mail/apps/mail-ai/native_host.py", app / "native_host.py")
    (app / "main.py").write_text(
        "import claw_os_sdk, cos_runtime\n"
        "assert claw_os_sdk.VALUE == 'public SDK'\n"
        "assert cos_runtime.VALUE == 'public runtime'\n"
        "HANDLERS = {'fixture': lambda: None}\n"
    )
    driver = (
        "import runpy, sys, urllib.request\n"
        "def forbidden(*args, **kwargs): raise AssertionError('network must never run')\n"
        "urllib.request.build_opener = forbidden\n"
        "sys.argv = [sys.argv[1], '--probe']\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    command = ["python3", "-I", "-c", driver, str(app / "native_host.py")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True, "verbs": ["fixture"]}
    assert not list((cache(dependency) / "payload").rglob("__pycache__"))
    platform.prepare()
    shutil.rmtree(cache(dependency))
    missing = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert missing.returncode != 0
    assert "prepare the pinned App platform artifact" in missing.stderr
    assert "network must never run" not in missing.stderr


@pytest.mark.parametrize("local", [False, True])
def test_test_runner_disables_cache_bytecode(dependency, development, monkeypatch, local):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location("artifact_test_runner", ROOT / "tools/test.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "prepare", platform.prepare)
    selected_arguments = development.arguments() if local else []
    monkeypatch.setattr(runner.sys, "argv", ["test.py", "--shared", *selected_arguments])
    calls = []
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    runner.main()
    assert len(calls) == 1
    environment = calls[0][1]["env"]
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    expected = development_cache(dependency, development) if local else cache(dependency)
    assert str(expected / "payload" / EXPORTS["python-sdk"]) in environment["PYTHONPATH"]
    command = calls[0][0][0]
    if local:
        assert command[5:11] == selected_arguments
        assert dependency.calls == []
    else:
        assert "--development-platform" not in command


def test_real_os_artifact_interoperability(dependency, request):
    path = request.config.getoption("--platform-artifact-fixture")
    if not path:
        pytest.skip("Pass an explicit OS-built --platform-artifact-fixture for interoperability")
    with Path(path).open("rb") as source:
        data = source.read(platform.artifact.MAX_ARCHIVE_BYTES + 1)
    assert len(data) <= platform.artifact.MAX_ARCHIVE_BYTES
    dependency.repin(data)
    python = platform.prepare()
    toolkit = platform.prepare_native()
    assert (toolkit / "Cargo.toml").is_file()
    assert (toolkit.parents[1] / "cos-runtime/rust/Cargo.toml").is_file()
    script = (
        "import sys\n"
        "sys.path[:0] = sys.argv[1:]\n"
        "from claw_os_sdk.mcp import App\n"
        "from cos_runtime import policy\n"
        "assert callable(App.from_manifest) and callable(policy.require)\n"
        "print('verified SDK/runtime imports')\n"
    )
    imported = subprocess.run(
        ["python3", "-I", "-B", "-c", script, *map(str, python)],
        capture_output=True, text=True, timeout=15,
    )
    assert imported.returncode == 0, imported.stderr
    assert imported.stdout.strip() == "verified SDK/runtime imports"
    platform.prepare(download=False)
    assert platform.manifest_schema_path(download=False).is_file()
    assert dependency.calls == [URL]


def test_download_only_allows_https_redirects():
    handler = platform._HTTPSRedirect()
    request = urllib.request.Request(URL)
    redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example.invalid/asset")
    assert redirected.full_url == "https://cdn.example.invalid/asset"
    for url in ["http://cdn.example.invalid/asset", "file:///not-read", "ftp://example.invalid/asset"]:
        with pytest.raises(ValueError, match="HTTPS"):
            handler.redirect_request(request, None, 302, "Found", {}, url)


@pytest.mark.parametrize("condition", ["valid", "no-length", "http-final", "status", "header-large", "body-large",
                                      "truncated", "time"])
def test_download_bounds_status_and_final_scheme(tmp_path, monkeypatch, condition):
    data = b"fixture archive"
    response = io.BytesIO(data)
    response.status = 206 if condition == "status" else 200
    response.headers = {"Content-Length": str(len(data) + (1 if condition == "truncated" else 0))}
    response.geturl = lambda: "http://example.invalid/asset" if condition == "http-final" else URL
    if condition in {"body-large", "no-length"}:
        response.headers.clear()
    if condition in {"body-large", "header-large"}:
        monkeypatch.setattr(platform.artifact, "MAX_ARCHIVE_BYTES", len(data) - 1)
    if condition == "time":
        times = iter([0, platform.DOWNLOAD_SECONDS + 1])
        monkeypatch.setattr(platform.time, "monotonic", lambda: next(times))
    def open_request(request, timeout):
        assert request.full_url == URL and timeout == platform.DOWNLOAD_TIMEOUT
        assert request.headers["Accept-encoding"] == "identity"
        return response
    monkeypatch.setattr(platform.urllib.request, "build_opener", lambda handler: SimpleNamespace(open=open_request))
    destination = tmp_path / "download"
    if condition in {"valid", "no-length"}:
        platform._download(URL, destination)
        assert destination.read_bytes() == data
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    else:
        with pytest.raises((ValueError, TimeoutError)):
            platform._download(URL, destination)
