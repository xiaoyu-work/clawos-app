"""Complete standalone Store inputs and private library contracts."""

import ast
import json
from pathlib import Path
import tomllib
import types
import pytest
from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-store"


def test_native_staging_preserves_all_files_and_modes(tmp_path):
    stage = load_local_module(ROOT / "tools/stage_native.py", "store_stage_native")
    assert stage.stage("store", tmp_path) == ["cosmic-store"]
    for path in NATIVE.rglob("*"):
        if path.is_file():
            output = tmp_path / "cosmic-store" / path.relative_to(NATIVE)
            assert output.read_bytes() == path.read_bytes()
            assert output.stat().st_mode == path.stat().st_mode
    assert (tmp_path / "cosmic-store/catalog_backend.py").read_bytes() == (PRODUCT / "apps/pkg/main.py").read_bytes()


def test_original_default_graph_and_nested_workspace(tmp_path):
    native = load_local_module(ROOT / "tools/native_build.py", "store_native_build")
    output = tmp_path / "store"
    native.prepare("store", tmp_path / "platform/desktop/toolkit", output)
    cargo = tomllib.loads((output / "Cargo.toml").read_text())
    assert cargo["workspace"]["members"] == ["flathub-stats"]
    assert (output / "flathub-stats/src/main.rs").is_file()
    assert cargo["features"]["default"] == [
        "dbus-config", "desktop-systemd-scope", "flatpak", "logind", "notify",
        "packagekit", "single-instance", "wgpu", "wayland", "xdg-portal",
    ]
    assert cargo["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic.git"
    assert "patch" not in cargo
    for library in ("claw-os-sdk", "cos-runtime"):
        assert cargo["dependencies"][library]["path"] == str(tmp_path / "platform" / library / "rust")
    assert (output / "Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    assert (output / "res/icons/hicolor/scalable/apps/com.clawos.Store.svg").is_file()


@pytest.mark.parametrize(("operation", "args", "expected"), [
    ("search", {"query": "--limit", "limit": 2}, ["--limit", "2", "--", "--limit"]),
    ("installed", {}, []), ("show", {"name": "curl:amd64"}, ["curl:amd64"]),
])
def test_native_queries_use_canonical_catalog_without_app_entrypoint(operation, args, expected):
    calls = []
    def query(values):
        calls.append(values)
        return {"fixture": True}
    backend = types.SimpleNamespace(cmd_search=query, cmd_list=query, cmd_show=query)
    source = ast.parse((NATIVE / "product_bridge.py").read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef))
    scope = {"backend": backend}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<bridge>", "exec"), scope)
    assert scope["dispatch"]({"operation": operation, "arguments": args}) == {"fixture": True}
    assert calls == [expected]
    for mutation in ("install", "need", "remove", "upgrade", "run"):
        with pytest.raises(ValueError, match="unknown private"):
            scope["dispatch"]({"operation": mutation, "arguments": {}})


def test_human_data_mutations_fail_closed_inside_mcp(monkeypatch):
    import os
    source = ast.parse((NATIVE / "product_bridge.py").read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef))
    scope = {"os": os}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<bridge>", "exec"), scope)
    monkeypatch.setenv("COS_MCP_SERVER", "1")
    with pytest.raises(ValueError, match="unavailable in MCP"):
        scope["dispatch"]({"operation": "remove_data", "arguments": {"path": "/not-accessed"}})


def test_human_data_cleanup_checks_delete_and_snapshots_before_removal(tmp_path, monkeypatch):
    import os
    import shutil
    import stat
    monkeypatch.delenv("COS_MCP_SERVER", raising=False)
    monkeypatch.setenv("COS_SESSION", "authenticated-human-session")
    path = tmp_path / "app-data"
    path.mkdir()
    (path / "content").write_text("synthetic user data")
    events = []
    def require(verb, **scope):
        events.append((verb, scope))
        assert path.exists()
    def snapshot(name, operation, **context):
        events.append((operation, context))
        assert path.exists() and (path / "content").read_text() == "synthetic user data"
    source = ast.parse((NATIVE / "product_bridge.py").read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef))
    scope = {
        "os": os, "shutil": shutil, "stat": stat,
        "policy": types.SimpleNamespace(require=require),
        "snapshot": types.SimpleNamespace(snapshot=snapshot),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<bridge>", "exec"), scope)
    request = {"operation": "remove_data", "arguments": {"path": str(path)}}
    assert scope["dispatch"](request) == {"removed": str(path)}
    assert not path.exists()
    assert events == [
        ("fs.delete", {"path": str(path)}),
        ("rm", {"session_id": "authenticated-human-session"}),
    ]
    path.mkdir()
    def denied(*args, **kwargs):
        raise PermissionError("denied")
    scope["policy"].require = denied
    with pytest.raises(PermissionError):
        scope["dispatch"](request)
    assert path.exists()
    scope["policy"].require = require
    scope["snapshot"].snapshot = denied
    with pytest.raises(PermissionError):
        scope["dispatch"](request)
    assert path.exists()
