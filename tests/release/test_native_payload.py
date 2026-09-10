"""Structural installer fixtures are not native product or GUI acceptance."""

from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import shutil
import sys

import pytest

import native_build
import native_payload
import release
import release_snapshots as snapshots
from release_common import ROOT, digest, license_files, run, write_json
import stage

PRODUCTS = (
    "editor", "files", "terminal", "launcher", "store",
    "media-player", "capture", "settings", "notifications",
)
ARCHITECTURE = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]


@pytest.fixture
def installer(tmp_path):
    def make(product):
        selected = native_payload.plan(product)
        root = tmp_path / f"installer-{product}"
        (root / "usr/bin").mkdir(parents=True)
        for name in (selected.program, *selected.auxiliary_programs):
            # Actual product binaries are supplied separately to the signed acceptance tests.
            shutil.copy2("/usr/bin/true", root / "usr/bin" / name)
        asset = root / "usr/share/icons/hicolor/scalable/apps" / f"{selected.app_id}.svg"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"original resource bytes\n")
        asset.chmod(0o440)
        return selected, root
    return make


def test_empty_resource_directories_and_modes_are_preserved(installer, tmp_path):
    selected, installed = installer("capture")
    empty = installed / "usr/share/icons/empty"
    empty.mkdir(mode=0o750)
    result = native_payload.prepare(selected, installed, tmp_path / "app", ARCHITECTURE)
    retained = result.root / "resources/usr/share/icons/empty"
    assert retained.is_dir() and not list(retained.iterdir())
    assert retained.stat().st_mode & 0o777 == 0o750


def test_changed_source_manifest_invalidates_the_native_plan(installer, tmp_path):
    selected, installed = installer("capture")
    source = tmp_path / "source"
    source.mkdir()
    manifest = json.loads(selected.manifest_bytes)
    manifest["summary"]["en"] += " changed"
    (source / "app.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest changed"):
        native_payload.prepare(replace(selected, source=source), installed, tmp_path / "app", ARCHITECTURE)
    assert not (tmp_path / "app").exists()


def test_exports_consume_the_prepared_copy_not_mutable_installer_paths(installer, tmp_path, monkeypatch):
    selected, installed = installer("capture")
    origin = installed / f"usr/share/icons/hicolor/scalable/apps/{selected.app_id}.svg"
    expected = origin.read_bytes()
    original_prepare = native_payload.prepare

    def prepare_then_replace(*args):
        prepared = original_prepare(*args)
        origin.chmod(0o600)
        origin.write_bytes(b"changed after native preparation")
        return prepared

    monkeypatch.setattr(native_payload, "prepare", prepare_then_replace)
    destination = tmp_path / "installed"
    native_payload.install(selected, installed, destination, ARCHITECTURE)
    exported = destination / origin.relative_to(installed)
    assert exported.read_bytes() == expected
    assert exported.stat().st_mode & 0o777 == 0o440
    assert (destination / selected.installed_app / "resources" / origin.relative_to(installed)).read_bytes() == expected


def test_uncontracted_global_resources_are_not_exported(installer, tmp_path):
    selected, installed = installer("capture")
    uncontracted = installed / "usr/share/keyrings/not-an-app-resource.gpg"
    uncontracted.parent.mkdir()
    uncontracted.write_bytes(b"must not become a global trust input")
    with pytest.raises(ValueError, match="explicit OS installation contract"):
        native_payload.install(selected, installed, tmp_path / "rejected", ARCHITECTURE)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("product", PRODUCTS)
def test_every_native_plan_binds_one_local_gui_and_mcp_entry(product):
    selected = native_payload.plan(product)
    manifest = snapshots.read_metadata(selected.source / "app.json")
    expected = f"bin/{selected.program}"
    assert manifest["entry"] == manifest["mcp"]["entry"] == expected
    assert snapshots.manifest_entries(manifest) == [
        ("operation/GUI", expected), ("MCP/background", expected),
    ]
    assert selected.entrypoints == (expected,)
    assert selected.record()["gui_command"] == [
        "/usr/local/bin/cos", "app", manifest["id"], manifest["desktop"]["exec"],
    ]
    assert selected.record()["unsigned_preparation_only"] is True
    packages = release.packages_for(product)
    assert {entry["architecture"] for entry in packages if entry["variant"] == "desktop"} == {"amd64", "arm64"}


