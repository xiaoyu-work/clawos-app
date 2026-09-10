"""Plan and build selected App Debian releases without building an operating system."""

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from release_common import (
    ROOT, config, control_bytes, license_files, package_record, relative_path, run, version,
    work_path, write_json,
)
import stage
import platform_dependency
import native_payload as native_apps
from release_payload import validate_install_tree
from release_development import build_archive, source_closure
from release_wheels import stage_wheels


def selections(value):
    requested = value.split(",")
    if not value or any(item != item.strip() or not item for item in requested):
        raise ValueError("Select comma-separated product names, capability:<name>, support or sets")
    available = [*stage.products(), *(f"capability:{name}" for name in stage.sources("capability")),
                 "support", "sets"]
    if requested == ["all"]:
        return sorted(available)
    if len(set(requested)) != len(requested) or any(item not in available for item in requested):
        raise ValueError("Unknown or repeated release selection")
    return sorted(requested)


def source_selection(selection):
    if selection.startswith("capability:"):
        return "capability", selection.removeprefix("capability:")
    return "product", selection


def package_name(name, kind):
    return f"claw-{'cap' if kind == 'capability' else 'app'}-{name}"


def library_interface(name):
    return f"claw-app-python-{name.replace('_', '-')}-v{config()['python_library_abi']}"


def require_platform_artifact(lock=None):
    if lock is None:
        platform_dependency.read_lock()
    else:
        platform_dependency.validate_lock(lock)


def packages_for(selection):
    settings = config()
    if selection == "support":
        return [{"package": "claw-app-support", "variant": "support", "architecture": "all",
                 "selection": selection, "apps": []}]
    if selection == "sets":
        return [{"package": settings[key], "variant": variant, "architecture": "all",
                 "selection": selection, "apps": []}
                for key, variant in (("headless_set", "agent"), ("desktop_set", "desktop"))]
    kind, name = source_selection(selection)
    source, package = stage.load_package(name, kind)
    if "native_payload" in package:
        native_apps.plan(name)
    manifests = {
        app_id: json.loads((path / "app.json").read_text())
        for app_id, path in stage.app_entries(source, package).items()
    }
    if any(manifest["runtime"] not in ("python", "binary", "shell") for manifest in manifests.values()):
        raise ValueError("App runtime needs an explicit release partition")
    agent = [app_id for app_id, manifest in manifests.items() if manifest["runtime"] == "python"]
    desktop = [app_id for app_id in manifests if app_id not in agent]
    result = []
    base = package_name(name, kind)
    if agent:
        result.append({"package": base, "variant": "agent", "architecture": "all",
                       "selection": selection, "apps": agent})
    if desktop or name in settings["desktop_assets"]:
        if desktop and not package.get("native"):
            raise ValueError(f"Desktop identities have no real native build: {name}")
        architectures = settings["architectures"] if package.get("native") else ["all"]
        for architecture in architectures:
            result.append({"package": base + "-desktop", "variant": "desktop",
                           "architecture": architecture, "selection": selection, "apps": desktop})
    return result


def make_plan(selected, release_version, *, fixtures=False):
    selected = selections(selected)
    version(release_version)
    if not isinstance(fixtures, bool):
        raise ValueError("Fixture archive selection must be a boolean")
    revision = run(["git", "rev-parse", "HEAD"]).stdout.decode().strip()
    epoch = int(run(["git", "show", "-s", "--format=%ct", "HEAD"]).stdout)
    entries = [entry for selection in selected for entry in packages_for(selection)]
    jobs = [{"architecture": "all", "runner": "ubuntu-24.04",
             "toolchain": config()["rust_toolchain"]}]
    for architecture, runner in (("amd64", "ubuntu-24.04"), ("arm64", "ubuntu-24.04-arm")):
        if any(entry["architecture"] == architecture for entry in entries):
            jobs.append({"architecture": architecture, "runner": runner,
                         "toolchain": config()["rust_toolchain"]})
    return {
        "format": "claw.app-release-plan/v1", "version": release_version,
        "include_fixtures": fixtures,
        "source_revision": revision, "source_date_epoch": epoch,
        "selections": selected, "packages": entries, "matrix": {"include": jobs},
    }


