"""Native identity, source ownership and shared Files business behavior."""

import json
import os
from pathlib import Path
import types
from unittest import mock

import pytest

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-files"


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("COS_OWNER_HOME", str(tmp_path))
    module = load_local_module(NATIVE / "product_bridge.py", "files_native_bridge")
    module.fs = load_local_module(PRODUCT / "apps/fs/main.py", "files_native_fs")
    module.recoll = load_local_module(PRODUCT / "apps/docs/main.py", "files_native_recoll")
    module.document = load_local_module(
        PRODUCT / "python/claw_files/document.py", "files_native_document",
    )
    with mock.patch.object(module.policy, "require") as require:
        module.require_fixture = require
        yield module


def invoke(bridge, operation, **arguments):
    return bridge.dispatch({"operation": operation, "arguments": arguments})


def test_preserves_native_catalog_and_exact_authority():
    package = json.loads((PRODUCT / "package.json").read_text())
    assert package["native_packages"] == ["cosmic-files", "cosmic-files-applet"]
    manifest = json.loads(Path(__file__).with_name("app.json").read_text())
    assert manifest["id"] == "cosmic-files"
    assert manifest["runtime"] == "binary"
    assert manifest["entry"] == manifest["mcp"]["entry"] == "bin/cosmic-files"
    assert manifest["desktop"]["exec"] == "--gui"
    assert manifest["ai"] == {
        "budget": {"monthly_units": 200000}, "safety": "strict",
        "origins": ["external-content"],
    }
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {f"files.{name}" for name in (
        "list", "metadata", "search", "reveal", "summarize", "explain", "find_similar",
    )}
    assert tools["files.reveal"]["needs"][1]["scope"]["scope"] == {
        "kind": "name", "value": "com.clawos.Files",
    }
    assert tools["files.summarize"]["needs"][2]["scope"]["scope"] == {
        "kind": "self-ref", "value": "cosmic-files",
    }
    assert tools["files.metadata"]["needs"][1]["scope"] == {
        "kind": "from-arg", "arg": "path", "transform": "parent",
    }


