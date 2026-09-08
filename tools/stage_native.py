"""Copy product-owned native build inputs, never OS implementation."""

import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def stage(product: str, destination: Path) -> list[str]:
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    installed = []
    for name, relative in package.get("native", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ValueError("Invalid native component name")
        component = source / relative
        if not component.resolve().is_relative_to(source.resolve()):
            raise ValueError("Native source must belong to the product")
        shutil.copytree(component, destination / name, symlinks=True,
                        ignore=shutil.ignore_patterns("target", "__pycache__", ".pytest_cache"))
        shutil.copy2(source / "native/LICENSE", destination / name / "LICENSE")
        installed.append(name)
    return installed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.product, args.root)))
