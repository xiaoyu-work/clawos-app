"""Prepare real package-local native Apps; installation and authority stay separate."""

import argparse
import configparser
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import tempfile

import stage
from release_common import license_files, work_path
from release_payload import validate_install_tree
from release_snapshots import (
    app_path, manifest_entries, read_metadata, read_metadata_snapshot,
    tree_inventory, validate_manifest_entries,
)

HOST = "/usr/local/bin/cos"
PROGRAM = re.compile(r"[a-z][a-z0-9-]*")
RESOURCE_EXPORTS = (
    "usr/share/applications", "usr/share/icons", "usr/share/metainfo",
    "usr/share/thumbnailers", "usr/share/cosmic",
)


@dataclass(frozen=True)
class NativePlan:
    product: str
    app_id: str
    source: Path
    license: Path
    installed_app: Path
    program: str
    auxiliary_programs: tuple[str, ...]
    entrypoints: tuple[str, ...]
    gui_selector: str
    manifest_bytes: bytes = field(repr=False)

    def record(self):
        return {
            "product": self.product, "app_id": self.app_id,
            "installed_app": self.installed_app.as_posix(),
            "program": self.program, "entrypoints": list(self.entrypoints),
            "auxiliary_programs": list(self.auxiliary_programs),
            "manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
            "gui_command": [HOST, "app", self.app_id, self.gui_selector],
            "resources": "Original installer usr/share files, archived under resources/usr/share",
            "unsigned_preparation_only": True,
        }


@dataclass(frozen=True)
class PreparedNative:
    root: Path
    entrypoints: tuple[str, ...]
    binaries: tuple[Path, ...]
    resources: tuple[str, ...]
    source_inventory: dict
    installer_inventory: dict
    payload_inventory: dict


def plan(product):
    source, package = stage.load_package(product, "product")
    declaration = package.get("native_payload")
    if package.get("native_kind") != "binary":
        raise ValueError("A native library is not an independently runnable App payload")
    if not isinstance(declaration, dict) or (
        set(declaration) - {"app", "program", "auxiliary_programs"}
        or not {"app", "program"} <= declaration.keys()
    ):
        raise ValueError("Native payload requires an explicit product-owned binary declaration")
    app_id, program = declaration["app"], declaration["program"]
    if not isinstance(app_id, str) or not PROGRAM.fullmatch(app_id) or (
        not isinstance(program, str) or not PROGRAM.fullmatch(program)
    ):
        raise ValueError("Native payload requires a declared App and canonical program name")
    auxiliary = declaration.get("auxiliary_programs", [])
    if not isinstance(auxiliary, list) or any(
        not isinstance(name, str) or not PROGRAM.fullmatch(name) for name in auxiliary
    ) or len(set([program, *auxiliary])) != 1 + len(auxiliary):
        raise ValueError("Native auxiliary programs must be distinct declared program names")
    apps = stage.app_entries(source, package)
    if app_id not in apps:
        raise ValueError("Native payload App must belong to this product")
    app = apps[app_id]
    manifest_bytes, manifest = read_metadata_snapshot(app / "app.json")
    entry = f"bin/{program}"
    entries = tuple(sorted({path for _, path in manifest_entries(manifest)}))
    mcp, desktop = manifest.get("mcp"), manifest.get("desktop")
    if manifest.get("id") != app_id or manifest.get("runtime") != "binary" or (
        manifest.get("schema_version") != 2 or manifest.get("entry") != entry
        or not isinstance(mcp, dict) or mcp.get("entry") != entry
        or mcp.get("transport") != "stdio" or entries != (entry,)
        or not isinstance(desktop, dict)
    ):
        raise ValueError("Native GUI/MCP must explicitly select the same package-local binary")
    selector = desktop.get("exec", "--gui")
    if not isinstance(selector, str) or not selector or selector in ("--help", "-h", "help", "--schema") or len(selector) > 256 or any(
        ord(char) < 32 or ord(char) == 127 for char in selector
    ):
        raise ValueError("Native GUI requires its exact non-empty declared selector")
    return NativePlan(
        product, app_id, app, source / "native/LICENSE",
        Path("usr/lib/cos/apps") / app.relative_to(source / "apps"),
        program, tuple(auxiliary), entries, selector, manifest_bytes,
    )


