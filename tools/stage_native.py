"""Copy product-owned native build inputs, never OS implementation."""

import argparse
import json
from pathlib import Path
import re
import shutil
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def library_paths(source: Path, package: dict) -> dict[str, Path]:
    exports = package.get("native_libraries", {})
    if not isinstance(exports, dict):
        raise ValueError("Native libraries must be explicitly declared")
    result = {}
    for name, export in exports.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or not isinstance(export, dict) or set(export) != {"component", "path"}:
            raise ValueError("Invalid native library declaration")
        component, relative = export["component"], export["path"]
        if not isinstance(component, str) or component not in package.get("native", {}) or not isinstance(relative, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*", relative
        ):
            raise ValueError("Native library must belong to a declared component")
        root = (source / package["native"][component]).resolve()
        library = (root / relative).resolve()
        if not root.is_relative_to(source.resolve()) or not library.is_relative_to(root):
            raise ValueError("Native library must belong to its product component")
        manifest = tomllib.loads((library / "Cargo.toml").read_text())
        if manifest.get("package", {}).get("name") != name:
            raise ValueError("Native library identity does not match its manifest")
        result[name] = Path(component) / relative
    return result


def stage_assets(source: Path, package: dict, name: str, destination: Path):
    for target, relative in package.get("native_assets", {}).get(name, {}).items():
        asset = source / relative
        output = destination / target
        if not asset.resolve().is_relative_to(source.resolve()) or not (
            output.resolve().is_relative_to(destination.resolve())
        ):
            raise ValueError("Native asset must belong to the product and destination")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, output)


def stage(product: str, destination: Path) -> list[str]:
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    library_paths(source, package)
    installed = []
    for name, relative in sorted(package.get("native", {}).items()):
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ValueError("Invalid native component name")
        component = source / relative
        if not component.resolve().is_relative_to(source.resolve()):
            raise ValueError("Native source must belong to the product")
        shutil.copytree(component, destination / name, symlinks=True,
                        ignore=shutil.ignore_patterns("target", "__pycache__", ".pytest_cache"))
        shutil.copy2(source / "native/LICENSE", destination / name / "LICENSE")
        stage_assets(source, package, name, destination / name)
        installed.append(name)
    return installed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.product, args.root)))
