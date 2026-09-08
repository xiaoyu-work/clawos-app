"""Complete nested Settings workspace, default pages and human-only adapters."""

import json
import os
from pathlib import Path
import tomllib
import types
import pytest
from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[1]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-settings"


def test_native_staging_preserves_all_sources_resources_and_modes(tmp_path):
    stage = load_local_module(ROOT / "tools/stage_native.py", "settings_stage_native")
    assert stage.stage("settings", tmp_path) == ["cosmic-settings"]
    for path in NATIVE.rglob("*"):
        output = tmp_path / "cosmic-settings" / path.relative_to(NATIVE)
        if path.is_symlink():
            assert output.is_symlink() and os.readlink(output) == os.readlink(path)
        elif path.is_file():
            assert output.read_bytes() == path.read_bytes()
            assert output.stat().st_mode == path.stat().st_mode


def test_original_nested_workspace_patches_and_full_default_graph(tmp_path):
    native = load_local_module(ROOT / "tools/native_build.py", "settings_native_build")
    output = tmp_path / "settings"
    native.prepare("settings", tmp_path / "platform/desktop/toolkit", output)
    cargo = tomllib.loads((output / "Cargo.toml").read_text())
    assert cargo["workspace"]["members"] == ["cosmic-settings", "crates/*", "page", "pages/*", "subscriptions/*"]
    assert cargo["workspace"]["default-members"] == ["cosmic-settings"]
    patches = cargo["patch"]
    assert patches["https://github.com/pop-os/libcosmic"]["libcosmic"]["path"] == str(tmp_path / "platform/desktop/toolkit")
    assert patches["https://github.com/pop-os/cosmic-protocols"]["cosmic-protocols"]["rev"] == "d0e95be"
    assert patches["crates-io"]["atspi"]["git"] == "https://github.com/wash2/atspi"
    main = tomllib.loads((output / "cosmic-settings/Cargo.toml").read_text())
    assert main["features"]["default"] == ["a11y", "linux", "single-instance", "wgpu"]
    assert len([feature for feature in main["features"]["linux"] if feature.startswith("page-")]) == 16
    for library in ("claw-os-sdk", "cos-runtime"):
        assert main["dependencies"][library]["path"] == str(tmp_path / "platform" / library / "rust")
    assert (output / "Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    for path in ("i18n/en/cosmic_settings.ftl", "page/src/lib.rs", "pages/wallpapers/src/lib.rs",
                 "subscriptions/sound/src/lib.rs", "resources/default_schema", "debian/copyright"):
        assert (output / path).exists(), path


@pytest.fixture
def human(monkeypatch):
    monkeypatch.delenv("COS_MCP_SERVER", raising=False)
    monkeypatch.setenv("COS_SESSION", "fixture-session")
    module = load_local_module(NATIVE / "human_bridge.py", "settings_human")
    events = []
    monkeypatch.setattr(module.policy, "require", lambda verb, **scope: events.append((verb, scope)))
    monkeypatch.setattr(module.snapshot, "snapshot", lambda path, op, **context: events.append((op, path, context)))
    monkeypatch.setattr(module.snapshot, "snapshot_pair", lambda src, dst, op, **context: events.append((op, src, dst, context)))
    return module, events


def test_human_mutations_preserve_exact_policy_and_snapshot_order(human, tmp_path):
    module, events = human
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.write_text("synthetic")
    module.dispatch({"operation": "rename", "arguments": {"path": str(source), "destination": str(destination)}})
    assert destination.read_text() == "synthetic" and not source.exists()
    assert events == [
        ("fs.delete", {"path": str(source)}), ("fs.write", {"path": str(destination)}),
        ("rename", str(source), str(destination), {"session_id": "fixture-session"}),
    ]
    events.clear()
    module.dispatch({"operation": "remove", "arguments": {"path": str(destination)}})
    assert not destination.exists()
    assert events == [("fs.delete", {"path": str(destination)}),
                      ("rm", str(destination), {"session_id": "fixture-session"})]
    module.dispatch({"operation": "mkdir", "arguments": {"path": str(destination)}})
    assert destination.is_dir()


def test_human_adapters_fail_closed_before_mutations(human, tmp_path, monkeypatch):
    module, events = human
    source = tmp_path / "source"
    source.write_text("unchanged")
    request = {"operation": "remove", "arguments": {"path": str(source)}}
    monkeypatch.setenv("COS_MCP_SERVER", "1")
    with pytest.raises(PermissionError):
        module.dispatch(request)
    assert events == [] and source.read_text() == "unchanged"
    monkeypatch.delenv("COS_MCP_SERVER")
    def denied(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(module.policy, "require", denied)
    with pytest.raises(PermissionError):
        module.dispatch(request)
    assert source.exists() and events == []
    monkeypatch.setattr(module.policy, "require", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.snapshot, "snapshot", denied)
    with pytest.raises(PermissionError):
        module.dispatch(request)
    assert source.exists()


def test_human_queries_are_bounded_scrubbed_and_gated(human, monkeypatch):
    module, events = human
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-secret")
    result = module.run(["/usr/bin/python3", "-c", "import os; print('OPENAI_API_KEY' in os.environ)"], 5)
    assert result == {"exit_code": 0, "stdout": "False\n", "stderr": ""}
    assert events == [("proc.spawn", {"name": "/usr/bin/python3"})]
    result = module.run(["/usr/bin/python3", "-c", "print('x'*1100000)"], 5)
    assert len(result["stdout"]) == 1_000_000
    with pytest.raises(TimeoutError):
        module.run(["/usr/bin/python3", "-c", "import time; time.sleep(5)"], 1)
    before = events.copy()
    for argv in ([], ["x\0y"], [1]):
        with pytest.raises(ValueError):
            module.run(argv, 5)
    assert events == before
