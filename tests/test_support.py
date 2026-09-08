"""Isolated loading for product modules that are executable entry points."""

import importlib.util
import os
import sys

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
