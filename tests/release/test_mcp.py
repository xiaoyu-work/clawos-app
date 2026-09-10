import json
import os
import shutil

import release
from release_common import ROOT, run
from test_support import authenticated_mcp_params, mcp_process


def install_development_runtime(root):
    release.require_platform_artifact()
    import platform_dependency

    exports = platform_dependency.prepare_exports()
    for name, export in (("claw_os_sdk", "python-sdk"), ("cos_runtime", "python-runtime")):
        source = exports[export] / name
        assert source.is_dir(), f"Platform artifact must export {name} through {export}"
        shutil.copytree(source, root / "usr/lib/cos/python" / name,
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))


def test_packaged_doc_and_kv_use_public_mcp_and_installed_support_without_os_sources(tmp_path):
    plan = release.make_plan("files,capability:document-engine,capability:storage-sdk,support", "1.0.0")
    packages = tmp_path / "packages"
    release.build(plan, "all", packages)
    root = tmp_path / "installed"
    for package in sorted(packages.glob("*.deb")):
        run(["dpkg-deb", "--extract", package, root])
    install_development_runtime(root)
    data = tmp_path / "owner/apps/kv"
    data.mkdir(parents=True)
    store = data / "kv.json"
    store.write_text('{"kept":"existing owner state"}')
    environment = {
        "PATH": os.defpath, "PYTHONPATH": str(root / "usr/lib/cos/python"),
        "COS_DATA_DIR": str(data), "TMPDIR": str(tmp_path),
    }
    app = root / "usr/lib/cos/apps/kv"
    with mcp_process(app, env=environment) as request:
        result = request("tools/call", authenticated_mcp_params({
            "name": "kv.get", "arguments": {"key": "kept"},
        }))
        assert result["content"] == [{"type": "text", "text": "existing owner state"}]
        result = request("tools/call", authenticated_mcp_params({
            "name": "kv.set", "arguments": {"key": "added", "value": "independent release"},
        }))
        assert result["structuredContent"] == {"key": "added", "value": "independent release"}
    upgrade = release.make_plan("capability:storage-sdk", "1.1.0")
    release.build(upgrade, "all", tmp_path / "upgrade")
    run(["dpkg-deb", "--extract", next((tmp_path / "upgrade").glob("*.deb")), root])
    with mcp_process(app, env=environment) as request:
        result = request("tools/call", authenticated_mcp_params({"name": "kv.dump", "arguments": {}}))
        assert result["structuredContent"]["data"] == {
            "kept": "existing owner state", "added": "independent release",
        }
    doc = root / "usr/lib/cos/apps/doc"
    with mcp_process(doc, env=environment) as request:
        tools = request("tools/list", {})["tools"]
        assert {tool["name"] for tool in tools} == {
            "doc.read", "doc.info", "doc.convert", "doc.summarize", "doc.explain", "doc.rewrite",
        }
    assert json.loads(store.read_text())["kept"] == "existing owner state"
    assert not (data.parent / "doc").exists()
    assert (root / "usr/lib/cos/python/claw_files/document.py").is_file()
    assert not (root / "usr/lib/cos/apps/_shared").exists()
