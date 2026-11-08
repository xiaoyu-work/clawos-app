"""Product packaging must keep the established installed App contract."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile

import pytest

from test_support import authenticated_mcp_params, load_local_module, mcp_process, stage_platform_python


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_stage", ROOT / "tools" / "stage.py")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


def test_product_web_interfaces_are_owned_staged_and_do_not_change_app_manifests(tmp_path):
    for kind in ("product", "capability"):
        for name in stage.sources(kind):
            source, package = stage.load_package(name, kind)
            entries = stage.app_entries(source, package)
            assert set(package["web_ui"]["apps"]) <= set(entries)
            for app_id in package["web_ui"]["apps"]:
                app_source = entries[app_id]
                target = tmp_path / kind / name / app_id
                shutil.copytree(app_source, target, ignore=stage.IGNORE)
                before = (target / "app.json").read_bytes()
                stage.stage_ui(source, package, app_id, target, kind=kind)
                descriptor = json.loads((target / "web-ui.json").read_text())
                assert descriptor["app_id"] == app_id
                assert descriptor["source_name"] == name and descriptor["source_kind"] == kind
                assert (target / descriptor["entry"]).is_file()
                assert (target / "web/app.js").read_bytes() == (source / "web/app.js").read_bytes()
                assert (target / "web/shared/client.js").is_file()
                assert (target / "app.json").read_bytes() == before

def test_staged_calendar_files_mail_chain_uses_public_mcp_and_isolated_wire(tmp_path):
    """Protocol acceptance only; OS Host/authority acceptance remains separate."""
    import textwrap

    destination = tmp_path / "stage"
    stage.stage("calendar", destination, ["calendar"])
    stage.stage("files", destination, ["fs"])
    stage.stage("mail", destination, ["email"])
    stage.stage_shared(destination)
    python = destination / "usr/lib/cos/python"
    stage_platform_python(python)
    control = tmp_path / "wire-control.json"
    control.write_text('{"deny":null}')
    log = tmp_path / "wire.jsonl"
    peer = tmp_path / "cos"
    peer.write_text(f"#!{sys.executable}\n" + textwrap.dedent("""\
        import json, os, sys
        from pathlib import Path
        assert sys.argv[1] == "--wire=1"
        app = os.environ["COS_APP_ID"]
        assert app in {"calendar", "fs", "email"}
        args = sys.argv[2:]
        record = {"app":app,"args":args}
        if args[:2] == ["__policy", "check"]:
            denied = json.loads(Path(os.environ["TEST_CONTROL"]).read_text())["deny"]
            data = {"decision":"deny" if args[2] == denied else "allow"}
        elif args[:2] == ["__app_event", "publish"]:
            record["event"] = json.loads(sys.stdin.read())
            assert "owner_uid" not in record["event"] and "source" not in record["event"]
            data = {"accepted":True}
        elif args[:2] == ["__memory", "remember"]:
            data = {"row_id":1,"session_id":"synthetic","indexed_semantic":False}
        elif args[:2] == ["ai", "chat"]:
            assert app == "email"
            options = dict(zip(args[2::2],args[3::2],strict=True))
            assert options["--app"] == "email"
            record["prompt"] = Path(options["--prompt-file"]).read_text()
            data = {"text":"Synthetic review draft","model":"fixture","provider":"fixture",
                "verb":"ai.chat","usage":{"input_tokens":1,"output_tokens":1,"units":2},
                "budget":{"period":"2026-11","units_used":2,"units_cap":10000},
                "review":{"safety":"strict","prompt_redacted":True}}
        else:
            raise AssertionError("No task submission, external transport or other App route")
        with open(os.environ["TEST_LOG"],"a") as out:
            out.write(json.dumps(record)+"\\n")
        print(json.dumps({"ok":True,"wire_version":1,"data":data}))
    """))
    peer.chmod(0o755)
    target = tmp_path / "agenda.txt"
    target.write_text("Original agenda\n")
    sentinels = [tmp_path / "other-owner" / "memory.db", tmp_path / "owner" / "credentials.json"]
    for sentinel in sentinels:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_bytes(b"unrelated synthetic state")

    def environment(app):
        data = tmp_path / "owner" / "apps" / app
        data.mkdir(parents=True, mode=0o700)
        return {
            "PATH": os.defpath, "PYTHONPATH": str(python), "CLAW_COS_BIN": str(peer),
            "COS_SESSION": f"synthetic-{app}", "COS_DATA_DIR": str(data),
            "TEST_CONTROL": str(control), "TEST_LOG": str(log),
        }

    def call(request, name, arguments):
        result = request("tools/call", authenticated_mcp_params({"name": name, "arguments": arguments}))
        assert not result.get("isError"), result
        return result["structuredContent"]

    apps = destination / "usr/lib/cos/apps"
    with mcp_process(apps / "calendar", env=environment("calendar")) as calendar:
        event = call(calendar, "calendar.create", {
            "provider": "local", "title": "Synthetic review", "start": "2026-11-10T10:00:00Z",
        })
        reference = event["event"]["object"]
        assert reference.startswith("app://calendar/local-event?")
    with mcp_process(apps / "fs", env=environment("fs")) as files:
        proposal = call(files, "fs.plan_write", {
            "path": str(target), "content": f"Review {reference}\n",
        })
        assert proposal["reference"].startswith("app://fs/change-plan?")
        shown = call(files, "fs.plan_show", {"path": str(target), "plan": proposal["plan_id"]})
        assert shown["review"] == proposal["review"]
        assert reference in shown["diff"]
        control.write_text('{"deny":"data.db.write"}')
        refused = files("tools/call", authenticated_mcp_params({
            "name": "fs.plan_write", "arguments": {"path": str(target), "content": "must not apply"},
        }))
        assert refused["isError"] is True
        control.write_text('{"deny":null}')
    with mcp_process(apps / "email", env=environment("email")) as mail:
        draft = call(mail, "email.draft", {
            "context": f"Prepare a review note for {reference} and {proposal['reference']}", "style": "formal",
        })
        assert draft["draft"] == "Synthetic review draft"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    ai_call = next(row for row in records if row["args"][:2] == ["ai", "chat"])
    assert reference in ai_call["prompt"] and proposal["reference"] in ai_call["prompt"]
    assert [row["app"] for row in records if "event" in row] == ["calendar", "fs"]
    assert target.read_text() == "Original agenda\n"
    assert all(path.read_bytes() == b"unrelated synthetic state" for path in sentinels)


def test_calendar_stage_is_separate_and_preserves_its_manifest(tmp_path):
    assert {"mail", "calendar"} <= set(stage.products())
    assert stage.stage("calendar", tmp_path) == ["calendar", "panel-calendar"]
    app = tmp_path / "usr/lib/cos/apps/calendar"
    source = ROOT / "products/calendar/apps/calendar"
    assert (app / "app.json").read_bytes() == (source / "app.json").read_bytes()
    assert (app / "main.py").read_bytes() == (source / "main.py").read_bytes()
    assert (app / "server.py").is_file()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/apps/mail-ai").exists()


def test_files_stage_preserves_the_direct_mcp_contract(tmp_path):
    assert "files" in stage.products()
    assert stage.stage("files", tmp_path) == ["fs", "docs", "cosmic-files"]
    for app_id in ("fs", "docs"):
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products/files/apps" / app_id
        for filename in ("app.json", "main.py", "server.py"):
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    assert (tmp_path / "usr/lib/cos/python/claw_files/document.py").read_bytes() == (
        ROOT / "products/files/python/claw_files/document.py"
    ).read_bytes()
    assert not (tmp_path / "usr/lib/systemd").exists()


def test_document_engine_is_a_capability_not_a_business_product(tmp_path):
    assert len(stage.products()) == 24
    assert stage.sources("capability") == ["ai-helpers", "document-engine", "http", "storage-sdk"]
    assert "document-engine" not in stage.products()
    assert stage.stage("document-engine", tmp_path, kind="capability") == ["doc"]
    source = ROOT / "capabilities/document-engine/apps/doc"
    installed = tmp_path / "usr/lib/cos/apps/doc"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for name in ("app.json", "main.py", "server.py"):
        assert (installed / name).read_bytes() == (source / name).read_bytes()
        assert (installed / name).stat().st_mode == (source / name).stat().st_mode
    library = tmp_path / "usr/lib/cos/python/claw_files"
    assert (library / "document.py").read_bytes() == (
        ROOT / "products/files/python/claw_files/document.py"
    ).read_bytes()
    assert not (tmp_path / "usr/lib/cos/apps/fs").exists()
    assert not (tmp_path / "usr/lib/cos/apps/docs").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var").exists()
    with pytest.raises(ValueError, match="Unknown product source"):
        stage.stage("document-engine", tmp_path / "wrong-kind")


def test_ai_helpers_complete_original_source_ownership_without_provider_or_state(tmp_path):
    products = stage.products()
    capabilities = stage.sources("capability")
    assert len(products) == 24
    assert len(capabilities) == 4
    identities = []
    for kind, names in [("product", products), ("capability", capabilities)]:
        for name in names:
            source, package = stage.load_package(name, kind)
            identities.extend(stage.app_entries(source, package))
    assert len(identities) == len(set(identities)) == 63
    assert stage.stage("ai-helpers", tmp_path, kind="capability") == ["summarize"]
    original = ROOT / "capabilities/ai-helpers/apps/summarize"
    installed = tmp_path / "usr/lib/cos/apps/summarize"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for name in ("app.json", "main.py", "server.py"):
        assert (installed / name).read_bytes() == (original / name).read_bytes()
        assert (installed / name).stat().st_mode == (original / name).stat().st_mode
    assert [path.name for path in installed.parent.iterdir()] == ["summarize"]
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var").exists()
    with pytest.raises(ValueError, match="Unknown product source"):
        stage.stage("ai-helpers", tmp_path / "wrong-kind")
    assert stage.stage("ai-helpers", tmp_path / "filtered", [], kind="capability") == []
    assert not (tmp_path / "filtered").exists()


def test_http_stages_the_complete_client_without_an_os_provider_or_product(tmp_path):
    assert "http" not in stage.products()
    assert stage.stage("http", tmp_path, kind="capability") == ["net"]
    source = ROOT / "capabilities/http/apps/net"
    installed = tmp_path / "usr/lib/cos/apps/net"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for name in ("app.json", "main.py", "server.py"):
        assert (installed / name).read_bytes() == (source / name).read_bytes()
        assert (installed / name).stat().st_mode == (source / name).stat().st_mode
    assert [path.name for path in installed.parent.iterdir()] == ["net"]
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var").exists()
    with pytest.raises(ValueError, match="Unknown product source"):
        stage.stage("http", tmp_path / "wrong-kind")
    assert stage.stage("http", tmp_path / "filtered", [], kind="capability") == []
    assert not (tmp_path / "filtered").exists()


def test_storage_sdk_stages_only_db_without_copying_sdk_providers_or_state(tmp_path):
    assert len(stage.products()) == 24
    assert "storage" in stage.products()
    assert "storage-sdk" not in stage.products()
    assert stage.stage("storage-sdk", tmp_path, ["db"], kind="capability") == ["db"]
    source = ROOT / "capabilities/storage-sdk/apps/db"
    installed = tmp_path / "usr/lib/cos/apps/db"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for name in ("app.json", "main.py", "server.py"):
        assert (installed / name).read_bytes() == (source / name).read_bytes()
        assert (installed / name).stat().st_mode == (source / name).stat().st_mode
    assert [path.name for path in installed.parent.iterdir()] == ["db"]
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var").exists()
    with pytest.raises(ValueError, match="Unknown product source"):
        stage.stage("storage-sdk", tmp_path / "wrong-kind")
    assert stage.stage("storage-sdk", tmp_path / "filtered", [], kind="capability") == []
    assert not (tmp_path / "filtered").exists()


def test_storage_sdk_stages_independent_db_and_kv_without_platform_code(tmp_path):
    assert stage.stage("storage-sdk", tmp_path, kind="capability") == ["db", "kv"]
    apps = tmp_path / "usr/lib/cos/apps"
    assert sorted(path.name for path in apps.iterdir()) == ["db", "kv"]
    kv = apps / "kv"
    original = ROOT / "capabilities/storage-sdk/apps/kv"
    assert {path.name for path in kv.iterdir()} == {"app.json", "server.py"}
    for name in ("app.json", "server.py"):
        assert (kv / name).read_bytes() == (original / name).read_bytes()
        assert (kv / name).stat().st_mode == (original / name).stat().st_mode
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "var").exists()
    assert stage.stage("storage-sdk", tmp_path / "kv-only", ["kv"], kind="capability") == ["kv"]
    assert not (tmp_path / "kv-only/usr/lib/cos/apps/db").exists()


def test_public_mcp_requires_common_runtime_and_never_imports_legacy_sibling_helpers(tmp_path):
    root = tmp_path / "installed"
    stage.stage("http", root, kind="capability")
    app = root / "usr/lib/cos/apps/net"
    python = root / "usr/lib/cos/python"
    stage_platform_python(python)
    legacy = app.parent / "_shared"
    legacy.mkdir()
    (legacy / "__init__.py").write_text("raise RuntimeError('legacy helper must not load')\n")
    manifest = json.loads((app / "app.json").read_text())
    environment = {
        "PATH": os.defpath, "PYTHONPATH": str(python),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "COS_APP_MANIFEST": str(app / "app.json"),
    }
    missing = subprocess.run(
        [sys.executable, str(app / manifest["mcp"]["entry"])],
        input="", cwd=app, env=environment, capture_output=True, text=True, timeout=20,
    )
    assert missing.returncode != 0
    assert "No module named '_shared'" in missing.stderr
    assert "legacy helper must not load" not in missing.stderr
    stage.stage_shared(root)
    with mcp_process(app, env=environment) as request:
        tools = request("tools/list", {})["tools"]
        assert {tool["name"] for tool in tools} == {"net.fetch", "net.download"}
        invalid = request("tools/call", authenticated_mcp_params({
            "name": "net.fetch", "arguments": {"url": "file:///not-accessed"},
        }))
        assert invalid["isError"] is True
        assert "not allowed" in invalid["content"][0]["text"]
    assert (legacy / "__init__.py").read_text() == "raise RuntimeError('legacy helper must not load')\n"


def test_mcp_only_app_uses_explicit_tests_without_a_main_module(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    runner = load_local_module(ROOT / "tools/test.py", "claw_test_app_runner")
    app = tmp_path / "apps/kv"
    app.mkdir(parents=True)
    (app / "app.json").write_text('{"id":"kv"}')
    (app / "test_server.py").write_text("def test_service(): pass\n")
    package = {"apps": ["apps/kv"], "tests": ["apps/kv/test_server.py"]}
    assert runner.source_tests(tmp_path, package) == [app / "test_server.py"]
    with pytest.raises(ValueError, match="requires an explicit test file"):
        runner.source_tests(tmp_path, {**package, "tests": []})
    (app / "test_server.py").unlink()
    with pytest.raises(ValueError, match="requires an explicit test file"):
        runner.source_tests(tmp_path, package)


@pytest.mark.parametrize("refactor", ["none", "private-module", "declared-entrypoint"])
def test_staged_kv_uses_public_mcp_and_preserves_its_independent_namespace(tmp_path, refactor):
    stage.stage("storage-sdk", tmp_path, ["kv"], kind="capability")
    python = stage.stage_shared(tmp_path)
    stage_platform_python(python)
    apps = tmp_path / "usr/lib/cos/apps"
    app = apps / "kv"
    manifest = json.loads((app / "app.json").read_text())
    if refactor == "private-module":
        (app / manifest["mcp"]["entry"]).rename(app / "kv_service.py")
        (app / manifest["mcp"]["entry"]).write_text("from kv_service import app\napp.serve()\n")
    elif refactor == "declared-entrypoint":
        (app / manifest["mcp"]["entry"]).rename(app / "kv_mcp.py")
        manifest["mcp"]["entry"] = "kv_mcp.py"
        (app / "app.json").write_text(json.dumps(manifest))
    data = tmp_path / "owner-data/apps/kv"
    data.mkdir(parents=True)
    store = data / "kv.json"
    original = b'{\n  "kept": "existing state",\n  "empty": ""\n}\n'
    store.write_bytes(original)
    identity = store.stat().st_ino
    neighbours = [
        tmp_path / "owner-data/apps/db/db/existing.db",
        tmp_path / "owner-data/apps/storage-manager/state",
        tmp_path / "owner-data/agent/memory.db",
        tmp_path / "other-owner/apps/kv/kv.json",
    ]
    for path in neighbours:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"unrelated private state")
    environment = {
        "PATH": os.defpath, "PYTHONPATH": str(python),
        "COS_DATA_DIR": str(data),
    }
    with mcp_process(app, env=environment) as request:
        def call(command, arguments):
            result = request("tools/call", authenticated_mcp_params({
                "name": f"kv.{command}", "arguments": arguments,
            }))
            assert not result.get("isError"), result
            return result

        assert call("get", {"key": "kept"})["content"] == [
            {"type": "text", "text": "existing state"},
        ]
        assert store.read_bytes() == original
        assert store.stat().st_ino == identity
        assert call("set", {"key": "new", "value": "next"})["structuredContent"] == {
            "key": "new", "value": "next",
        }
        assert call("list", {})["structuredContent"] == {
            "pattern": "*", "keys": ["empty", "kept", "new"],
        }
    with mcp_process(app, env=environment) as request:
        result = request("tools/call", authenticated_mcp_params({"name": "kv.dump", "arguments": {}}))
        assert result["structuredContent"] == {
            "count": 3, "data": {"kept": "existing state", "empty": "", "new": "next"},
        }
    assert json.loads(store.read_bytes()) == {"kept": "existing state", "empty": "", "new": "next"}
    assert store.stat().st_mode & 0o777 == 0o600
    assert store.stat().st_ino != identity
    assert {path.name for path in data.iterdir()} == {"kv.json", "kv.json.lock"}
    assert all(path.read_bytes() == b"unrelated private state" for path in neighbours)
    assert not (data.parent / "storage-sdk").exists()
    assert not (app / "main.py").exists()


@pytest.mark.parametrize("refactor", ["none", "private-module", "declared-entrypoint"])
def test_staged_db_dispatches_with_real_sdk_and_preserves_its_data_namespace(tmp_path, refactor):
    stage.stage("storage-sdk", tmp_path, kind="capability")
    python = tmp_path / "usr/lib/cos/python"
    stage_platform_python(python)
    data = tmp_path / "owner-data/apps/db"
    database = data / "db/existing.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE items (value TEXT)")
        connection.execute("INSERT INTO items VALUES ('existing state')")
    identity = (database.stat().st_dev, database.stat().st_ino)
    siblings = [
        tmp_path / "owner-data/apps/kv/kv.json",
        tmp_path / "owner-data/agent/memory.db",
        tmp_path / "other-owner/apps/db/db/existing.db",
    ]
    for sibling in siblings:
        sibling.parent.mkdir(parents=True, exist_ok=True)
        sibling.write_bytes(b"unrelated private state")
    policy = tmp_path / "cos"
    policy.write_text(
        '#!/bin/sh\n'
        'test "$1:$2:$3" = "--wire=1:__policy:check" || exit 99\n'
        'case "$4:$5:$6" in\n'
        '  data.db.read:--name:existing|data.db.write:--name:existing) decision=allow;;\n'
        '  *) decision=deny;;\n'
        'esac\n'
        'printf \'{"ok":true,"wire_version":1,"data":{"decision":"%s"}}\\n\' "$decision"\n'
    )
    policy.chmod(0o755)
    calls = [
        ("query", {"database": "existing", "sql": "SELECT value FROM items"}),
        ("exec", {"database": "existing", "sql": "UPDATE items SET value = 'updated state'"}),
        ("query", {"database": "existing", "sql": "SELECT value FROM items"}),
        ("query", {"database": "other", "sql": "SELECT 1"}),
        ("databases", {}),
    ]
    app = tmp_path / "usr/lib/cos/apps/db"
    if refactor == "private-module":
        (app / "main.py").rename(app / "database_client.py")
        entry = app / json.loads((app / "app.json").read_text())["mcp"]["entry"]
        entry.write_text(entry.read_text().replace("from main import ", "from database_client import "))
    elif refactor == "declared-entrypoint":
        manifest = json.loads((app / "app.json").read_text())
        (app / manifest["mcp"]["entry"]).rename(app / "db_mcp.py")
        manifest["mcp"]["entry"] = "db_mcp.py"
        (app / "app.json").write_text(json.dumps(manifest))
    with mcp_process(app, env={
        "PATH": os.defpath, "PYTHONPATH": str(python), "COS_DATA_DIR": str(data),
        "CLAW_COS_BIN": str(policy),
    }) as request:
        results = [
            request("tools/call", authenticated_mcp_params({
                "name": f"db.{command}", "arguments": arguments,
            }))
            for command, arguments in calls
        ]
    assert results[0]["structuredContent"]["rows"] == [["existing state"]]
    assert results[1]["structuredContent"]["rows_affected"] == 1
    assert results[2]["structuredContent"]["rows"] == [["updated state"]]
    for denied in results[3:]:
        assert denied["isError"] is True
        assert "PermissionDenied" in denied["content"][0]["text"]
    assert (database.stat().st_dev, database.stat().st_ino) == identity
    assert [path.name for path in database.parent.iterdir()] == ["existing.db"]
    assert all(sibling.read_bytes() == b"unrelated private state" for sibling in siblings)
    assert not (data.parent / "storage-sdk").exists()


@pytest.mark.parametrize("order", [("files", "document-engine"), ("document-engine", "files")])
def test_shared_library_costages_once_without_merging_trees(tmp_path, order):
    for name in order:
        stage.stage(name, tmp_path, kind="capability" if name == "document-engine" else "product")
    assert sorted(path.name for path in (tmp_path / "usr/lib/cos/python").iterdir()) == ["claw_files"]
    assert sorted(path.name for path in (tmp_path / "usr/lib/cos/apps").iterdir()) == [
        "cosmic-files", "doc", "docs", "fs",
    ]


@pytest.mark.parametrize("change", ["content", "mode", "extra", "symlink"])
def test_conflicting_shared_library_is_never_overwritten_or_merged(tmp_path, change):
    stage.stage("files", tmp_path)
    library = tmp_path / "usr/lib/cos/python/claw_files"
    document = library / "document.py"
    if change == "content":
        document.write_text("different source")
    elif change == "mode":
        document.chmod(0o755)
    elif change == "extra":
        (library / "unrelated.py").write_text("unrelated source")
    else:
        document.unlink()
        document.symlink_to("missing.py")
    before = stage._library_tree(library)
    with pytest.raises(ValueError, match="Conflicting staged Python library"):
        stage.stage("document-engine", tmp_path, kind="capability")
    assert stage._library_tree(library) == before
    assert not (tmp_path / "usr/lib/cos/apps/doc").exists()


def test_filtered_capability_does_not_stage_unused_library(tmp_path):
    assert stage.stage("document-engine", tmp_path, [], kind="capability") == []
    assert not tmp_path.joinpath("usr").exists()


@pytest.fixture
def capability_package(tmp_path, monkeypatch):
    source = tmp_path / "source"
    group = source / "capabilities/document-engine"
    app = group / "apps/doc"
    app.mkdir(parents=True)
    (app / "app.json").write_text('{"id":"doc"}')
    package = {"kind": "shared-capability-client", "apps": ["apps/doc"]}
    (group / "package.json").write_text(json.dumps(package))
    monkeypatch.setattr(stage, "ROOT", source)
    return source, group, package


@pytest.mark.parametrize("kind", [None, [], "unknown", "../products"])
def test_unknown_source_kind_is_rejected(capability_package, kind):
    with pytest.raises(ValueError, match="source kind"):
        stage.load_package("document-engine", kind)


@pytest.mark.parametrize("declared", [None, "product", "capability"])
def test_capability_metadata_requires_explicit_client_kind(capability_package, declared):
    _, group, package = capability_package
    if declared is None:
        package.pop("kind")
    else:
        package["kind"] = declared
    (group / "package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="Package kind"):
        stage.load_package("document-engine", "capability")


def test_duplicate_source_names_across_kinds_are_rejected(capability_package):
    source, _, _ = capability_package
    duplicate = source / "products/document-engine"
    duplicate.mkdir(parents=True)
    (duplicate / "package.json").write_text('{"apps":["apps/doc"]}')
    with pytest.raises(ValueError, match="Duplicate App source"):
        stage.sources()


@pytest.mark.parametrize("name", ["../document-engine", "/document-engine", "missing"])
def test_capability_source_never_falls_back_to_another_root(capability_package, name):
    with pytest.raises(ValueError, match="Unknown capability source"):
        stage.load_package(name, "capability")


@pytest.mark.parametrize("field", ["native", "native_libraries", "extension"])
def test_capability_cannot_invent_native_product_assets(capability_package, field):
    _, group, package = capability_package
    package[field] = {}
    (group / "package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="native product assets"):
        stage.load_package("document-engine", "capability")


@pytest.mark.parametrize("apps", [["apps/doc", "apps/doc"], ["apps/../doc"]])
def test_capability_duplicate_or_traversing_apps_are_rejected(capability_package, apps, tmp_path):
    _, group, package = capability_package
    package["apps"] = apps
    (group / "package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="Duplicate|layout"):
        stage.stage("document-engine", tmp_path / "stage", kind="capability")


def test_capability_source_symlink_escape_is_rejected(capability_package, tmp_path):
    source, group, _ = capability_package
    outside = tmp_path / "outside"
    group.rename(outside)
    group.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="declared kind"):
        stage.load_package("document-engine", "capability")
    assert not (source / "products/document-engine").exists()


@pytest.mark.parametrize("dependency", [
    {"kind": "product", "name": "../files", "library": "claw_files", "apps": ["doc"]},
    {"kind": "product", "name": "missing", "library": "claw_files", "apps": ["doc"]},
    {"kind": "unknown", "name": "files", "library": "claw_files", "apps": ["doc"]},
    {"path": "../files/python"},
])
def test_library_dependencies_require_declared_sources(capability_package, dependency, tmp_path):
    _, group, package = capability_package
    package["python_dependencies"] = [dependency]
    (group / "package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="source|dependency"):
        stage.stage("document-engine", tmp_path / "stage", kind="capability")
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize("change", ["missing", "name", "path", "duplicate", "consumer"])
def test_library_dependency_must_match_one_owned_export(capability_package, change, tmp_path):
    source, group, package = capability_package
    owner = source / "products/files"
    (owner / "apps/fs").mkdir(parents=True)
    (owner / "apps/fs/app.json").write_text('{"id":"fs"}')
    library = owner / "python/claw_files"
    library.mkdir(parents=True)
    (library / "__init__.py").write_text("")
    export = {"name": "claw_files", "path": "python/claw_files", "apps": ["fs"]}
    owner_package = {"apps": ["apps/fs"], "python_library": export}
    dependency = {"kind": "product", "name": "files", "library": "claw_files", "apps": ["doc"]}
    package["python_dependencies"] = [dependency]
    if change == "missing":
        owner_package.pop("python_library")
    elif change == "name":
        dependency["library"] = "undeclared"
    elif change == "path":
        export["path"] = "../outside"
    elif change == "duplicate":
        package["python_dependencies"].append(dependency.copy())
    else:
        dependency["apps"] = ["another-app"]
    (owner / "package.json").write_text(json.dumps(owner_package))
    (group / "package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="library"):
        stage.stage("document-engine", tmp_path / "stage", kind="capability")
    assert not (tmp_path / "stage").exists()


def test_document_runs_with_only_the_actual_staged_library_and_platform(tmp_path):
    stage.stage("document-engine", tmp_path, kind="capability")
    python = stage.stage_shared(tmp_path)
    stage_platform_python(python)
    document = tmp_path / "synthetic.txt"
    document.write_text("installed shared document parser")
    policy = tmp_path / "cos"
    policy.write_text(
        '#!/bin/sh\n'
        'test "$1:$2:$3" = "--wire=1:__policy:check" || exit 99\n'
        'printf \'%s\\n\' \'{"ok":true,"wire_version":1,"data":{"decision":"allow"}}\'\n'
    )
    policy.chmod(0o755)
    app = tmp_path / "usr/lib/cos/apps/doc"
    result = subprocess.run(
        [sys.executable, "-c",
         "import json; import claw_files.document as library; import main; "
         "print(json.dumps({'library':library.__file__, 'result':main.run('read', "
         f"[{str(document)!r}])}}))"],
        cwd=app, capture_output=True, text=True, check=True, timeout=20,
        env={"PATH": os.defpath, "PYTHONPATH": str(python),
             "PYTHONDONTWRITEBYTECODE": "1", "CLAW_COS_BIN": str(policy)},
    )
    payload = json.loads(result.stdout)
    assert payload["library"] == str(python / "claw_files/document.py")
    assert payload["result"]["content"] == "installed shared document parser"


def test_browser_stage_preserves_search_without_os_services(tmp_path):
    assert "browser" in stage.products()
    assert stage.stage("browser", tmp_path) == ["search", "web", "browser-attached"]
    for app_id in ("search", "web", "browser-attached"):
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products/browser/apps" / app_id
        for filename in ("app.json", "main.py", "server.py"):
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    native_host = "usr/lib/cos/apps/browser-attached/native_host.py"
    assert (tmp_path / native_host).read_bytes() == (
        ROOT / "products/browser/apps/browser-attached/native_host.py"
    ).read_bytes()
    extension = tmp_path / "usr/share/claw/extensions/claw-agent-browser"
    assert stage._library_tree(extension) == stage._library_tree(
        ROOT / "products/browser/extension", payload=True,
    )
    launcher = tmp_path / "usr/lib/cos/claw-browser-host"
    source_launcher = ROOT / "products/browser/packaging/claw-browser-host"
    assert launcher.read_bytes() == source_launcher.read_bytes()
    assert launcher.stat().st_mode == source_launcher.stat().st_mode
    assert launcher.stat().st_mode & 0o111
    assert not (extension / "test_contract.py").exists()
    assert not (tmp_path / "usr/lib/cos/browser-agent").exists()
    assert not (tmp_path / "usr/lib/cos/apps/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin/cos-browser").exists()
    assert not (tmp_path / "etc/chromium").exists()


@pytest.mark.parametrize("selected", [
    [], ["search"], ["web"], ["search", "web"],
    ["browser-attached"], ["search", "browser-attached"],
])
def test_browser_assets_follow_declared_owner_selection(tmp_path, selected):
    assert stage.stage("browser", tmp_path, selected) == selected
    attached = "browser-attached" in selected
    extension = tmp_path / "usr/share/claw/extensions/claw-agent-browser"
    launcher = tmp_path / "usr/lib/cos/claw-browser-host"
    assert extension.exists() is attached
    assert launcher.exists() is attached
    apps = tmp_path / "usr/lib/cos/apps"
    if selected:
        assert sorted(path.name for path in apps.iterdir()) == sorted(selected)
    else:
        assert not apps.exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/lib/cos/browser-agent").exists()
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path / "var").exists()


def test_browser_cli_stage_includes_declared_assets_without_a_second_stager(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/stage.py"), "browser", "--root", str(tmp_path),
         "--apps", "browser-attached"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=20,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert json.loads(result.stdout) == ["browser-attached"]
    assert (tmp_path / "usr/share/claw/extensions/claw-agent-browser/manifest.json").is_file()
    assert (tmp_path / "usr/lib/cos/claw-browser-host").is_file()
    assert (tmp_path / "usr/lib/cos/apps/browser-attached/native_host.py").is_file()
    assert not (tmp_path / "usr/lib/cos/apps/search").exists()
    assert not (tmp_path / "usr/lib/cos/apps/web").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()


def test_normal_staging_propagates_asset_validation_before_payload_writes(tmp_path, monkeypatch):
    source, package = stage.load_package("browser")
    monkeypatch.setattr(stage, "load_package", lambda *args, **kwargs: (
        source, {**package, "installed_assets": None},
    ))
    with pytest.raises(ValueError, match="Installed assets"):
        stage.stage("browser", tmp_path)
    assert not (tmp_path / "usr").exists()


def test_normal_staging_never_overwrites_a_conflicting_installed_asset(tmp_path):
    launcher = tmp_path / "usr/lib/cos/claw-browser-host"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"unrelated existing file")
    with pytest.raises(ValueError, match="Conflicting staged installed asset"):
        stage.stage("browser", tmp_path, ["browser-attached"])
    assert launcher.read_bytes() == b"unrelated existing file"
    assert not (tmp_path / "usr/share/claw/extensions/claw-agent-browser").exists()
    assert not (tmp_path / "usr/lib/cos/apps").exists()


def test_terminal_stage_preserves_exec_without_process_services(tmp_path):
    assert "terminal" in stage.products()
    assert stage.stage("terminal", tmp_path) == ["exec", "cosmic-term"]
    app = tmp_path / "usr/lib/cos/apps/exec"
    source = ROOT / "products/terminal/apps/exec"
    for filename in ("app.json", "main.py", "server.py"):
        assert (app / filename).read_bytes() == (source / filename).read_bytes()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "var/lib/cos").exists()


@pytest.mark.parametrize(("product", "app_ids"), [
    ("containers", ["container-manager"]),
    ("backup-recovery", ["backup-center", "system-snapshot"]),
    ("store", ["pkg", "cosmic-store"]),
    ("diagnostics", ["hardware-center", "crash-doctor", "netdiag"]),
    ("storage", ["storage-manager"]),
    ("security", ["security-center", "firewall-manager", "usb-guard"]),
    ("maintenance", ["config-editor", "systemd"]),
    ("events-audit", ["event-center", "log"]),
    ("launcher", ["launcher", "cosmic-launcher"]),
    ("clipboard", ["clipboard-manager", "panel-clipboard"]),
    ("settings", ["accessibility-manager", "audio-manager", "bluetooth-manager", "camera-manager", "display-manager", "desktop-manager", "location-manager", "network-manager", "power-manager", "printer-manager", "user-manager", "cosmic-settings"]),
])
def test_broker_products_stage_without_os_services(tmp_path, product, app_ids):
    assert product in stage.products()
    assert stage.stage(product, tmp_path) == app_ids
    for app_id in app_ids:
        app = tmp_path / "usr/lib/cos/apps" / app_id
        source = ROOT / "products" / product / "apps" / app_id
        filenames = (("app.json",) if app_id in ("cosmic-launcher", "cosmic-store", "cosmic-settings") else
                     ("app.json", "main.sh") if app_id == "panel-clipboard" else
                     ("app.json", "main.py", "server.py"))
        for filename in filenames:
            assert (app / filename).read_bytes() == (source / filename).read_bytes()
        assert not (app / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/bin").exists()
    assert not (tmp_path / "var/lib").exists()


def test_mail_stage_contains_matching_app_and_ui_without_os_runtime(tmp_path):
    assert stage.stage("mail", tmp_path) == ["mail-ai", "email"]
    app = tmp_path / "usr/lib/cos/apps/mail-ai"
    assert (app / "server.py").is_file()
    assert (app / "native_host.py").is_file()
    assert not (app / "test_main.py").exists()
    email = tmp_path / "usr/lib/cos/apps/email"
    assert (email / "main.py").is_file()
    assert (email / "server.py").is_file()
    assert not (email / "test_main.py").exists()
    assert not (tmp_path / "usr/lib/cos/apps/_shared").exists()
    gateway = tmp_path / "usr/lib/cos/apps/gateway/email"
    assert not gateway.exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway-email").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "usr/lib/cos/claw-mail-ai-host").exists()
    manifest = json.loads((app / "app.json").read_text())
    xpi = tmp_path / "usr/lib/thunderbird/distribution/extensions/claw-mail-ai@claw.os.xpi"
    with zipfile.ZipFile(xpi) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == manifest["version"]
        assert "test_contract.py" not in archive.namelist()
    with pytest.raises(FileExistsError):
        stage.stage("mail", tmp_path)


def test_home_integration_stages_only_adapter_payload(tmp_path):
    assert stage.stage("home-integration", tmp_path) == ["gateway-homeassistant"]
    source = ROOT / "products/home-integration/apps/gateway/homeassistant"
    installed = tmp_path / "usr/lib/cos/apps/gateway/homeassistant"
    assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
    for filename in ("app.json", "main.py", "server.py"):
        assert (installed / filename).read_bytes() == (source / filename).read_bytes()
    assert not (tmp_path / "usr/lib/cos/apps/gateway-homeassistant").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "var/lib").exists()


def test_notification_delivery_stages_only_product_payload(tmp_path):
    assert stage.stage("notification-delivery", tmp_path) == ["gateway-ntfy", "gateway-pushover", "gateway-webhook"]
    for channel in ("ntfy", "pushover", "webhook"):
        source = ROOT / "products/notification-delivery/apps/gateway" / channel
        installed = tmp_path / "usr/lib/cos/apps/gateway" / channel
        assert {path.name for path in installed.iterdir()} == {"app.json", "main.py", "server.py"}
        for filename in ("app.json", "main.py", "server.py"):
            assert (installed / filename).read_bytes() == (source / filename).read_bytes()
        assert not (tmp_path / "usr/lib/cos/apps" / f"gateway-{channel}").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "var/lib").exists()


def test_messaging_channels_stage_nested_connector_without_shared_runtime_or_state(tmp_path):
    assert stage.stage("messaging-channels", tmp_path) == ["gateway-discord", "gateway-slack", "gateway-telegram", "gateway-whatsapp"]
    for channel in ("discord", "slack", "telegram", "whatsapp"):
        source = ROOT / "products/messaging-channels/apps/gateway" / channel
        installed = tmp_path / "usr/lib/cos/apps/gateway" / channel
        for filename in ("app.json", "main.py", "server.py"):
            assert (installed / filename).read_bytes() == (source / filename).read_bytes()
        assert not (installed / "test_main.py").exists()
        assert not (tmp_path / "usr/lib/cos/apps" / f"gateway-{channel}").exists()
    assert not (tmp_path / "usr/lib/cos/apps/gateway/_shared").exists()
    assert not (tmp_path / "usr/lib/cos/python").exists()
    assert not (tmp_path / "var/lib").exists()


@pytest.mark.parametrize("layout,app_id", [
    ("apps/gateway/email", "email"),
    ("apps/../outside", "outside"),
    ("apps", "mail"),
])
def test_stage_rejects_identity_or_layout_drift(tmp_path, monkeypatch, layout, app_id):
    source = tmp_path / "source"
    product = source / "products/mail"
    product.mkdir(parents=True)
    (product / "package.json").write_text(json.dumps({"apps": [layout]}))
    if layout == "apps/gateway/email":
        app = product / layout
        app.mkdir(parents=True)
        (app / "app.json").write_text(json.dumps({"id": app_id}))
    monkeypatch.setattr(stage, "ROOT", source)
    target = tmp_path / "stage"
    with pytest.raises(ValueError, match="layout"):
        stage.stage("mail", target)
    assert not target.exists()