def load_plan(path):
    plan = json.loads(path.read_text())
    expected = make_plan(",".join(plan["selections"]), plan["version"], fixtures=plan["include_fixtures"])
    if plan != expected:
        raise ValueError("Release plan differs from the selected source commit or package contract")
    return plan


def dependencies(entry, release_version):
    settings = config()
    selection, variant = entry["selection"], entry["variant"]
    if selection == "sets":
        other = [
            item["package"]
            for selected in selections("all") if selected not in ("support", "sets")
            for item in packages_for(selected) if item["variant"] == variant
        ]
        return sorted(set(["claw-app-support", *other] + (
            [settings["headless_set"]] if variant == "desktop" else []
        )))
    result = [settings["runtime_dependency"], "python3 (>= 3.11)"]
    if selection == "support":
        return [*result, "python3-idna (>= 3.3)", "python3-idna (<< 4)"]
    result.append(f"claw-app-support-v{settings['support_abi']}")
    kind, name = source_selection(selection)
    source, package = stage.load_package(name, kind)
    selected = set(entry["apps"])
    # Resolve the same exports as staging, but give every library one dpkg owner.
    stage.python_libraries(source, package, entry["apps"])
    for dependency in package.get("python_dependencies", []):
        if selected.intersection(dependency["apps"]):
            result.extend([
                package_name(dependency["name"], dependency["kind"]),
                library_interface(dependency["library"]),
            ])
    if variant == "desktop":
        result.extend(["claw-os-app-permissions-v1",
                       *settings["desktop_dependencies"].get(name, [])])
        if any(item["variant"] == "agent" for item in packages_for(selection)):
            result.append(f"{package_name(name, kind)} (= {release_version})")
    else:
        result.extend(settings["dependencies"].get(name, []))
    return sorted(set(result))


def write_control(root, entry, plan, extra_dependencies=()):
    settings = config()
    selection = entry["selection"]
    kind, name = source_selection(selection) if selection not in ("support", "sets") else (selection, selection)
    control = {
        "Package": entry["package"], "Version": plan["version"], "Section": "misc",
        "Priority": "optional", "Architecture": entry["architecture"],
        "Maintainer": "Claw OS Applications <noreply@github.com>",
        "Homepage": "https://github.com/xiaoyu-work/clawos-app",
        "Depends": ", ".join(sorted(set(dependencies(entry, plan["version"])) | set(extra_dependencies))),
        "X-Claw-Product": name, "X-Claw-Source-Kind": kind, "X-Claw-Variant": entry["variant"],
        "X-Claw-Runtime-ABI": "1", "X-Claw-Source-Revision": plan["source_revision"],
        "Description": f"Claw OS Applications - {name} ({entry['variant']})\n"
                       " Independently updated application payload; authority remains in Claw OS.\n"
                       " Installed App identities, grants and user data remain separate.",
    }
    if entry["apps"]:
        control["X-Claw-App-Ids"] = ", ".join(entry["apps"])
    if selection != "sets":
        former = "claw-os-desktop" if entry["variant"] == "desktop" and name != "mail" else "claw-os-agent"
        control["Breaks"] = f"{former} (<< {settings['migration_before']})"
        control["Replaces"] = control["Breaks"]
    if selection == "support":
        control["Provides"] = f"claw-app-support-v{settings['support_abi']}"
    elif selection != "sets":
        _, package = stage.load_package(name, kind)
        library = package.get("python_library")
        if library and set(library["apps"]).intersection(entry["apps"]):
            control["Provides"] = library_interface(library["name"])
    (root / "DEBIAN").mkdir()
    (root / "DEBIAN/control").write_bytes(control_bytes(control))
    write_json(root / "usr/share/clawos-app/packages" / f"{entry['package']}.json", {
        **entry, "version": plan["version"], "source_revision": plan["source_revision"],
        "runtime_abi": 1, "format": "claw.installed-app-package/v1",
    })


