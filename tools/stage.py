"""Stage product-owned assets into an otherwise empty installation root."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]


def products() -> list[str]:
    return sorted(path.parent.name for path in (ROOT / "products").glob("*/package.json"))


def stage(product: str, destination: Path) -> list[str]:
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    installed = []
    for relative in package["apps"]:
        layout = Path(relative).relative_to("apps")
        if not layout.parts or any(
            not re.fullmatch(r"[a-z][a-z0-9-]*", part) for part in layout.parts
        ):
            raise ValueError("Invalid installed App layout")
        app = source / relative
        manifest = json.loads((app / "app.json").read_text())
        app_id = manifest["id"]
        if app_id != "-".join(layout.parts):
            raise ValueError("Installed App identity does not match its layout")
        target = destination / "usr/lib/cos/apps" / layout
        shutil.copytree(app, target, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", ".pytest_cache"))
        installed.append(app_id)
    extension = package.get("extension")
    if extension:
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
    parser.add_argument("product", choices=products())
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.product, args.root)))