@pytest.mark.parametrize("product", PRODUCTS)
def test_native_preparation_preserves_bytes_modes_licenses_and_raw_manifest(product, installer, tmp_path):
    selected, installed = installer(product)
    original = (selected.source / "app.json").read_bytes()
    result = native_payload.prepare(selected, installed, tmp_path / "app", ARCHITECTURE)
    assert (result.root / "app.json").read_bytes() == original
    assert (selected.source / "app.json").read_bytes() == original
    for name in (selected.program, *selected.auxiliary_programs):
        binary = result.root / "bin" / name
        assert binary.read_bytes() == (installed / "usr/bin" / name).read_bytes()
        assert binary.stat().st_mode & 0o777 == 0o755
        assert binary.stat().st_nlink == 1
    for relative in result.resources:
        origin = installed / relative.removeprefix("resources/")
        assert (result.root / relative).read_bytes() == origin.read_bytes()
        assert (result.root / relative).stat().st_mode == origin.stat().st_mode
    for license_path in license_files(selected.license.parent):
        target = result.root / "licenses" / license_path.relative_to(selected.license.parent)
        assert target.read_bytes() == license_path.read_bytes()
    assert not (result.root / ".provenance.json").exists()
    assert not (result.root / "usr/lib/cos/python").exists()
    snapshots.validate_manifest_entries(result.root, json.loads(original), result.entrypoints)
    with pytest.raises(ValueError, match="declared signed"):
        snapshots.validate_manifest_entries(result.root, json.loads(original), [])
    with pytest.raises(ValueError, match="overwrite"):
        native_payload.prepare(selected, installed, result.root, ARCHITECTURE)


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("failure", ("missing", "script", "wrong_architecture", "nonexecutable", "symlink", "hardlink"))
def test_every_native_payload_refuses_bad_executable_before_writing(product, failure, installer, tmp_path):
    selected, installed = installer(product)
    binary = installed / "usr/bin" / selected.program
    if failure == "missing":
        binary.unlink()
    elif failure == "script":
        binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    elif failure == "wrong_architecture":
        data = bytearray(binary.read_bytes())
        data[18:20] = (183 if ARCHITECTURE == "amd64" else 62).to_bytes(2, "little")
        binary.write_bytes(data)
    elif failure == "nonexecutable":
        binary.chmod(0o644)
    elif failure == "symlink":
        binary.unlink()
        binary.symlink_to("/usr/bin/true")
    elif failure == "hardlink":
        os.link(binary, tmp_path / "outside-package")
    with pytest.raises(ValueError):
        native_payload.prepare(selected, installed, tmp_path / "rejected", ARCHITECTURE)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("entry", ("", "/usr/bin/outside", "../outside", "bin/../outside", "bin\\program", None))
