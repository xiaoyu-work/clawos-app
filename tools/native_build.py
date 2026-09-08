"""Build/test the native UI against the immutable Claw OS toolkit, not upstream styling."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAGE_SPEC = importlib.util.spec_from_file_location(
    "stage_native", ROOT / "tools/stage_native.py",
)
stage_native = importlib.util.module_from_spec(STAGE_SPEC)
STAGE_SPEC.loader.exec_module(stage_native)


def prepare(product: str, toolkit: Path, destination: Path):
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    components = package["native"]
    if len(components) != 1:
        raise ValueError("Native development builds require one component per product")
    name, relative = next(iter(components.items()))
    component = (source / relative).resolve()
    if not component.is_relative_to(source.resolve()):
        raise ValueError("Native source must belong to the product")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(component, destination, symlinks=True)
    stage_native.stage_assets(source, package, name, destination)
    if package.get("native_kind") == "binary":
        manifest = destination / "Cargo.toml"
        content = manifest.read_text().replace(
            '"../../../desktop/', '"' + toolkit.parent.as_posix() + "/"
        )
        for library in ("cos-runtime", "claw-os-sdk"):
            content = content.replace(
                f'"../../../{library}/',
                '"' + (toolkit.parents[1] / library).as_posix() + "/",
            )
        manifest.write_text(content)
    else:
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
    package = json.loads((ROOT / "products" / product / "package.json").read_text())
    targets = [] if package.get("native_kind") == "binary" else ["--lib"]
    subprocess.run(
        ["cargo", options.command, "--locked", "--manifest-path", str(destination / "Cargo.toml"),
         "--target-dir", str(ROOT / "build/native-target"), *targets],
        check=True, cwd=ROOT,
    )


if __name__ == "__main__":
    main()
