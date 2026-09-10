"""Stage explicitly kinded App sources and their declared shared libraries."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = {"product": "products", "capability": "capabilities"}
PACKAGE_KINDS = {"product": "product", "capability": "shared-capability-client"}
SHARED_LIBRARIES = ("_shared", "gateway", "canonical_argv.py")
IGNORE = shutil.ignore_patterns(
    "__pycache__", ".pytest_cache", "test", "tests", "conftest.py",
    "test_*.py", "*_test.py", "*.pyc", "*.pyo",
)


def shared_python_root(repository: Path | None = None) -> Path:
    """Resolve the App-owned common import root without any OS source fallback."""
    repository = ROOT if repository is None else repository
    root = repository / "shared/python"
    packages = [root / "_shared", root / "gateway", root / "gateway/_shared"]
    if (
        root.is_symlink()
        or not root.is_dir()
        or not root.resolve().is_relative_to(repository.resolve())
        or any(
            path.is_symlink() or not path.is_dir()
            or (path / "__init__.py").is_symlink()
            or not (path / "__init__.py").is_file()
            for path in packages
        )
        or (root / "canonical_argv.py").is_symlink()
        or not (root / "canonical_argv.py").is_file()
    ):
        raise ValueError("Missing or invalid App shared Python libraries under shared/python")
    return root


def sources(kind: str = "product") -> list[str]:
    if not isinstance(kind, str) or kind not in SOURCE_ROOTS:
        raise ValueError("Unknown App source kind")
    groups = {
        key: {path.parent.name for path in (ROOT / directory).glob("*/package.json")}
        for key, directory in SOURCE_ROOTS.items()
    }
    names = [name for values in groups.values() for name in values]
    if any(not re.fullmatch(r"[a-z][a-z0-9-]*", name) for name in names):
        raise ValueError("Invalid App source name")
    if len(names) != len(set(names)):
        raise ValueError("Duplicate App source name across kinds")
    return sorted(groups[kind])


def products() -> list[str]:
    return sources("product")


def load_package(name: str, kind: str = "product") -> tuple[Path, dict]:
    if name not in sources(kind):
        raise ValueError(f"Unknown {kind} source package: {name}")
    source = ROOT / SOURCE_ROOTS[kind] / name
    if not source.resolve().is_relative_to((ROOT / SOURCE_ROOTS[kind]).resolve()):
        raise ValueError("App source must belong to its declared kind")
    package = json.loads((source / "package.json").read_text())
    if not isinstance(package, dict) or package.get("kind", "product") != PACKAGE_KINDS[kind]:
        raise ValueError("Package kind does not match its declared source kind")
    if kind == "capability" and any(
        key.startswith("native") or key == "extension" for key in package
    ):
        raise ValueError("Shared capability clients cannot declare native product assets")
    return source, package


def app_entries(source: Path, package: dict) -> dict[str, Path]:
    paths = package["apps"]
    if not isinstance(paths, list) or not paths:
        raise ValueError("Source package requires an explicit App list")
    entries = {}
    for relative in paths:
        if not isinstance(relative, str) or not re.fullmatch(
            r"apps/[a-z][a-z0-9-]*(/[a-z][a-z0-9-]*)*", relative
        ):
            raise ValueError("Invalid installed App layout")
        layout = Path(relative).relative_to("apps")
        app = source / relative
        if not app.resolve().is_relative_to(source.resolve()):
            raise ValueError("Installed App layout escapes its source package")
        manifest = json.loads((app / "app.json").read_text())
        app_id = manifest["id"]
        if app_id != "-".join(layout.parts):
            raise ValueError("Installed App identity does not match its layout")
        if app_id in entries:
            raise ValueError("Duplicate installed App identity")
        entries[app_id] = app
    return entries


def _library_export(source: Path, library: dict) -> Path:
    if not isinstance(library, dict) or set(library) != {"name", "path", "apps"}:
        raise ValueError("Invalid Python library export")
    name, relative = library["name"], library["path"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError("Invalid Python library name")
    if name in {Path(entry).stem for entry in SHARED_LIBRARIES}:
        raise ValueError("Common Python library names are owned by shared/python")
    if not isinstance(relative, str) or not re.fullmatch(r"python/[a-z_][a-z0-9_]*", relative):
        raise ValueError("Python library must be an explicit package under python/")
    path = source / relative
    if path.name != name or path.is_symlink() or not path.resolve().is_relative_to(source.resolve()) or not (
        path / "__init__.py"
    ).is_file():
        raise ValueError("Python library must belong to its declaring source package")
    return path


def _library_apps(values, declared: set[str]) -> set[str]:
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or value not in declared for value in values
    ) or len(values) != len(set(values)):
        raise ValueError("Python library consumers must be declared App identities")
    return set(values)


def python_libraries(source: Path, package: dict, installed: list[str]) -> dict[str, Path]:
    declared = set(app_entries(source, package))
    selected = set(installed)
    libraries = {}
    library = package.get("python_library")
    if library is not None:
        path = _library_export(source, library)
        if _library_apps(library["apps"], declared) & selected:
            libraries[path.name] = path
    dependencies = package.get("python_dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError("Python dependencies must be explicitly declared")
    seen = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"kind", "name", "library", "apps"}:
            raise ValueError("Invalid Python library dependency")
        owner, exported = load_package(dependency["name"], dependency["kind"])
        path = _library_export(owner, exported.get("python_library"))
        _library_apps(exported["python_library"]["apps"], set(app_entries(owner, exported)))
        if dependency["library"] != path.name or path in seen:
            raise ValueError("Missing or duplicate Python library dependency")
        seen.add(path)
        if _library_apps(dependency["apps"], declared) & selected:
            if path.name in libraries and libraries[path.name] != path:
                raise ValueError("Conflicting Python library exports")
            libraries[path.name] = path
    return libraries


def _library_tree(root: Path, *, payload: bool = False) -> dict:
    entries = {}
    for path in [root, *sorted(root.rglob("*"))]:
        relative = path.relative_to(root)
        if payload and any(IGNORE("", [part]) for part in relative.parts):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            value = ("symlink", os.readlink(path))
        elif stat.S_ISREG(mode):
            value = ("file", stat.S_IMODE(mode), path.read_bytes())
        elif stat.S_ISDIR(mode):
            value = ("directory", stat.S_IMODE(mode))
        else:
            raise ValueError("Unsupported Python library entry")
        entries[relative] = value
    return entries


def _library_target(path: Path, destination: Path) -> Path:
    target = destination / "usr/lib/cos/python" / path.name
    parents = [destination, *(destination / part for part in (
        "usr", "usr/lib", "usr/lib/cos", "usr/lib/cos/python",
    ))]
    expected = _library_tree(path, payload=True)
    if (
        any(parent.is_symlink() or (parent.exists() and not parent.is_dir()) for parent in parents)
        or target.is_symlink()
        or (target.exists() and expected != _library_tree(target))
    ):
        raise ValueError(f"Conflicting staged Python library: {path.name}")
    return target


def stage_library(path: Path, destination: Path):
    target = _library_target(path, destination)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target, symlinks=True, ignore=IGNORE)
        else:
            shutil.copy2(path, target)


def stage_shared(destination: Path) -> Path:
    """Stage only App support, separately owned from product and OS packages."""
    source = shared_python_root()
    libraries = [source / name for name in SHARED_LIBRARIES]
    for path in libraries:
        _library_target(path, destination)
    for path in libraries:
        stage_library(path, destination)
    return destination / "usr/lib/cos/python"


def stage(product: str, destination: Path, app_ids: list[str] | None = None,
          *, kind: str = "product") -> list[str]:
    source, package = load_package(product, kind)
    apps = app_entries(source, package)
    installed = [app_id for app_id in apps if app_ids is None or app_id in app_ids]
    libraries = python_libraries(source, package, installed)
    for path in libraries.values():
        _library_target(path, destination)
    if "installed_assets" in package:
        specification = importlib.util.spec_from_file_location(
            "product_installed_assets", Path(__file__).with_name("package_assets.py"),
        )
        asset_stager = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(asset_stager)
        asset_stager.stage_assets(source, package, destination, installed, ignore=IGNORE)
    for path in libraries.values():
        stage_library(path, destination)
    for app_id in installed:
        app = apps[app_id]
        target = destination / "usr/lib/cos/apps" / app.relative_to(source / "apps")
        shutil.copytree(app, target, symlinks=True, ignore=IGNORE)
    extension = package.get("extension")
    if extension and "mail-ai" in installed:
        specification = importlib.util.spec_from_file_location(
            "product_extension_builder", source / "build-extension.py"
        )
        builder = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(builder)
        extension_source = source / extension
        extension_manifest = json.loads((extension_source / "manifest.json").read_text())
        app_manifest = json.loads((source / package["apps"][0] / "app.json").read_text())
        if extension_manifest["version"] != app_manifest["version"]:
            raise ValueError("Mail App and extension versions must match")
        target = destination / "usr/lib/thunderbird/distribution/extensions"
        builder.build_extension(extension_source, target / f"{builder.EXTENSION_ID}.xpi")
    return installed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", nargs="?")
    parser.add_argument("--shared", action="store_true", help="Stage the App-owned common runtime")
    parser.add_argument("--kind", choices=SOURCE_ROOTS, default="product")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--apps", nargs="*", help="Stage only these installed identities")
    args = parser.parse_args()
    if bool(args.product) == args.shared:
        parser.error("select one source package or --shared")
    if args.shared:
        if args.apps is not None or args.kind != "product":
            parser.error("--shared cannot select App identities or a source kind")
        print(json.dumps(str(stage_shared(args.root))))
    else:
        print(json.dumps(stage(args.product, args.root, args.apps, kind=args.kind)))
