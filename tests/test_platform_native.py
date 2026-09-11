"""Native developer-tool smoke coverage; ordinary Python products need no Cargo."""

import hashlib
import json
import os
import subprocess
import sys

from test_platform_dependency import (
    FILES, cache, copy_development_tools, dependency, platform, public_archive,
)


def test_native_cli_uses_the_verified_local_sdk_without_unlocking_dependencies(dependency):
    copy_development_tools(dependency.root)
    files = {
        **FILES,
        "claw-os-sdk/rust/Cargo.toml": (
            b'[package]\nname="fixture-sdk"\nversion="0.0.0"\nedition="2021"\n[workspace]\n'
        ),
        "claw-os-sdk/rust/src/lib.rs": b'pub const VALUE: &str = "verified local SDK";\n',
    }
    data = public_archive(files=files, mutate=lambda manifest: manifest.update(version="0.1.0"))
    archive = dependency.root / "local-native.tar.gz"
    archive.write_bytes(data)
    selected = platform.DevelopmentArtifact(archive, "0.1.0", hashlib.sha256(data).hexdigest())
    product = dependency.root / "products/probe"
    native = product / "native"
    (native / "src").mkdir(parents=True)
    (product / "package.json").write_text(json.dumps({
        "native": {"probe": "native"}, "native_kind": "binary",
    }))
    (native / "Cargo.toml").write_text(
        '[package]\nname="development-probe"\nversion="0.0.0"\nedition="2021"\n'
        '[workspace]\n[dependencies]\nfixture-sdk={path="../../../claw-os-sdk/rust"}\n'
    )
    (native / "Cargo.lock").write_text(
        'version=4\n[[package]]\nname="development-probe"\nversion="0.0.0"\n'
        'dependencies=["fixture-sdk"]\n[[package]]\nname="fixture-sdk"\nversion="0.0.0"\n'
    )
    (native / "src/main.rs").write_text(
        'fn main() {}\n#[test]\nfn local_sdk() { assert_eq!(fixture_sdk::VALUE, "verified local SDK"); }\n'
    )
    original_lock = (native / "Cargo.lock").read_bytes()
    command = [sys.executable, "-B", str(dependency.root / "tools/native_build.py"), "probe"]
    result = subprocess.run(
        [*command, "test", *selected.arguments()], cwd=dependency.root,
        env={**os.environ, "CARGO_NET_OFFLINE": "true"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "local_sdk ... ok" in result.stdout
    assert (native / "Cargo.lock").read_bytes() == original_lock
    assert not cache(dependency).exists()
    for output in ("--app-root", "--install-root"):
        denied = subprocess.run(
            [*command, "build", "--release", output, str(dependency.root / "build/release"),
             *selected.arguments()], cwd=dependency.root, capture_output=True, text=True, timeout=15,
        )
        assert denied.returncode == 2
        assert "cannot be used for release payload or install staging" in denied.stderr
        assert not (dependency.root / "build/release").exists()
