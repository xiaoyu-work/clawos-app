"""Fetch only pinned libraries, not another product implementation."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "platform_dependency", ROOT / "tools/platform_dependency.py"
)
platform = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(platform)


@pytest.fixture
def dependency(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git = ["git", "-C", str(upstream)]
    subprocess.run([*git, "init", "--quiet"], check=True)
    subprocess.run([*git, "config", "user.name", "Fixture"], check=True)
    subprocess.run([*git, "config", "user.email", "fixture@example.invalid"], check=True)
    libraries = ["claw-os-sdk/python/src", "cos-runtime/python/src",
                 "apps/_shared", "apps/gateway/_shared"]
    for relative in [*libraries, "apps/other-product", "apps/gateway/other-product"]:
        path = upstream / relative / "fixture.py"
        path.parent.mkdir(parents=True)
        path.write_text("VALUE = 1\n")
    (upstream / "apps/canonical_argv.py").write_text("VALUE = 1\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "--quiet", "-m", "fixture"], check=True)
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    root = tmp_path / "product"
    root.mkdir()
    lock = {"repository": str(upstream), "revision": revision,
            "python_sources": libraries[:2], "python_packages": libraries[2:]}
    (root / "platform.lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(platform, "ROOT", root)
    return root, lock


def test_only_locked_libraries_are_checked_out(dependency):
    root, lock = dependency
    paths = platform.prepare()
    cached = root / "build/platform" / lock["revision"]
    assert paths == [cached / source for source in lock["python_sources"]] + [cached / "apps"]
    assert (paths[-1] / "_shared/fixture.py").is_file()
    assert (paths[-1] / "gateway/_shared/fixture.py").is_file()
    assert (paths[-1] / "canonical_argv.py").is_file()
    assert not (cached / "apps/other-product").exists()
    assert not (cached / "apps/gateway/other-product").exists()
    assert platform.prepare() == paths


def test_changed_library_cache_is_rejected(dependency):
    paths = platform.prepare()
    (paths[-1] / "_shared/fixture.py").write_text("VALUE = 2\n")
    with pytest.raises(RuntimeError, match="modified"):
        platform.prepare()


@pytest.mark.parametrize("field,value", [
    ("revision", "main"),
    ("python_sources", ["core"]),
    ("python_packages", ["apps/email"]),
])
def test_unpinned_or_product_dependencies_are_rejected(dependency, field, value):
    root, lock = dependency
    lock[field] = value
    (root / "platform.lock.json").write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        platform.prepare()
