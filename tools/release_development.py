"""Content-addressed App fixture sources and declared shared-crate compatibility exports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tomllib

from release_common import ROOT, digest, relative_path, run, version, work_path, write_json
from release_wheels import stage_wheels
from package_assets import asset_entries
import stage
import stage_native

FORMAT = "claw.app-development/v1"
STAGING_FIELDS = {"apps", "kind", "extension", "python_library", "python_dependencies", "installed_assets"}
SOURCE_IGNORE = shutil.ignore_patterns(".git", "target", "build", "node_modules", "__pycache__",
                                      ".pytest_cache", "*.pyc", "*.pyo")
MAX_FILES = 20_000
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
RETIRED_NATIVE_INTERFACES = {"cosmic-notifications-config", "cosmic-notifications-util"}


def source_closure(selection):
    if selection in ("support", "sets"):
        return []
    first = ("capability", selection.removeprefix("capability:")) if selection.startswith("capability:") else (
        "product", selection,
    )
    pending = [first]
    groups = {}
    while pending:
        kind, name = pending.pop()
        if (kind, name) in groups:
            continue
        source, package = stage.load_package(name, kind)
        exports = package.get("native_libraries", {})
        if not isinstance(exports, dict):
            raise ValueError("Native library declarations must be an object")
        if RETIRED_NATIVE_INTERFACES.intersection(exports):
            raise ValueError(
                "Notifications config/util release exports are retired; use the public presentation SDK"
            )
        apps = stage.app_entries(source, package)
        stage.python_libraries(source, package, list(apps))
        groups[kind, name] = {
            "kind": kind, "name": name, "path": f"{stage.SOURCE_ROOTS[kind]}/{name}",
            "role": "selected" if (kind, name) == first else "python-dependency",
            "apps": list(apps), "source_package": package,
        }
        pending.extend((item["kind"], item["name"]) for item in package.get("python_dependencies", []))
    return [groups[key] for key in sorted(groups)]


def copy_source(source, destination, *, boundary):
    if not source.resolve().is_relative_to(boundary.resolve()):
        raise ValueError("Fixture source escapes its declared owner")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, symlinks=True, ignore=SOURCE_IGNORE)
    elif source.is_file() and not source.is_symlink():
        shutil.copy2(source, destination)
    else:
        raise ValueError("Fixture root must be a regular source file or directory")


def interface_roots(groups):
    result = {}
    for group in groups:
        if group["role"] != "selected" or group["kind"] != "product":
            continue
        source = ROOT / group["path"]
        package = group["source_package"]
        for name, relative in stage_native.library_paths(source, package).items():
            component = relative.parts[0]
            root = source / package["native"][component] / Path(*relative.parts[1:])
            if name in result:
                raise ValueError("Duplicate native interface export")
            result[name] = (root, group["name"])
    return result


def validate_interface(name, root, roots):
    manifest = tomllib.loads((root / "Cargo.toml").read_text())
    package = manifest["package"]
    library = manifest.get("lib", {})
    entry = root / relative_path(library.get("path", "src/lib.rs"))
    if package.get("name") != name or not entry.is_file() or not entry.resolve().is_relative_to(root.resolve()):
        raise ValueError("Native interface identity or library entrypoint is invalid")
    if any(key in manifest for key in ("bin", "example", "bench", "workspace", "build-dependencies")) or (
        package.get("build") not in (None, False) or library.get("proc-macro") or library.get("proc_macro")
    ) or any((root / path).exists() for path in ("src/main.rs", "src/bin", "build.rs", "examples")):
        raise ValueError("Native interface exports cannot contain product executables or build hooks")
    if "workspace" in package or any(isinstance(value, dict) and value.get("workspace") for value in package.values()):
        raise ValueError("Native interface metadata must be independent of its product workspace")

    def dependencies(value):
        for key, item in value.items():
            if key in ("dependencies", "dev-dependencies", "build-dependencies"):
                yield from item.values()
            elif isinstance(item, dict):
                yield from dependencies(item)

    allowed = {path.resolve() for path, _ in roots.values()}
    for dependency in dependencies(manifest):
        if isinstance(dependency, dict):
            if dependency.get("workspace"):
                raise ValueError("Native interface dependencies cannot inherit the product workspace")
            if "path" in dependency and (root / dependency["path"]).resolve() not in allowed:
                raise ValueError("Native interface depends on undeclared product implementation")
    for source in root.rglob("*.rs"):
        for relative in re.findall(r'include(?:_str|_bytes)?!\s*\(\s*"([^"]+)"', source.read_text()):
            if not (source.parent / relative).resolve().is_relative_to(root.resolve()):
                raise ValueError("Native interface includes undeclared product implementation")
    return {"path": f"interfaces/{name}", "package": name, "version": package["version"]}


def prepare_sources(selection, destination):
    groups = source_closure(selection)
    copy_source(ROOT / "LICENSE", destination / "LICENSE", boundary=ROOT)
    copy_source(ROOT / "tools/stage.py", destination / "tools/stage.py", boundary=ROOT)
    copy_source(ROOT / "tools/package_assets.py", destination / "tools/package_assets.py", boundary=ROOT)
    copy_source(ROOT / "shared/python", destination / "shared/python", boundary=ROOT / "shared")
    for group in groups:
        source = ROOT / group["path"]
        target = destination / group["path"]
        package = group["source_package"]
        # This is the complete staging projection, not a truncated native build tree.
        projection = {key: package[key] for key in STAGING_FIELDS if key in package}
        projection["tests"] = []
        write_json(target / "package.json", projection)
        for relative in package["apps"]:
            copy_source(source / relative, target / relative, boundary=source)
        if "python_library" in package:
            relative = package["python_library"]["path"]
            copy_source(source / relative, target / relative, boundary=source)
        if "extension" in package:
            copy_source(source / package["extension"], target / package["extension"], boundary=source)
            copy_source(source / "build-extension.py", target / "build-extension.py", boundary=source)
        for origin, _ in asset_entries(source, package, group["apps"]):
            copy_source(origin, target / origin.relative_to(source), boundary=source)
        for path in source.iterdir():
            if path.is_file() and re.fullmatch(r"(?:LICENSE|COPYING|COPYRIGHT|NOTICE|PROVENANCE)(?:[._-].*)?",
                                             path.name, re.IGNORECASE):
                copy_source(path, target / path.name, boundary=source)
    interfaces = {}
    roots = interface_roots(groups)
    for name, (source, owner) in roots.items():
        metadata = validate_interface(name, source, roots)
        target = destination / metadata["path"]
        copy_source(source, target, boundary=source)
        license_file = ROOT / "products" / owner / "native/LICENSE"
        if not any(path.name.upper().startswith("LICENSE") for path in target.iterdir()):
            copy_source(license_file, target / "LICENSE", boundary=ROOT / "products" / owner)
        interfaces[name] = {**metadata, "owner": owner}
    return groups, interfaces


def stage_payload(destination, groups):
    payload = destination / "payload"
    stager = destination / "tools/stage.py"
    environment = {"PYTHONDONTWRITEBYTECODE": "1"}
    run([sys.executable, stager, "--shared", "--root", payload], cwd=destination, env=environment)
    installed = []
    for group in groups:
        if group["role"] == "selected":
            result = run([sys.executable, stager, group["name"], "--kind", group["kind"],
                          "--root", payload], cwd=destination, env=environment)
            apps = json.loads(result.stdout)
            if apps != group["apps"]:
                raise ValueError("Fixture staging differs from its declared identities")
            installed.extend(apps)
        stage_wheels(group["name"], payload, owner=(
            f"claw-{'cap' if group['kind'] == 'capability' else 'app'}-{group['name']}"
        ))
    return installed


def inventory(root):
    result = {}
    total = 0
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        relative_path(name)
        if path.is_symlink():
            if Path(os.readlink(path)).is_absolute() or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError("Fixture symlink escapes its declared archive")
            record = {"type": "symlink", "target": os.readlink(path), "mode": 0o777}
        elif path.is_dir():
            record = {"type": "directory", "mode": 0o755}
        elif path.is_file():
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_SIZE or total > MAX_TOTAL_SIZE:
                raise ValueError("Fixture source exceeds the bounded archive size")
            record = {"type": "file", "size": size, "sha256": digest(path),
                      "mode": 0o755 if path.stat().st_mode & 0o111 else 0o644}
        else:
            raise ValueError("Fixture source contains a special file")
        result[name] = record
        if len(result) > MAX_FILES:
            raise ValueError("Fixture source exceeds the bounded file count")
    return result


def tar_entry(archive, root, name, record, epoch):
    member = tarfile.TarInfo(name)
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    member.mtime = epoch
    member.mode = record["mode"]
    if record["type"] == "directory":
        member.type = tarfile.DIRTYPE
        archive.addfile(member)
    elif record["type"] == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = record["target"]
        archive.addfile(member)
    else:
        member.size = (root / name).stat().st_size
        with (root / name).open("rb") as stream:
            archive.addfile(member, stream)


def build_archive(plan, selection, output):
    version(plan["version"])
    if not re.fullmatch(r"[0-9a-f]{40}", plan["source_revision"]):
        raise ValueError("Fixture archive requires a full source commit")
    output = work_path(output)
    output.mkdir(parents=True, exist_ok=True)
    root = output / (".development-" + selection.replace(":", "-"))
    root.mkdir()
    partial = root / "archive.tar.xz"
    try:
        groups, interfaces = prepare_sources(selection, root)
        apps = stage_payload(root, groups)
        files = inventory(root)
        manifest = {
            "format": FORMAT, "selection": selection, "version": plan["version"],
            "source_revision": plan["source_revision"], "source_date_epoch": plan["source_date_epoch"],
            "runtime_abi": 1, "purpose": "development-and-integration-fixtures",
            "groups": groups, "apps": apps, "stager": "tools/stage.py",
            "asset_helper": "tools/package_assets.py",
            "payload": "payload", "shared_python": "shared/python",
            "native_interfaces": interfaces, "files": files,
        }
        write_json(root / "manifest.json", manifest)
        with tarfile.open(partial, "w:xz", format=tarfile.PAX_FORMAT, preset=6) as archive:
            tar_entry(archive, root, "manifest.json", {"type": "file", "mode": 0o644},
                      plan["source_date_epoch"])
            for name, record in files.items():
                tar_entry(archive, root, name, record, plan["source_date_epoch"])
        sha256 = digest(partial)
        filename = f"claw-app-development-{sha256}.tar.xz"
        record = {
            "format": FORMAT, "selection": selection, "version": plan["version"],
            "source_revision": plan["source_revision"], "filename": filename,
            "sha256": sha256, "size": partial.stat().st_size,
        }
        target = output / filename
        if target.exists():
            raise ValueError("Refusing to overwrite a development archive")
        partial.rename(target)
        verify_archive(target, record, plan)
        return record
    finally:
        shutil.rmtree(root)


def read_archive(path, record, plan, *, compression, expected_manifest=None):
    if record["version"] != plan["version"] or (
        record["source_revision"] != plan["source_revision"]
    ) or record["selection"] not in plan["selections"]:
        raise ValueError("Development archive does not match its release plan")
    if path.name != record["filename"] or path.is_symlink() or not path.is_file() or path.stat().st_size != record["size"] or (
        digest(path) != record["sha256"]
    ):
        raise ValueError("Development archive digest mismatch")
    with tarfile.open(path, f"r|{compression}") as archive:
        manifest = expected_manifest
        if manifest is None:
            first = archive.next()
            if not first or first.name != "manifest.json" or not first.isfile() or first.size > 10 * 1024 * 1024 or (
                first.uid or first.gid or first.mode != 0o644 or first.mtime != plan["source_date_epoch"]
            ):
                raise ValueError("Development archive has no bounded leading manifest")
            manifest = json.load(archive.extractfile(first))
        if any(manifest.get(key) != record[key] for key in ("format", "selection", "version", "source_revision")) or (
            manifest.get("source_date_epoch") != plan["source_date_epoch"]
        ):
            raise ValueError("Development manifest differs from its release")
        expected = manifest["files"]
        if not isinstance(expected, dict) or len(expected) > MAX_FILES:
            raise ValueError("Invalid development file inventory")
        seen = set()
        total = 0
        while member := archive.next():
            name = relative_path(member.name).as_posix()
            if name in seen or name not in expected or member.uid or member.gid or (
                member.mtime != plan["source_date_epoch"] or member.mode != expected[name]["mode"]
            ):
                raise ValueError("Unindexed or mismatched development archive entry")
            seen.add(name)
            item = expected[name]
            if member.isfile() and item["type"] == "file":
                total += member.size
                if member.size > MAX_FILE_SIZE or total > MAX_TOTAL_SIZE or member.size != item["size"]:
                    raise ValueError("Development file size mismatch")
                with archive.extractfile(member) as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if checksum != item["sha256"]:
                    raise ValueError("Development file digest mismatch")
            elif member.isdir() and item["type"] == "directory":
                continue
            elif member.issym() and item["type"] == "symlink" and member.linkname == item["target"]:
                target = Path(member.linkname)
                if target.is_absolute():
                    raise ValueError("Development symlink escapes the archive")
                resolved = Path(os.path.normpath(str(Path(name).parent / target))).as_posix()
                if resolved not in expected:
                    raise ValueError("Development symlink has no archived target")
            else:
                raise ValueError("Development archive contains a special or mismatched file")
        if seen != set(expected):
            raise ValueError("Development archive is missing declared files")
    return manifest


def verify_archive(path, record, plan):
    if record["format"] != FORMAT or record["filename"] != f"claw-app-development-{record['sha256']}.tar.xz":
        raise ValueError("Development archive format or content-addressed filename is invalid")
    manifest = read_archive(path, record, plan, compression="xz")
    declared = manifest.get("native_interfaces")
    if not isinstance(declared, dict) or RETIRED_NATIVE_INTERFACES.intersection(declared):
        raise ValueError("Retired or invalid native interface exports cannot enter App fixtures")
    groups = source_closure(record["selection"])
    roots = interface_roots(groups)
    interfaces = {
        name: {**validate_interface(name, root, roots), "owner": owner}
        for name, (root, owner) in roots.items()
    }
    if manifest.get("groups") != groups or manifest.get("native_interfaces") != interfaces or (
        manifest.get("apps") != [app for group in groups if group["role"] == "selected" for app in group["apps"]]
    ) or manifest.get("purpose") != "development-and-integration-fixtures" or manifest.get("runtime_abi") != 1 or (
        manifest.get("stager") != "tools/stage.py" or manifest.get("asset_helper") != "tools/package_assets.py"
    ):
        raise ValueError("Development archive does not describe its declared fixture/interface closure")
    for name in manifest["files"]:
        relative_path(name)
        if name == "interfaces" or name.startswith("interfaces/"):
            if not interfaces or (name != "interfaces" and not any(
                name == item["path"] or name.startswith(item["path"] + "/")
                for item in interfaces.values()
            )):
                raise ValueError("Undeclared or retired interface payload cannot enter an App fixture")
        if re.match(r"^(?:products|capabilities)/[^/]+/native(?:/|$)", name) or (
            Path(name).name == "Cargo.toml" and not name.startswith("interfaces/")
        ):
            raise ValueError("Native product implementation cannot enter a fixture archive")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/development-archives")
    options = parser.parse_args()
    from release import load_plan

    plan = load_plan(options.plan)
    records = {selection: build_archive(plan, selection, options.output) for selection in plan["selections"]}
    write_json(options.output / "development.json", records)
    print(json.dumps(records, sort_keys=True))


if __name__ == "__main__":
    main()
