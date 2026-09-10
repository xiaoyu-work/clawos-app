"""The common App payload has one import root and exact package ownership."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_support import load_local_module


ROOT = Path(__file__).resolve().parents[2]
stage = load_local_module(ROOT / "tools/stage.py", "shared_library_stage")


@pytest.fixture
def source(tmp_path, monkeypatch):
    repository = tmp_path / "checkout"
    shared = repository / "shared/python"
    shutil.copytree(ROOT / "shared/python", shared, ignore=stage.IGNORE)
    monkeypatch.setattr(stage, "ROOT", repository)
    return repository, shared


def test_shared_stages_exact_app_libraries_once_without_platform_or_apps(source, tmp_path):
    _, shared = source
    root = tmp_path / "installed"
    python = stage.stage_shared(root)
    assert python == root / "usr/lib/cos/python"
    assert {path.name for path in python.iterdir()} == set(stage.SHARED_LIBRARIES)
    before = {}
    for name in stage.SHARED_LIBRARIES:
        assert stage._library_tree(python / name) == stage._library_tree(shared / name)
        before[name] = (python / name).stat().st_ino
    assert stage.stage_shared(root) == python
    assert {name: (python / name).stat().st_ino for name in before} == before
    assert not (root / "usr/lib/cos/apps").exists()
    assert not (python / "claw_os_sdk").exists()
    assert not (python / "cos_runtime").exists()
    assert not (root / "var").exists()


@pytest.mark.parametrize("relative", [
    "_shared/test_helper.py", "_shared/helper_test.py", "_shared/conftest.py",
    "_shared/helper.pyc", "_shared/helper.pyo", "_shared/__pycache__/helper.pyc",
    "_shared/tests/fixture.json", "gateway/_shared/test/fixture.py",
    "gateway/_shared/.pytest_cache/state",
])
def test_shared_excludes_tests_and_bytecode(source, tmp_path, relative):
    _, shared = source
    excluded = shared / relative
    excluded.parent.mkdir(parents=True, exist_ok=True)
    excluded.write_text("must not ship")
    python = stage.stage_shared(tmp_path / "installed")
    assert not (python / relative).exists()
    assert stage.stage_shared(tmp_path / "installed") == python


@pytest.mark.parametrize("missing", [
    "_shared", "_shared/__init__.py", "gateway", "gateway/_shared",
    "gateway/_shared/__init__.py", "canonical_argv.py",
])
def test_shared_missing_sources_fail_before_writing_any_payload(source, tmp_path, missing):
    _, shared = source
    path = shared / missing
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    destination = tmp_path / "installed"
    with pytest.raises(ValueError, match="App shared Python"):
        stage.stage_shared(destination)
    assert not destination.exists()


@pytest.mark.parametrize("change", ["content", "mode", "extra", "bytecode", "test", "symlink"])
def test_shared_conflicts_are_not_merged_or_overwritten(source, tmp_path, change):
    root = tmp_path / "installed"
    python = stage.stage_shared(root)
    path = python / "gateway/_shared/atomic.py"
    if change == "content":
        path.write_text("conflicting library")
    elif change == "mode":
        path.chmod(0o755)
    elif change == "extra":
        (path.parent / "extra.py").write_text("unexpected")
    elif change == "bytecode":
        (path.parent / "atomic.pyc").write_text("unexpected")
    elif change == "test":
        (path.parent / "test_atomic.py").write_text("unexpected")
    else:
        path.unlink()
        path.symlink_to("missing.py")
    before = stage._library_tree(python)
    with pytest.raises(ValueError, match="Conflicting staged Python library"):
        stage.stage_shared(root)
    assert stage._library_tree(python) == before


def test_shared_module_conflict_is_preflighted_before_any_package_copy(source, tmp_path):
    python = tmp_path / "installed/usr/lib/cos/python"
    python.mkdir(parents=True)
    (python / "canonical_argv.py").write_text("conflicting module")
    with pytest.raises(ValueError, match="canonical_argv"):
        stage.stage_shared(tmp_path / "installed")
    assert sorted(path.name for path in python.iterdir()) == ["canonical_argv.py"]
    assert (python / "canonical_argv.py").read_text() == "conflicting module"


def test_shared_never_follows_a_destination_symlink(source, tmp_path):
    outside = tmp_path / "unrelated"
    outside.mkdir()
    root = tmp_path / "installed"
    root.mkdir()
    (root / "usr").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Conflicting staged Python library"):
        stage.stage_shared(root)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("name", ["_shared", "gateway", "canonical_argv"])
def test_product_library_cannot_claim_a_common_namespace(tmp_path, name):
    with pytest.raises(ValueError, match="owned by shared/python"):
        stage._library_export(tmp_path, {"name": name, "path": f"python/{name}", "apps": ["fixture"]})


def test_shared_cli_and_isolated_imports_need_no_sibling_os_checkout(source, tmp_path):
    repository, _ = source
    tools = repository / "tools"
    tools.mkdir()
    shutil.copy2(ROOT / "tools/stage.py", tools / "stage.py")
    root = tmp_path / "installed"
    assert not (repository.parent / "claw-os").exists()
    assert not (repository / "apps").exists()
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(tools / "stage.py"), "--shared", "--root", str(root)],
        cwd=repository, env={"PATH": os.defpath}, capture_output=True, text=True,
        check=True, timeout=20,
    )
    python = Path(json.loads(result.stdout))
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         "import json, sys; "
         f"sys.path.insert(0, {str(python)!r}); "
         "import _shared.atomic, gateway._shared.gateway_args, canonical_argv; "
         "print(json.dumps({"
         "'modules': [_shared.atomic.__file__, gateway._shared.gateway_args.__file__, "
         "canonical_argv.__file__], "
         "'args': canonical_argv.parse_canonical_argv(['--label=--urgent', '--', '--literal'], "
         "value_flags=['label'])}))"],
        cwd=root, env={"PATH": os.defpath}, capture_output=True, text=True,
        check=True, timeout=20,
    )
    payload = json.loads(result.stdout)
    assert all(Path(path).is_relative_to(python) for path in payload["modules"])
    assert payload["args"] == [["--literal"], {"label": "--urgent"}]
    assert not (root / "usr/lib/cos/apps").exists()
    assert not list(root.rglob("*.pyc"))
