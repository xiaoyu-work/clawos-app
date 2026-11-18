"""Build/test native products with their locked library and toolkit boundaries."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
from platform import machine
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE_SPEC = importlib.util.spec_from_file_location(
    "stage_native", ROOT / "tools/stage_native.py",
)
stage_native = importlib.util.module_from_spec(STAGE_SPEC)
STAGE_SPEC.loader.exec_module(stage_native)


def build_system(package):
    system = package.get("native_build_system", "cargo")
    if system not in ("cargo", "cmake"):
        raise ValueError("Native build system must be cargo or cmake")
    return system


def prepare(product: str, toolkit: Path | None, destination: Path):
    source = ROOT / "products" / product
    package = json.loads((source / "package.json").read_text())
    stage_native.library_paths(source, package)
    components = package["native"]
    if len(components) != 1:
        raise ValueError("Native development builds require one component per product")
    name, relative = next(iter(components.items()))
    component = (source / relative).resolve()
    if not component.is_relative_to(source.resolve()):
        raise ValueError("Native source must belong to the product")
    if build_system(package) == "cmake":
        if package.get("native_kind") != "binary" or not (component / "CMakeLists.txt").is_file():
            raise ValueError("CMake native products require a binary and CMakeLists.txt")
        if package.get("native_assets"):
            raise ValueError("CMake products must stage their assets through their own installer")
        return component
    if toolkit is None:
        raise ValueError("Cargo native products require the verified toolkit")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(component, destination, symlinks=True)
    stage_native.stage_assets(source, package, name, destination)
    if package.get("native_kind") == "binary":
        for manifest in destination.rglob("Cargo.toml"):
            depth = len(manifest.relative_to(destination).parts) - 1
            prefix = "../" * (3 + depth)
            content = manifest.read_text().replace(
                f'"{prefix}desktop/', '"' + toolkit.parent.as_posix() + "/"
            )
            for library in ("cos-runtime", "claw-os-sdk"):
                content = content.replace(
                    f'"{prefix}{library}/',
                    '"' + (toolkit.parents[1] / library).as_posix() + "/",
                )
            shared_prefix = "../" * (4 + depth)
            content = content.replace(
                f'"{shared_prefix}shared/rust/gui-argv"',
                '"' + (ROOT / "shared/rust/gui-argv").as_posix() + '"',
            )
            manifest.write_text(content)
    else:
        shutil.copy2(source / "native/Cargo.lock", destination / "Cargo.lock")
        patches = (ROOT / "tools/native-patches.toml").read_text()
        patches = patches.replace('"../toolkit', '"' + toolkit.as_posix())
        with (destination / "Cargo.toml").open("a") as manifest:
            manifest.write("\n" + patches)
    return destination


def run_installer(package, prepared, output, environment):
    if build_system(package) == "cmake":
        subprocess.run(
            ["cmake", "--install", str(prepared), "--prefix", "/usr"],
            check=True, cwd=ROOT, env={**environment, "DESTDIR": str(output)},
        )
    else:
        subprocess.run(
            ["just", "--justfile", str(prepared / "justfile"),
             f"rootdir={output}", "prefix=/usr", "install"],
            check=True, cwd=prepared, env=environment,
        )


def install_payload(product, package, prepared, output, environment, *, app_only=False):
    if "native_payload" not in package:
        if app_only:
            raise ValueError("App-only native preparation requires a native_payload declaration")
        run_installer(package, prepared, output, environment)
        return
    import native_payload

    selected = native_payload.plan(product)
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine())
    if architecture is None:
        raise ValueError("Native payload installation requires an amd64 or arm64 Linux host")
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{product}-installer-", dir=ROOT / "build") as temporary:
        installed = Path(temporary)
        run_installer(package, prepared, installed, environment)
        if app_only:
            result = native_payload.prepare(selected, installed, output, architecture)
            print(json.dumps({**selected.record(), "root": str(result.root)}))
        else:
            native_payload.install(selected, installed, output, architecture)


def main(product=None):
    specification = importlib.util.spec_from_file_location(
        "platform_dependency", ROOT / "tools/platform_dependency.py"
    )
    platform = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(platform)
    parser = argparse.ArgumentParser(description=__doc__)
    if product is None:
        parser.add_argument("product", choices=[
            path.parent.name for path in sorted((ROOT / "products").glob("*/package.json"))
            if json.loads(path.read_text()).get("native")
        ])
    parser.add_argument("command", choices=["test", "check", "build"], default="test", nargs="?")
    parser.add_argument("--release", action="store_true", help="Use Cargo's real release profile")
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--install-root", type=Path,
                        help="Stage a release App payload and common-Host compatibility launchers")
    parser.add_argument("--app-root", type=Path,
                        help="Prepare a release App directory for the existing provenance signer")
    platform.add_development_arguments(parser)
    options = parser.parse_args()
    try:
        development = platform.development_from_args(options)
    except ValueError as error:
        parser.error(str(error))
    if development is not None and (options.install_root or options.app_root):
        parser.error("A local development platform cannot be used for release payload or install staging")
    if options.install_root and (options.command != "build" or not options.release):
        parser.error("--install-root requires build --release")
    if options.app_root and (options.command != "build" or not options.release):
        parser.error("--app-root requires build --release")
    if options.install_root and options.app_root:
        parser.error("--install-root and --app-root are separate staging outputs")
    product = product or options.product
    package = json.loads((ROOT / "products" / product / "package.json").read_text())
    system = build_system(package)
    if system == "cmake" and options.command == "test":
        parser.error("This CMake product has no test target; use build or check")
    if system == "cmake" and development is not None:
        parser.error("This CMake product does not consume the native Rust toolkit")
    output = options.install_root or options.app_root
    if output:
        if package.get("native_kind") != "binary":
            raise ValueError("A native library is not a runnable release payload")
        install_root = output.resolve()
        if install_root == ROOT / "build" or not install_root.is_relative_to(ROOT / "build"):
            raise ValueError("Native install root must be an explicit directory under build/")
    platform.report_development(development)
    if system == "cargo":
        toolkit = platform.prepare_native(development=development)
    else:
        platform.read_lock()
        toolkit = None
    destination = ROOT / "build" / f"{product}-native"
    prepared = prepare(product, toolkit, destination)
    targets = [] if package.get("native_kind") == "binary" else ["--lib"]
    arguments = ["--", "--test-threads=1"] if options.command == "test" else []
    profile = ["--release"] if options.release else []
    default_target = "native-target" if system == "cargo" else f"{product}-cmake"
    target_dir = (options.target_dir or ROOT / "build" / default_target).resolve()
    environment = dict(os.environ)
    environment["CARGO_TARGET_DIR"] = str(target_dir)
    environment["CLAW_NATIVE_DESKTOP_METADATA"] = str(ROOT / "tools/native_desktop_metadata.py")
    if output:
        # Build-time resource paths must describe the installed system, not staging.
        environment["INSTALL_DIR"] = "/usr/share"
    if system == "cmake":
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
        subprocess.run(
            ["cmake", "-S", str(prepared), "-B", str(target_dir), "-G", "Ninja",
             f"-DCMAKE_BUILD_TYPE={'Release' if options.release else 'Debug'}",
             f"-DGIT_REVISION={revision}", "-DBUILD_TESTING=OFF"],
            check=True, cwd=ROOT, env=environment,
        )
        subprocess.run(
            ["cmake", "--build", str(target_dir), "--parallel", "3"],
            check=True, cwd=ROOT, env=environment,
        )
        if output:
            install_payload(product, package, target_dir, install_root, environment,
                            app_only=bool(options.app_root))
        return
    # Match workspaces whose upstream justfile builds binaries separately:
    # combining packages would incorrectly unify renderer/applet features.
    for member in package.get("native_packages", [None]):
        selection = ["--package", member] if member else []
        subprocess.run(
            ["cargo", options.command, "--locked", "--manifest-path", str(destination / "Cargo.toml"),
             "--target-dir", str(target_dir), *profile, *targets, *selection, *arguments],
            check=True, cwd=ROOT, env=environment,
        )
    if options.command == "build" and not options.release:
        for example in package.get("native_examples", []):
            subprocess.run(
                ["cargo", "build", "--locked", "--manifest-path", str(destination / "Cargo.toml"),
                 "--target-dir", str(target_dir), "--example", example],
                check=True, cwd=ROOT,
            )
    if output:
        install_payload(product, package, destination, install_root, environment,
                        app_only=bool(options.app_root))


if __name__ == "__main__":
    main()