def test_native_plan_refuses_bad_explicit_manifest_entries(entry, tmp_path, monkeypatch):
    source, package = stage.load_package("capture")
    fixture = tmp_path / "source"
    app = fixture / package["apps"][0]
    app.mkdir(parents=True)
    manifest = snapshots.read_metadata(source / package["apps"][0] / "app.json")
    manifest["entry"] = entry
    (app / "app.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(native_payload.stage, "load_package", lambda product, kind: (fixture, package))
    with pytest.raises(ValueError):
        native_payload.plan("capture")


@pytest.mark.parametrize("path", (
    "usr/share/polkit-1/rules.d/cosmic-settings.rules",
    "usr/share/polkit-1/actions/com.clawos.Settings.Users.policy",
    "etc/claw/permissions.json",
))
def test_settings_authority_payload_is_rejected_not_stripped_or_exempted(path, installer, tmp_path):
    selected, installed = installer("settings")
    authority = installed / path
    authority.parent.mkdir(parents=True, exist_ok=True)
    authority.write_bytes(b"must remain refused\n")
    for operation in (native_payload.prepare, native_payload.install):
        with pytest.raises(ValueError, match="authority hooks"):
            operation(selected, installed, tmp_path / "rejected", ARCHITECTURE)
        assert authority.read_bytes() == b"must remain refused\n"
        assert not (tmp_path / "rejected").exists()


def test_files_auxiliary_elf_is_preserved_but_not_an_implicit_execution_surface(installer, tmp_path):
    selected, installed = installer("files")
    result = native_payload.prepare(selected, installed, tmp_path / "app", ARCHITECTURE)
    assert (result.root / "bin/cosmic-files-applet").is_file()
    assert result.entrypoints == ("bin/cosmic-files",)
    with pytest.raises(ValueError, match="no declared common Host entry"):
        native_payload.install(selected, installed, tmp_path / "not-installed", ARCHITECTURE)
    assert not (tmp_path / "not-installed").exists()


@pytest.mark.parametrize("product", [name for name in PRODUCTS if name != "files"])
def test_compatibility_exports_only_enter_common_host(product, installer, tmp_path):
    selected, installed = installer(product)
    desktop = installed / "usr/share/applications" / f"{selected.app_id}.desktop"
    desktop.parent.mkdir()
    desktop.write_text(f"[Desktop Entry]\nExec={selected.program} %U\n")
    destination = tmp_path / "installed"
    stage.stage(product, destination, [selected.app_id])
    binaries = native_payload.install(selected, installed, destination, ARCHITECTURE)
    assert binaries == (destination / selected.installed_app / f"bin/{selected.program}",)
    wrapper = destination / "usr/bin" / selected.program
    assert wrapper.read_bytes() == native_payload.compatibility_launcher(selected)
    assert wrapper.stat().st_mode & 0o777 == 0o755
    assert b'/usr/local/bin/cos app ' in wrapper.read_bytes()
    assert b'"$@"' in wrapper.read_bytes()
    assert (destination / desktop.relative_to(installed)).read_bytes() == desktop.read_bytes()
    assert (destination / selected.installed_app / "app.json").read_bytes() == (selected.source / "app.json").read_bytes()


@pytest.mark.parametrize("metadata", (
    "Exec=/bin/sh -c forbidden\n",
    " Exec = /bin/sh -c forbidden\n",
    "TryExec=/other/program\n",
    "Exec=cosmic-screenshot\nDBusActivatable=true\n",
    "Exec=cosmic-screenshot\nDBusActivatable = TRUE\n",
    "Name=No executable\n",
))
def test_compatibility_refuses_alternate_execution_or_activation(metadata, installer, tmp_path):
    selected, installed = installer("capture")
    desktop = installed / "usr/share/applications/fixture.desktop"
    desktop.parent.mkdir()
    desktop.write_text("[Desktop Entry]\n" + metadata)
    with pytest.raises(ValueError, match="Host"):
        native_payload.install(selected, installed, tmp_path / "rejected", ARCHITECTURE)
    assert not (tmp_path / "rejected").exists()


def test_wrapper_preserves_public_cli_arguments_and_host_error_without_executing_an_app(tmp_path):
    selected = native_payload.plan("settings")
    wrapper = tmp_path / "wrapper"
    wrapper.write_bytes(native_payload.compatibility_launcher(selected))
    wrapper.chmod(0o755)
    recorder = tmp_path / "cos-argv-recorder"
    recorder.write_text("#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(23)\n")
    recorder.chmod(0o755)
    arguments = ["network", "--new-window", "file:///tmp/a b", "$(not-a-command)", "--", "-leading"]
    result = run([
        "bwrap", "--unshare-all", "--die-with-parent", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind", recorder, "/usr/local/bin/cos", "--ro-bind", wrapper, "/wrapper",
        "/wrapper", *arguments,
    ], check=False)
    assert result.returncode == 23
    assert json.loads(result.stdout) == ["app", selected.app_id, "--gui", *arguments]


@pytest.mark.parametrize("app_only", (False, True))
def test_native_builder_composes_original_installer_with_local_app_stager(app_only, installer, tmp_path, monkeypatch):
    selected, installed = installer("capture")
    _, package = stage.load_package("capture")
    calls = []

    def original_installer(command, **kwargs):
        calls.append(command)
        assert command[0] == "just" and command[-1] == "install"
        raw = Path(next(value.removeprefix("rootdir=") for value in command if value.startswith("rootdir=")))
        assert raw != tmp_path / "output"
        shutil.copytree(installed, raw, dirs_exist_ok=True)

    monkeypatch.setattr(native_build.subprocess, "run", original_installer)
    output = tmp_path / "output"
    native_build.install_payload("capture", package, tmp_path / "prepared", output, {}, app_only=app_only)
    app = output if app_only else output / selected.installed_app
    assert (app / "bin" / selected.program).read_bytes() == (installed / "usr/bin" / selected.program).read_bytes()
    assert (app / "app.json").read_bytes() == (selected.source / "app.json").read_bytes()
    assert len(calls) == 1


def test_native_plan_cli_does_not_build_or_fetch_and_refuses_host_output_roots():
    command = [sys.executable, ROOT / "tools/native_payload.py", "notifications"]
    result = run([*command, "--plan"])
    assert json.loads(result.stdout)["entrypoints"] == ["bin/cosmic-notifications"]
    result = run([*command, "--installed-root", "/", "--app-root", "/", "--architecture", ARCHITECTURE], check=False)
    assert result.returncode != 0
    assert b"explicit directories under build/" in result.stderr


@pytest.mark.parametrize("product,option", [
    ("settings", "--native-settings-fixture"),
    ("notifications", "--native-notifications-fixture"),
])
def test_real_native_elf_preparation_and_isolated_mcp(
    product, option, request, tmp_path, native_mcp_probe,
):
    supplied = request.config.getoption(option)
    if not supplied:
        pytest.skip(f"Real native execution requires the explicit {option} ELF")
    binary = Path(supplied).resolve(strict=True)
    selected = native_payload.plan(product)
    installed = tmp_path / "installed-input"
    program = installed / "usr/bin" / selected.program
    program.parent.mkdir(parents=True)
    shutil.copy2(binary, program)
    prepared = native_payload.prepare(selected, installed, tmp_path / "app", ARCHITECTURE)
    assert digest(prepared.root / prepared.entrypoints[0]) == digest(binary)
    assert (prepared.root / prepared.entrypoints[0]).stat().st_mode & 0o777 == binary.stat().st_mode & 0o777
    assert (prepared.root / "app.json").read_bytes() == selected.manifest_bytes
    tools = native_mcp_probe(prepared.root, prepared.entrypoints[0])
    manifest = json.loads(selected.manifest_bytes)
    assert {tool["name"] for tool in tools} == {tool["name"] for tool in manifest["mcp"]["tools"]}
    write_json(tmp_path / "native-transport.json", {
        "product": product, "binary": str(binary), "sha256": digest(binary),
        "size": binary.stat().st_size, "entrypoints": list(prepared.entrypoints),
        "real_elf": True, "isolated_mcp_tools": sorted(tool["name"] for tool in tools),
        "scope": "Real full ELF copying and isolated MCP transport only; not signed snapshot/resource/GUI/authority acceptance",
    })
