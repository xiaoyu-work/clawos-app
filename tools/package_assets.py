"""Stage product-owned installed assets alongside their declared App identities."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat


def _relative(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)*", value):
        raise ValueError("Installed asset paths must be explicit relative paths")
    path = Path(value)
    if any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Installed asset paths cannot escape their roots")
    return path


def asset_entries(source, package, installed):
    assets = package.get("installed_assets", [])
    if not isinstance(assets, list) or assets and package.get("kind", "product") != "product":
        raise ValueError("Installed assets must be explicitly declared by a product")
    declared = {"-".join(Path(path).parts[1:]) for path in package["apps"]}
    selected = set(installed)
    entries, destinations = [], []
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) != {"source", "destination", "apps"}:
            raise ValueError("Invalid installed asset declaration")
        apps = asset["apps"]
        if not isinstance(apps, list) or not apps or any(
            not isinstance(app, str) or app not in declared for app in apps
        ) or len(apps) != len(set(apps)):
            raise ValueError("Installed asset owners must be declared App identities")
        origin = source / _relative(asset["source"])
        destination = _relative(asset["destination"])
        if destination.parts[0] != "usr" or len(destination.parts) < 3:
            raise ValueError("Installed assets must use package-owned paths under usr/")
        if origin.is_symlink() or not origin.resolve().is_relative_to(source.resolve()) or not (
            origin.is_dir() or origin.is_file()
        ):
            raise ValueError("Installed asset must belong to its source product")
        if any(destination.is_relative_to(other) or other.is_relative_to(destination)
               for other in destinations):
            raise ValueError("Installed asset destinations overlap")
        destinations.append(destination)
        if selected.intersection(apps):
            entries.append((origin, destination))
    return entries


def _validate_tree(origin, ignore):
    nodes = [origin, *origin.rglob("*")] if origin.is_dir() else [origin]
    for path in nodes:
        relative = path.relative_to(origin)
        if ignore and any(ignore("", [part]) for part in relative.parts):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            resolved = path.resolve()
            if Path(os.readlink(path)).is_absolute() or not resolved.is_relative_to(origin.resolve()) or not (
                resolved.exists()
            ) or ignore and any(ignore("", [part]) for part in resolved.relative_to(origin.resolve()).parts):
                raise ValueError("Installed asset symlink escapes its payload")
        elif not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError("Installed assets cannot contain special files")


def stage_assets(source, package, destination, installed, *, ignore=None):
    entries = asset_entries(source, package, installed)
    targets = []
    for origin, relative in entries:
        target = destination / relative
        parents = [destination, *(destination / parent for parent in relative.parents)]
        if target.exists() or target.is_symlink() or any(
            parent.is_symlink() or (parent.exists() and not parent.is_dir()) for parent in parents
        ):
            raise ValueError("Conflicting staged installed asset")
        _validate_tree(origin, ignore)
        targets.append((origin, target))
    for origin, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, target, symlinks=True, ignore=ignore)
        else:
            shutil.copy2(origin, target)
    return [relative.as_posix() for _, relative in entries]


def main():
    import stage

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--kind", choices=stage.SOURCE_ROOTS, default="product")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--apps", nargs="*", help="Stage assets only for these declared App identities")
    options = parser.parse_args()
    source, package = stage.load_package(options.name, options.kind)
    apps = stage.app_entries(source, package)
    if options.apps is not None and (
        len(options.apps) != len(set(options.apps)) or set(options.apps) - set(apps)
    ):
        parser.error("asset owners must be unique declared App identities")
    installed = [app for app in apps if options.apps is None or app in options.apps]
    print(json.dumps(stage_assets(source, package, options.root, installed, ignore=stage.IGNORE)))


if __name__ == "__main__":
    main()