def licenses(root, entry):
    destination = root / "usr/share/doc" / entry["package"]
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", destination / "copyright")
    if entry["selection"] in ("support", "sets"):
        source = ROOT / "shared" if entry["selection"] == "support" else None
    else:
        kind, name = source_selection(entry["selection"])
        source, _ = stage.load_package(name, kind)
    if source and source.exists():
        # Mail's unbuilt Mozilla tree is not part of the extension release.
        roots = [source / "native"] if entry["architecture"] != "all" else [
            path for path in source.iterdir() if path.name != "native"
        ]
        for selected in roots:
            for path in license_files(selected):
                target = destination / "licenses" / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def stage_payload(root, entry):
    selection = entry["selection"]
    if selection == "support":
        stage.stage_shared(root)
        return
    if selection == "sets":
        return
    kind, name = source_selection(selection)
    source, package = stage.load_package(name, kind)
    # Mail's existing staging entrypoint builds the XPI together with mail-ai.
    installed = entry["apps"] if name != "mail" or entry["variant"] == "agent" else ["mail-ai"]
    stage.stage(name, root, installed, kind=kind)
    if name == "mail":
        if entry["variant"] == "agent":
            shutil.rmtree(root / "usr/lib/thunderbird")
        else:
            shutil.rmtree(root / "usr/lib/cos/apps")
    python = root / "usr/lib/cos/python"
    own = package.get("python_library", {})
    keep = own.get("name") if set(own.get("apps", [])).intersection(entry["apps"]) else None
    allowed = {"_shared", "gateway", "canonical_argv.py",
               *stage.python_libraries(source, package, installed)}
    if python.exists():
        for path in python.iterdir():
            if path.name == keep:
                continue
            if path.name not in allowed:
                raise ValueError(f"Unowned staged Python library: {path.name}")
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    if entry["variant"] == "desktop":
        for relative, destination in config()["desktop_assets"].get(name, {}).items():
            origin = source / relative_path(relative)
            target = root / relative_path(destination)
            shutil.copytree(origin, target, symlinks=True, ignore=stage.IGNORE)
    else:
        stage_wheels(name, root, owner=entry["package"])


