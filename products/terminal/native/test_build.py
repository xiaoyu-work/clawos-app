"""Terminal source completeness, standalone dependency graph and private adapters."""

import json
from pathlib import Path
import tomllib

import pytest
from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-term"


def test_native_staging_preserves_every_file_and_mode(tmp_path):
    native = load_local_module(ROOT / "tools/stage_native.py", "terminal_native_stage")
    assert native.stage("terminal", tmp_path) == ["cosmic-term"]
    for path in NATIVE.rglob("*"):
        relative = path.relative_to(NATIVE)
        if path.is_file():
            assert (tmp_path / "cosmic-term" / relative).read_bytes() == path.read_bytes()
            assert (tmp_path / "cosmic-term" / relative).stat().st_mode == path.stat().st_mode
    for source, target in [
        ("apps/cosmic-term/app.json", "app.json"), ("apps/exec/main.py", "exec_backend.py"),
    ]:
        assert (tmp_path / "cosmic-term" / target).read_bytes() == (PRODUCT / source).read_bytes()


def test_standalone_keeps_original_renderer_filechooser_and_lock(tmp_path):
    native = load_local_module(ROOT / "tools/native_build.py", "terminal_native_build")
    destination = tmp_path / "terminal"
    native.prepare("terminal", tmp_path / "platform/desktop/toolkit", destination)
    cargo = tomllib.loads((destination / "Cargo.toml").read_text())
    for library in ("claw-os-sdk", "cos-runtime"):
        assert cargo["dependencies"][library]["path"] == str(tmp_path / "platform" / library / "rust")
    assert cargo["features"]["default"] == ["dbus-config", "wgpu", "wayland", "password_manager"]
    assert cargo["dependencies"]["cosmic-files"]["git"] == "https://github.com/pop-os/cosmic-files.git"
    assert cargo["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic.git"
    assert "patch" not in cargo
    assert (destination / "Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    assert "Exec=cosmic-term" in (destination / "res/com.clawos.Term.desktop").read_text()
    assert (destination / "i18n/en/cosmic_term.ftl").is_file()


def test_ui_and_mcp_do_not_invoke_apps_or_merge_process_state():
    code = "\n".join(path.read_text() for path in (NATIVE / "src").rglob("*.rs"))
    assert "cos_runtime::exec::" not in code
    assert "cos_runtime::fs::" not in code
    bridge = (NATIVE / "product_bridge.py").read_text()
    assert "backend.cmd_run" in bridge and "backend.cmd_which" in bridge
    assert "cmd_start" not in bridge and "session_id" not in bridge
    source = (NATIVE / "src/product.rs").read_text()
    assert '["-I", "-c"' in source
    assert "COS_SESSION" not in source
    assert "cos_runtime::filesystem::write" in source


@pytest.mark.parametrize(("operation", "result", "expected"), [
    ("run", {"stdout": "", "stderr": "", "exit_code": 7}, {
        "stdout": "", "stderr": "", "exit_code": 7, "timed_out": False,
    }),
    ("run", {"stdout": "partial", "stderr": "", "exit_code": -15,
             "timed_out": True, "error": "timeout"}, {
        "stdout": "partial", "stderr": "", "exit_code": -15, "timed_out": True,
    }),
    ("which", {"command": "fixture", "error": "not found"}, {
        "program": "fixture", "path": None, "found": False,
    }),
])
def test_private_adapter_preserves_nonzero_timeout_and_missing_shapes(operation, result, expected):
    import ast
    import types
    source = ast.parse((NATIVE / "product_bridge.py").read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef))
    calls = []
    def command(args):
        calls.append(args)
        return result
    scope = {"backend": types.SimpleNamespace(cmd_run=command, cmd_which=command)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<fixture>", "exec"), scope)
    assert scope["dispatch"]({
        "operation": operation,
        "arguments": {"command": "fixture", "arguments": ["--shell", "$(not-executed)"],
                      "timeout_secs": 30, "program": "fixture"},
    }) == expected
    if operation == "run":
        assert calls == [["--timeout", "30", "--", "fixture", "--shell", "$(not-executed)"]]