def test_standalone_build_preserves_original_toolkit_patches(tmp_path):
    import tomllib
    build = load_local_module(ROOT / "tools/native_build.py", "files_native_build")
    toolkit = tmp_path / "platform/desktop/toolkit"
    destination = tmp_path / "generated"
    build.prepare("files", toolkit, destination)
    manifest = tomllib.loads((destination / "Cargo.toml").read_text())
    assert manifest["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic.git"
    assert manifest["patch"]["https://github.com/pop-os/libcosmic.git"]["libcosmic"]["path"] == str(toolkit)
    assert manifest["workspace"]["members"] == ["cosmic-files-applet"]
    assert manifest["features"]["default"] == [
        "bzip2", "dbus-config", "desktop", "gvfs", "io-uring",
        "lzma-rust2", "notify", "wayland", "wgpu",
    ]
    assert (destination / "Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()


def test_stages_complete_source_both_binaries_and_package_separation(tmp_path):
    native = load_local_module(ROOT / "tools/stage_native.py", "files_native_stage")
    stage = load_local_module(ROOT / "tools/stage.py", "files_stage")
    assert native.stage("files", tmp_path / "native") == ["cosmic-files"]
    staged = tmp_path / "native/cosmic-files"
    for path in NATIVE.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            assert (staged / path.relative_to(NATIVE)).read_bytes() == path.read_bytes()
    assert (staged / "cosmic-files-applet/Cargo.toml").is_file()
    assert (staged / "fs_backend.py").read_bytes() == (PRODUCT / "apps/fs/main.py").read_bytes()
    assert (staged / "recoll_backend.py").read_bytes() == (PRODUCT / "apps/docs/main.py").read_bytes()
    assert stage.stage("files", tmp_path / "desktop", ["cosmic-files"]) == ["cosmic-files"]
    assert not (tmp_path / "desktop/usr/lib/cos/python").exists()
    assert stage.stage("files", tmp_path / "agent", ["fs", "docs"]) == ["fs", "docs"]
    assert (tmp_path / "agent/usr/lib/cos/python/claw_files/document.py").is_file()


def test_document_reader_keeps_authorized_descriptor(bridge, tmp_path):
    file = tmp_path / "a.txt"
    other = tmp_path / "other.txt"
    file.write_text("authorized")
    other.write_text("secret")
    def swap(verb, **scope):
        assert (verb, scope) == ("fs.read", {"path": str(file)})
        file.unlink()
        file.symlink_to(other)
    bridge.require_fixture.side_effect = swap
    assert invoke(bridge, "document", path=str(file))["content"] == "authorized"
    bridge.require_fixture.reset_mock()
    with pytest.raises(ValueError, match="symlink"):
        invoke(bridge, "document", path=str(file))
    bridge.require_fixture.assert_not_called()


@pytest.mark.parametrize(("suffix", "body", "expected"), [
    ("txt", "hello", "hello"), ("json", '{"a":1}', '"a": 1'),
    ("csv", "a,b\n1,2\n", '"b": "2"'), ("md", "# Title", "# Title"),
])
def test_shared_document_formats(bridge, tmp_path, suffix, body, expected):
    path = tmp_path / f"document.{suffix}"
    path.write_text(body)
    assert expected in invoke(bridge, "document", path=str(path))["content"]


def test_gui_mutation_snapshots_original_bytes_and_mcp_environment_is_rejected(
    bridge, monkeypatch, tmp_path,
):
    file = tmp_path / "file"
    file.write_bytes(b"before")
    monkeypatch.setenv("COS_SESSION", "gui-session")
    monkeypatch.delenv("COS_MCP_SERVER", raising=False)
    seen = []
    with mock.patch.object(bridge.fs.snapshot, "snapshot", side_effect=lambda path, op, **kw:
                           seen.append((Path(path).read_bytes(), op, kw))):
        invoke(bridge, "write_bytes", path=str(file), content=[0, 255, 65])
    assert file.read_bytes() == b"\x00\xffA"
    assert seen == [(b"before", "write_bytes", {"session_id": "gui-session"})]
    monkeypatch.setenv("COS_MCP_SERVER", "1")
    with pytest.raises(ValueError, match="MCP process"):
        invoke(bridge, "rm", path=str(file))
    assert file.exists()


def test_denial_blocks_document_and_mutation(bridge, tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("before")
    bridge.require_fixture.side_effect = bridge.policy.PermissionDenied({"summary": "denied"})
    for operation, arguments in [
        ("document", {"path": str(file)}),
        ("write", {"path": str(file), "content": "after"}),
    ]:
        with pytest.raises(bridge.policy.PermissionDenied):
            invoke(bridge, operation, **arguments)
    assert file.read_text() == "before"


def test_recoll_uses_canonical_owner_and_fixed_command(bridge, tmp_path):
    (tmp_path / ".recoll/xapiandb").mkdir(parents=True)
    with mock.patch.object(bridge.recoll.subprocess, "run", return_value=types.SimpleNamespace(
        returncode=0, stdout='"file:///work/a" "text/plain" "123" "match"\n', stderr="",
    )) as run:
        result = invoke(bridge, "recoll", query="subject", max_results=4)
    assert result["results"][0]["snippet"] == "match"
    assert run.call_args.args[0][:3] == ["/usr/bin/recollq", "-c", str(tmp_path / ".recoll")]
    assert run.call_args.kwargs["env"]["HOME"] == str(tmp_path)
    bridge.require_fixture.assert_has_calls([
        mock.call("proc.spawn", name="recollq"), mock.call("fs.read", path=str(tmp_path / ".recoll")),
    ])


def test_summary_memory_retains_files_identity_and_surfaces_denial(bridge):
    with mock.patch.object(bridge.memory, "remember", return_value={"ok": True}) as remember:
        invoke(bridge, "remember", path="/work/a", text="Summary\nsecond line")
    assert remember.call_args.kwargs["source"] == "cosmic-files"
    assert remember.call_args.kwargs["text"] == "Summarised document /work/a: Summary"
