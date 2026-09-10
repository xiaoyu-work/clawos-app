"""App-owned module loading and public MCP stdio contract fixtures."""

from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile

import pytest


def authenticated_mcp_params(params, *, call_id="test-call"):
    """Attach the same broker-owned context used by OS App contract fixtures."""
    value = dict(params or {})
    meta = dict(value.get("_meta", {}))
    meta["claw-os.dev/call-context"] = {
        "wire_version": 1,
        "call_id": call_id,
        "trace_id": "test-trace",
        "session_id": "test-session",
        "task_id": "test-task",
        "caller": {
            "kind": "system-agent",
            "id": "test-agent-session",
            "owner_uid": 1000,
        },
    }
    value["_meta"] = meta
    return value


@contextmanager
def mcp_process(app_dir, *, env):
    """Run a Python App through its declared entrypoint and public MCP wire."""
    app_dir = Path(app_dir).resolve()
    manifest = json.loads((app_dir / "app.json").read_text())
    assert manifest["runtime"] == "python"
    entry = manifest["mcp"].get("entry", "server.py")
    environment = {
        **env, "COS_APP_ID": manifest["id"],
        "COS_APP_MANIFEST": str(app_dir / "app.json"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    }
    with tempfile.TemporaryFile(mode="w+t") as errors:
        process = subprocess.Popen(
            [sys.executable, str(app_dir / entry)], cwd=app_dir, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
        )
        counter = 0

        def request(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": counter, "method": method, "params": params,
            }) + "\n")
            process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(20):
                    raise TimeoutError(f"MCP fixture timed out: {method}")
                line = process.stdout.readline()
            if not line:
                errors.seek(0)
                raise AssertionError(f"MCP fixture exited: {errors.read()}")
            response = json.loads(line)
            assert response["jsonrpc"] == "2.0" and response["id"] == counter, response
            assert "result" in response, response
            return response["result"]

        try:
            request("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "app-contract-fixture", "version": "1"},
            })
            process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            process.stdin.flush()
            yield request
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                raise
            finally:
                process.stdout.close()
        errors.seek(0)
        assert process.returncode == 0, errors.read()


@pytest.fixture(autouse=True)
def unit_policy_bridge(tmp_path, monkeypatch):
    """Imported only by App unit modules that use the original OS policy stub."""
    if os.environ.get("CLAW_COS_BIN"):
        return
    stub = tmp_path / "cos"
    stub.write_text(
        '#!/bin/sh\n'
        'case "$1:$2:$3" in\n'
        '  --wire=1:__policy:check)\n'
        '    echo \'{"ok":true,"wire_version":1,"data":{"decision":"allow"}}\'\n'
        '    exit 0;;\n'
        'esac\n'
        'echo "unsupported unit-test cos command" >&2\n'
        'exit 99\n'
    )
    stub.chmod(0o755)
    monkeypatch.setenv("CLAW_COS_BIN", str(stub))


def load_local_module(path, name, *, clear_modules=()):
    for prefix in clear_modules:
        for module_name in list(sys.modules):
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                sys.modules.pop(module_name, None)
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def platform_dependency():
    root = Path(__file__).resolve().parents[1]
    return load_local_module(root / "tools/platform_dependency.py", "_fixture_platform_dependency")


def stage_platform_python(python):
    """Compose verified SDK/runtime exports without fetching during a test."""
    platform = platform_dependency()
    exports = platform.prepare_exports(download=False)
    for export, package in [("python-sdk", "claw_os_sdk"), ("python-runtime", "cos_runtime")]:
        shutil.copytree(
            exports[export] / package, python / package,
            symlinks=True, ignore=platform.stage.IGNORE,
        )