def native_payload(root, entry):
    if entry["architecture"] == "all":
        return []
    kind, name = source_selection(entry["selection"])
    _, package = stage.load_package(name, kind)
    if package.get("native_kind") != "binary":
        raise ValueError(f"{name} is still a native library, not an independently installable App")
    host = run(["dpkg", "--print-architecture"]).stdout.decode().strip()
    if host != entry["architecture"]:
        raise ValueError("Native packages must be built on their declared Linux architecture")
    require_platform_artifact()
    subprocess.run([
        sys.executable, str(ROOT / "tools/native_build.py"), name, "build", "--release",
        "--target-dir", str(ROOT / "build/release-native-target"), "--install-root", str(root),
    ], check=True, cwd=ROOT)
    native_plan = native_apps.plan(name) if "native_payload" in package else None
    binary_root = root / native_plan.installed_app / "bin" if native_plan else root / "usr/bin"
    binaries = []
    for path in sorted(binary_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        native_apps.validate_elf(path, host)
        run(["strip", "--strip-unneeded", path])
        binaries.append(path)
    if not binaries:
        raise ValueError("Native installer produced no real executable")
    for manifest in (root / "usr/lib/cos/apps").rglob("app.json"):
        app = json.loads(manifest.read_text())
        if app["runtime"] == "binary":
            if native_plan is None or app["id"] != native_plan.app_id:
                raise ValueError("Native App manifest has no declared package-local payload")
            native_apps.validate_manifest_entries(manifest.parent, app, native_plan.entrypoints)
    debian = root.parent / f"{entry['package']}-shlibdeps/debian"
    debian.mkdir(parents=True)
    (debian / "control").write_text(
        f"Source: {entry['package']}\n\nPackage: {entry['package']}\nArchitecture: any\n"
    )
    try:
        result = run(["dpkg-shlibdeps", "-O", *(f"-e{binary}" for binary in binaries)], cwd=debian.parent)
        output = result.stdout.decode().strip()
        if not output.startswith("shlibs:Depends="):
            raise ValueError("Native dependency scanner did not report its runtime dependencies")
        return [value.strip() for value in output.removeprefix("shlibs:Depends=").split(",") if value.strip()]
    finally:
        shutil.rmtree(debian.parent)


def normalize(root, epoch):
    validate_install_tree(root)
    for path in [*root.rglob("*"), root]:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Package contains an escaping symlink")
        elif stat.S_ISDIR(mode):
            path.chmod(0o755)
        elif stat.S_ISREG(mode):
            path.chmod(0o755 if mode & 0o111 else 0o644)
        else:
            raise ValueError("Package contains a device or special file")
        os.utime(path, (epoch, epoch), follow_symlinks=False)


def build(plan, architecture, output):
    output = work_path(output)
    for selection in plan["selections"]:
        source_closure(selection)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in plan["packages"]:
        if entry["architecture"] != architecture:
            continue
        root = output / f".stage-{entry['package']}-{architecture}"
        root.mkdir()
        try:
            stage_payload(root, entry)
            extra = native_payload(root, entry)
            validate_install_tree(root, allow_control=False)
            licenses(root, entry)
            write_control(root, entry, plan, extra)
            normalize(root, plan["source_date_epoch"])
            artifact = output / f"{entry['package']}_{plan['version']}_{architecture}.deb"
            if artifact.exists():
                raise ValueError(f"Refusing to overwrite an existing release artifact: {artifact.name}")
            run(["dpkg-deb", "--root-owner-group", "--uniform-compression", "--threads-max=1",
                 "-Zxz", "-z9", "--build", root, artifact],
                env={"SOURCE_DATE_EPOCH": str(plan["source_date_epoch"])})
            records.append(package_record(artifact))
        finally:
            shutil.rmtree(root)
    development = {
        selection: build_archive(plan, selection, output) for selection in plan["selections"]
    } if architecture == "all" and plan["include_fixtures"] else {}
    write_json(output / f"build-record-{architecture}.json", {
        "format": "claw.app-build/v1", "plan": plan, "packages": records,
        "development": development,
        "interfaces": {},
    })
    return records


def test_selected(plan, architecture):
    if architecture == "all":
        selected = [item for item in plan["selections"] if item not in ("support", "sets")]
        products = [item for item in selected if not item.startswith("capability:")]
        capabilities = [item.removeprefix("capability:") for item in selected if item.startswith("capability:")]
        if selected:
            require_platform_artifact()
            arguments = [sys.executable, "tools/test.py", *products]
            if capabilities:
                arguments.extend(["--capability", *capabilities])
            subprocess.run(arguments, check=True, cwd=ROOT)
        elif "support" in plan["selections"]:
            require_platform_artifact()
            subprocess.run([sys.executable, "tools/test.py", "--shared"], check=True, cwd=ROOT)
    else:
        require_platform_artifact()
        for selection in sorted({
            entry["selection"] for entry in plan["packages"] if entry["architecture"] == architecture
        }):
            subprocess.run([sys.executable, "tools/native_build.py", selection, "test"], check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--select", required=True)
    planning.add_argument("--version", required=True)
    planning.add_argument("--fixtures", action="store_true",
                          help="Also publish optional complete source/staging fixture archives")
    planning.add_argument("--output", type=Path, default=ROOT / "build/release-plan.json")
    for command in ("build", "test"):
        action = commands.add_parser(command)
        action.add_argument("--plan", type=Path, required=True)
        action.add_argument("--architecture", choices=["all", "amd64", "arm64"], required=True)
        if command == "build":
            action.add_argument("--output", type=Path, default=ROOT / "build/release")
    options = parser.parse_args()
    if options.command == "plan":
        plan = make_plan(options.select, options.version, fixtures=options.fixtures)
        write_json(work_path(options.output), plan)
        print(json.dumps(plan["matrix"], separators=(",", ":")))
    else:
        plan = load_plan(options.plan)
        if options.command == "build":
            build(plan, options.architecture, options.output)
        else:
            test_selected(plan, options.architecture)


if __name__ == "__main__":
    main()