def validate_elf(path, architecture):
    """Require a loadable executable ELF, not a script, library or header-only fixture."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not info.st_mode & 0o111:
        raise ValueError(f"Native payload requires a single-link executable regular file: {path}")
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
            raise ValueError(f"Native installer did not produce a runnable {architecture} ELF: {path}")
        fields = struct.unpack("<16sHHIQQQIHHHHHH", header)
        _, kind, machine, version, entry, phoff, _, _, ehsize, phsize, phnum, _, _, _ = fields
        if kind not in (2, 3) or machine != {"amd64": 62, "arm64": 183}.get(architecture) or (
            version != 1 or not entry or ehsize != 64 or phsize != 56 or not 0 < phnum <= 4096
            or phoff < 64 or phoff + phsize * phnum > info.st_size
        ):
            raise ValueError(f"Native installer did not produce a runnable {architecture} ELF: {path}")
        stream.seek(phoff)
        executable_entry = False
        for _ in range(phnum):
            segment = stream.read(phsize)
            if len(segment) != phsize:
                raise ValueError(f"Native ELF changed while reading its load segments: {path}")
            kind, flags, offset, address, _, filesz, memsz, _ = struct.unpack("<IIQQQQQQ", segment)
            if kind == 1:
                if filesz > memsz or offset + filesz > info.st_size:
                    raise ValueError(f"Native ELF has an invalid load segment: {path}")
                executable_entry |= bool(flags & 1 and address <= entry < address + memsz)
        if not executable_entry:
            raise ValueError(f"Native ELF entry has no executable load segment: {path}")


def _inputs(selected, installed, architecture):
    validate_install_tree(installed, allow_control=False)
    inventory = tree_inventory(installed, architecture)
    programs = {f"usr/bin/{name}" for name in (selected.program, *selected.auxiliary_programs)}
    for name, record in inventory.items():
        if record["type"] != "file":
            if name not in ("usr", "usr/bin", "usr/share") and not name.startswith("usr/share/"):
                raise ValueError(f"Native installer produced an unowned directory: {name}")
            continue
        info = (installed / name).stat()
        if info.st_nlink != 1:
            raise ValueError(f"Native installer output must not contain hardlinks: {name}")
        if name.startswith("usr/bin/"):
            if name not in programs:
                raise ValueError(f"Native installer produced an undeclared executable: {name}")
            validate_elf(installed / name, architecture)
        elif not name.startswith("usr/share/") or info.st_mode & 0o111:
            raise ValueError(f"Native installer produced an unowned resource or executable: {name}")
    for name in programs:
        if name not in inventory or inventory[name]["type"] != "file":
            raise ValueError(f"Native installer did not produce its declared executable: {name}")
    return inventory


def _payload_path(name):
    if name == "usr":
        return None
    if name == "usr/bin" or name.startswith("usr/bin/"):
        return name.removeprefix("usr/")
    return "resources/" + name


def prepare(selected, installed, destination, architecture):
    """Create an unsigned App directory ready for the existing public provenance signer."""
    installed, destination = Path(installed), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Refusing to overwrite a native App preparation: {destination}")
    inventory = _inputs(selected, installed, architecture)
    if (selected.source / ".provenance.json").exists():
        raise ValueError("Native preparation must not rewrite an already signed App")
    if not selected.license.is_file() or selected.license.is_symlink():
        raise ValueError("Native payload requires its original product license")
    source_bytes = (selected.source / "app.json").read_bytes()
    if source_bytes != selected.manifest_bytes:
        raise ValueError("Native source manifest changed after its payload plan")
    resources, binaries = [], []
    complete = created = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o755)
        created = True
        shutil.copytree(selected.source, destination, dirs_exist_ok=True, symlinks=True, ignore=stage.IGNORE)
        destination.chmod(0o755)
        source_inventory = tree_inventory(destination, architecture)
        for reserved in ("bin", "resources", "licenses", ".provenance.json"):
            if (destination / reserved).exists() or (destination / reserved).is_symlink():
                raise ValueError(f"Native source conflicts with its prepared payload: {reserved}")
        if (destination / "LICENSE").exists():
            if (destination / "LICENSE").read_bytes() != selected.license.read_bytes():
                raise ValueError("Native App and product licenses conflict")
        else:
            shutil.copy2(selected.license, destination / "LICENSE")
        for license_path in license_files(selected.license.parent):
            if license_path.is_symlink():
                raise ValueError(f"Native license must be a regular owned file: {license_path}")
            target = destination / "licenses" / license_path.relative_to(selected.license.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(license_path, target)
        for name, record in inventory.items():
            relative = _payload_path(name)
            if relative is None:
                continue
            target = destination / relative
            app_path(relative)
            if record["type"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(record["mode"])
                continue
            if name.startswith("usr/bin/"):
                binaries.append(destination / relative)
            else:
                resources.append(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(installed / name, target, follow_symlinks=False)
        if tree_inventory(installed, architecture) != inventory or (
            (destination / "app.json").read_bytes() != source_bytes
            or (selected.source / "app.json").read_bytes() != source_bytes
        ):
            raise ValueError("Native payload inputs changed during preparation")
        validate_manifest_entries(destination, read_metadata(destination / "app.json"), selected.entrypoints)
        copied = tree_inventory(destination, architecture)
        for name, record in inventory.items():
            target = _payload_path(name)
            if target is not None and copied.get(target) != record:
                raise ValueError(f"Native payload bytes or modes changed during preparation: {name}")
        complete = True
        return PreparedNative(
            destination, selected.entrypoints, tuple(binaries), tuple(resources),
            source_inventory, inventory, copied,
        )
    finally:
        if created and not complete and destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)


def compatibility_launcher(selected):
    command = " ".join(shlex.quote(value) for value in (
        HOST, "app", selected.app_id, selected.gui_selector,
    ))
    return f'#!/bin/sh\nexec {command} "$@"\n'.encode()


def _launch_metadata(selected, origin, name):
    if origin.suffix == ".service":
        raise ValueError(f"Native D-Bus activation requires an authenticated Host contract: {name}")
    if origin.suffix not in (".desktop", ".thumbnailer"):
        return
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.optionxform = str
    try:
        metadata.read_string(origin.read_text())
    except configparser.Error as error:
        raise ValueError(f"Malformed native launch metadata: {name}") from error
    found = False
    for section in metadata.sections():
        for key, value in metadata.items(section, raw=True):
            if key in ("Exec", "TryExec"):
                words = shlex.split(value)
                if not words or words[0] not in (selected.program, f"/usr/bin/{selected.program}") or (
                    key == "TryExec" and len(words) != 1
                ):
                    raise ValueError(f"Native launch metadata bypasses its common Host: {name}")
                found |= key == "Exec"
            if key == "DBusActivatable" and metadata.getboolean(section, key):
                raise ValueError(f"Native D-Bus activation requires an authenticated Host contract: {name}")
    if not found:
        raise ValueError(f"Native launch metadata requires its explicit common Host command: {name}")


def install(selected, installed, destination, architecture):
    """Stage App bytes and Host-only exports, never a second direct native launcher."""
    installed, destination = Path(installed), Path(destination)
    _inputs(selected, installed, architecture)
    if destination.exists():
        tree_inventory(destination, architecture)
    if selected.auxiliary_programs:
        raise ValueError(
            "Native compatibility surface has no declared common Host entry: "
            + ", ".join(selected.auxiliary_programs)
            + "; prepare App-only signed resources separately and keep this package gated"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-payload-", dir=destination.parent) as temporary:
        prepared = prepare(selected, installed, Path(temporary) / selected.app_id, architecture)
        target = destination / selected.installed_app
        if target.exists() and tree_inventory(target, architecture) != prepared.source_inventory:
            raise ValueError("Native installation conflicts with an existing App payload")
        exports = {}
        for name, record in prepared.installer_inventory.items():
            if record["type"] == "file":
                if name.startswith("usr/bin/"):
                    exports[name] = compatibility_launcher(selected)
                else:
                    if not any(name.startswith(prefix + "/") for prefix in RESOURCE_EXPORTS):
                        raise ValueError(f"Native resource export requires an explicit OS installation contract: {name}")
                    origin = prepared.root / _payload_path(name)
                    _launch_metadata(selected, origin, name)
                    exports[name] = origin.read_bytes()
                    if hashlib.sha256(exports[name]).hexdigest() != record["sha256"]:
                        raise ValueError(f"Prepared native resource changed before export: {name}")
        for name in exports:
            if (destination / name).exists() or (destination / name).is_symlink():
                raise ValueError(f"Conflicting native compatibility export: {name}")
        if target.exists():
            for name, record in prepared.payload_inventory.items():
                if name in prepared.source_inventory:
                    continue
                output = target / name
                if record["type"] == "directory":
                    output.mkdir(mode=record["mode"])
                else:
                    with (prepared.root / name).open("rb") as source, output.open("xb") as stream:
                        shutil.copyfileobj(source, stream)
                    output.chmod(record["mode"])
        else:
            shutil.copytree(prepared.root, target)
        if tree_inventory(target, architecture) != prepared.payload_inventory:
            raise ValueError("Native App payload changed during installation")
        for name, content in exports.items():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(content)
            output.chmod(0o755 if name.startswith("usr/bin/") else prepared.installer_inventory[name]["mode"])
        return tuple(target / binary.relative_to(prepared.root) for binary in prepared.binaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--installed-root", type=Path)
    parser.add_argument("--app-root", type=Path)
    parser.add_argument("--architecture", choices=("amd64", "arm64"))
    args = parser.parse_args()
    selected = plan(args.product)
    if args.plan:
        if args.installed_root or args.app_root or args.architecture:
            parser.error("--plan cannot prepare an output")
        print(json.dumps(selected.record()))
        return
    if not args.installed_root or not args.app_root or not args.architecture:
        parser.error("preparation requires --installed-root, --app-root and --architecture")
    result = prepare(
        selected, work_path(args.installed_root),
        work_path(args.app_root), args.architecture,
    )
    print(json.dumps({**selected.record(), "root": str(result.root), "resources": list(result.resources)}))


if __name__ == "__main__":
    main()
