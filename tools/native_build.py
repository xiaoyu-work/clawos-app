"""Build/test the native UI against the immutable Claw OS toolkit, not upstream styling."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare(product: str, toolkit: Path, destination: Path):
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    components = package["native"]
    if len(components) != 1:
        raise ValueError("Native development builds require one library per product")
    relative = next(iter(components.values()))
    component = (source / relative).resolve()
    if not component.is_relative_to(source.resolve()):
        raise ValueError("Native source must belong to the product")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(component, destination, symlinks=True)
    shutil.copy2(source / "native/Cargo.lock", destination / "Cargo.lock")
    patches = (ROOT / "tools/native-patches.toml").read_text()
    patches = patches.replace('"../toolkit', '"' + toolkit.as_posix())
    with (destination / "Cargo.toml").open("a") as manifest:
        manifest.write("\n" + patches)


def main(product=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if product is None:
        parser.add_argument("product", choices=[
            path.parent.name for path in sorted((ROOT / "products").glob("*/package.json"))
            if json.loads(path.read_text()).get("native")
        ])
    parser.add_argument("command", choices=["test", "check", "build"], default="test", nargs="?")
    options = parser.parse_args()
    product = product or options.product
    specification = importlib.util.spec_from_file_location(
        "platform_dependency", ROOT / "tools/platform_dependency.py"
    )
    platform = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(platform)
    toolkit = platform.prepare_native()
    destination = ROOT / "build" / f"{product}-native"
    prepare(product, toolkit, destination)
    subprocess.run(
        ["cargo", options.command, "--locked", "--manifest-path", str(destination / "Cargo.toml"),
         "--target-dir", str(ROOT / "build/native-target"), "--lib"],
        check=True, cwd=ROOT,
    )


if __name__ == "__main__":
    main()
