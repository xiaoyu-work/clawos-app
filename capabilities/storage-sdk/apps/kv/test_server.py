"""Tests for the kv MCP service."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import threading
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module, mcp_process


APP_DIR = Path(__file__).parent


def _load_server(monkeypatch: pytest.MonkeyPatch, data_dir: Path):
    monkeypatch.setenv("COS_APP_MANIFEST", str(APP_DIR / "app.json"))
    monkeypatch.setenv("COS_APP_ID", "kv")
    monkeypatch.setenv("COS_DATA_DIR", str(data_dir))
    return load_local_module(
        APP_DIR / "server.py",
        "claw_test_kv_server",
        clear_modules=("_shared",),
    )


def test_list_defaults_to_all_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("zebra", "last")
    server.kv_set("alpha", "first")

    assert server.kv_list() == {
        "pattern": "*",
        "keys": ["alpha", "zebra"],
    }


def test_values_persist_across_cache_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("greeting", "hello")
    server._cache = None

    assert server.kv_get("greeting") == "hello"
    assert json.loads((tmp_path / "kv.json").read_text(encoding="utf-8")) == {
        "greeting": "hello",
    }


@pytest.mark.parametrize(
    "contents",
    [
        "{not json",
        '["not", "an", "object"]',
        '{"answer": 42}',
    ],
)
def test_invalid_persisted_store_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contents: str,
) -> None:
    (tmp_path / "kv.json").write_text(contents, encoding="utf-8")
    server = _load_server(monkeypatch, tmp_path)

    with pytest.raises((json.JSONDecodeError, ValueError)):
        server.kv_dump()


def _environment(data_dir):
    return {
        "PATH": os.defpath,
        "PYTHONPATH": os.environ["PYTHONPATH"],
        "COS_DATA_DIR": str(data_dir),
    }


def _call(request, command, arguments=None):
    return request("tools/call", authenticated_mcp_params({
        "name": f"kv.{command}", "arguments": arguments or {},
    }))


def _object(result):
    assert not result.get("isError"), result
    value = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == value
    return value


def _text(result):
    assert not result.get("isError"), result
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    return result["content"][0]["text"]


def test_existing_json_is_not_rewritten_by_reads(monkeypatch, tmp_path):
    original = b'{\n  "empty": "",\n  "scope/key:*": "kept"\n}\n'
    store = tmp_path / "kv.json"
    store.write_bytes(original)
    identity = store.stat().st_ino
    server = _load_server(monkeypatch, tmp_path)

    assert server.kv_get("missing") == ""
    assert server.kv_get("empty") == ""
    assert server.kv_list("scope/*") == {"pattern": "scope/*", "keys": ["scope/key:*"]}
    assert server.kv_dump() == {
        "count": 2, "data": {"empty": "", "scope/key:*": "kept"},
    }
    assert store.read_bytes() == original
    assert store.stat().st_ino == identity


def test_cached_reads_follow_external_replacement_and_removal(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("key", "old")
    replacement = tmp_path / "replacement"
    replacement.write_text('{"key":"new","external":"kept"}')
    replacement.replace(tmp_path / "kv.json")

    assert server.kv_get("key") == "new"
    assert server.kv_dump()["data"] == {"key": "new", "external": "kept"}
    (tmp_path / "kv.json").unlink()
    assert server.kv_get("key") == ""
    assert server.kv_dump() == {"count": 0, "data": {}}
    assert server.kv_del("key") == {"key": "key", "deleted": False}
    assert not (tmp_path / "kv.json").exists()


def test_cache_detects_same_size_edits_with_restored_mtime(monkeypatch, tmp_path):
    store = tmp_path / "kv.json"
    store.write_text('{"key":"old"}')
    server = _load_server(monkeypatch, tmp_path)
    assert server.kv_get("key") == "old"
    before = store.stat()
    store.write_text('{"key":"new"}')
    os.utime(store, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert server.kv_get("key") == "new"


def test_unchanged_snapshots_reuse_the_parsed_cache(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("key", "old")
    with mock.patch.object(server.json, "loads", wraps=server.json.loads) as decode:
        assert server.kv_get("key") == server.kv_get("key") == "old"
        decode.assert_not_called()
        (tmp_path / "kv.json").write_text('{"key":"new"}')
        assert server.kv_get("key") == "new"
        decode.assert_called_once()


@pytest.mark.parametrize("contents", [
    b"", b"\xff", b'\xef\xbb\xbf{"key":"value"}', '{"key":"value"}'.encode("utf-16"),
])
def test_store_keeps_its_strict_utf8_json_contract(monkeypatch, tmp_path, contents):
    store = tmp_path / "kv.json"
    store.write_bytes(contents)
    server = _load_server(monkeypatch, tmp_path)
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
        server.kv_dump()
    assert store.read_bytes() == contents


def test_live_writers_preserve_each_others_committed_keys(monkeypatch, tmp_path):
    first = _load_server(monkeypatch, tmp_path)
    second = _load_server(monkeypatch, tmp_path)
    assert first.kv_dump() == second.kv_dump() == {"count": 0, "data": {}}
    first.kv_set("left", "one")
    second.kv_set("right", "two")

    assert json.loads((tmp_path / "kv.json").read_text()) == {
        "left": "one", "right": "two",
    }
    assert first.kv_get("right") == "two"
    assert first.kv_del("left") == {"key": "left", "deleted": True}
    assert second.kv_dump() == {"count": 1, "data": {"right": "two"}}


@pytest.mark.parametrize("command", ["set", "del"])
def test_failed_commit_does_not_publish_uncommitted_cache(monkeypatch, tmp_path, command):
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("kept", "old")
    original = (tmp_path / "kv.json").read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError("synthetic atomic-write failure")

    monkeypatch.setattr(server, "atomic_write_bytes", fail_write)
    with pytest.raises(OSError, match="synthetic atomic-write failure"):
        if command == "set":
            server.kv_set("kept", "uncommitted")
        else:
            server.kv_del("kept")
    assert server.kv_get("kept") == "old"
    assert (tmp_path / "kv.json").read_bytes() == original


@pytest.mark.parametrize("contents", ['{not json', '[]', '{"kept":42}'])
@pytest.mark.parametrize("command", ["get", "dump", "set", "del"])
def test_corrupt_external_state_never_falls_back_to_warm_cache(
    monkeypatch, tmp_path, contents, command,
):
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("kept", "old")
    store = tmp_path / "kv.json"
    store.write_text(contents)
    calls = {
        "get": lambda: server.kv_get("kept"),
        "dump": server.kv_dump,
        "set": lambda: server.kv_set("new", "value"),
        "del": lambda: server.kv_del("kept"),
    }
    with pytest.raises((json.JSONDecodeError, ValueError)):
        calls[command]()
    assert store.read_text() == contents


def test_private_atomic_replacement_preserves_the_complete_old_inode(monkeypatch, tmp_path):
    store = tmp_path / "kv.json"
    original = b'{"seed":"existing"}'
    store.write_bytes(original)
    server = _load_server(monkeypatch, tmp_path)
    previous_umask = os.umask(0)
    try:
        with store.open("rb") as old:
            identity = os.fstat(old.fileno()).st_ino
            assert server.kv_set("next", "value") == {"key": "next", "value": "value"}
            assert old.read() == original
            assert store.stat().st_ino != identity
    finally:
        os.umask(previous_umask)
    assert store.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "kv.json.lock").stat().st_mode & 0o777 == 0o600
    assert json.loads(store.read_text()) == {"seed": "existing", "next": "value"}
    assert {path.name for path in tmp_path.iterdir()} == {"kv.json", "kv.json.lock"}


def test_writers_reload_after_acquiring_the_exclusive_lock(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    server.kv_set("seed", "existing")
    started = threading.Event()

    def write():
        started.set()
        return server.kv_set("local", "value")

    with (tmp_path / "kv.json.lock").open("a+") as lock, ThreadPoolExecutor(max_workers=1) as pool:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            future = pool.submit(write)
            assert started.wait(5)
            with pytest.raises(FutureTimeout):
                future.result(timeout=0.1)
            replacement = tmp_path / "replacement"
            replacement.write_text('{"seed":"existing","external":"committed"}')
            replacement.replace(tmp_path / "kv.json")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
        assert future.result(timeout=5) == {"key": "local", "value": "value"}
    assert json.loads((tmp_path / "kv.json").read_text()) == {
        "seed": "existing", "external": "committed", "local": "value",
    }


def test_concurrent_threads_preserve_independent_updates_and_deletes(monkeypatch, tmp_path):
    server = _load_server(monkeypatch, tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: server.kv_set(f"key-{index}", str(index)), range(64)))
        deleted = list(pool.map(lambda index: server.kv_del(f"key-{index}"), range(0, 64, 2)))
    assert all(result["deleted"] for result in deleted)
    expected = {f"key-{index}": str(index) for index in range(1, 64, 2)}
    assert server.kv_dump() == {"count": 32, "data": expected}
    assert _load_server(monkeypatch, tmp_path).kv_dump()["data"] == expected


def test_public_mcp_catalog_defaults_and_output_shapes(tmp_path):
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        tools = request("tools/list", {})["tools"]
        assert [tool["name"] for tool in tools] == [
            "kv.get", "kv.set", "kv.del", "kv.list", "kv.dump",
        ]
        for tool, names, required in zip(
            tools,
            [["key"], ["key", "value"], ["key"], ["pattern"], []],
            [["key"], ["key", "value"], ["key"], [], []],
            strict=True,
        ):
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert schema["additionalProperties"] is False
            assert list(schema["properties"]) == names
            assert schema.get("required", []) == required
            assert all(argument["type"] == "string" for argument in schema["properties"].values())
        assert tools[3]["inputSchema"]["properties"]["pattern"]["default"] == "*"
        assert _text(_call(request, "get", {"key": "missing"})) == ""
        assert _object(_call(request, "del", {"key": "missing"})) == {
            "key": "missing", "deleted": False,
        }
        assert not list(tmp_path.iterdir())
        for key, value in [("zebra", "last"), ("alpha", "first"), ("empty", "")]:
            assert _object(_call(request, "set", {"key": key, "value": value})) == {
                "key": key, "value": value,
            }
        assert _object(_call(request, "list")) == {
            "pattern": "*", "keys": ["alpha", "empty", "zebra"],
        }
        assert _object(_call(request, "list", {"pattern": "[az]*"})) == {
            "pattern": "[az]*", "keys": ["alpha", "zebra"],
        }
        assert _text(_call(request, "get", {"key": "empty"})) == ""
        assert _object(_call(request, "dump")) == {
            "count": 3, "data": {"zebra": "last", "alpha": "first", "empty": ""},
        }
        assert _object(_call(request, "del", {"key": "alpha"})) == {
            "key": "alpha", "deleted": True,
        }


def test_manifest_keeps_key_grants_distinct_and_requires_full_store_read():
    manifest = json.loads((APP_DIR / "app.json").read_text())
    assert manifest["id"] == "kv"
    assert not manifest.get("operations")
    tools = manifest["mcp"]["tools"]
    for tool, verb in zip(tools[:3], ["data.kv.read", "data.kv.write", "data.kv.delete"], strict=True):
        assert len(tool["needs"]) == 1
        assert tool["needs"][0]["verb"] == verb
        assert tool["needs"][0]["scope"] == {"kind": "from-arg", "arg": "key"}
    for tool in tools[3:]:
        assert len(tool["needs"]) == 1
        assert tool["needs"][0]["verb"] == "data.kv.read"
        assert tool["needs"][0]["scope"] == {"kind": "fixed", "scope": {"kind": "wild"}}


def test_object_declaration_reuses_the_existing_exact_key_mcp_command():
    manifest = json.loads((APP_DIR / "app.json").read_text())
    resolver = manifest["objects"]["entry"]["resolve"]
    assert resolver == {"operation": "get", "id_arg": "key"}
    assert "operations" not in manifest
    assert not (APP_DIR / "main.py").exists()
    tool = next(
        tool for tool in manifest["mcp"]["tools"]
        if tool["name"] == f"{manifest['id']}.{resolver['operation']}"
    )
    assert tool["args"] == [{"name": "key", "kind": "name", "required": True}]
    assert tool["needs"][0]["verb"] == "data.kv.read"
    assert tool["needs"][0]["scope"] == {"kind": "from-arg", "arg": "key"}
    assert tool["effects"][0]["recovery"] == "not_applicable"
    for name in ("kv.set", "kv.del"):
        mutation = next(tool for tool in manifest["mcp"]["tools"] if tool["name"] == name)
        assert mutation["effects"][0]["target_arg"] == "key"
        assert mutation["effects"][0]["recovery"] == "unknown"


@pytest.mark.parametrize("key", ["--schema", "001", "space /?id=key&revision=版本"])
def test_object_identity_remains_literal_data_through_public_mcp(tmp_path, key):
    from claw_os_sdk.objects import format_reference, parse_reference

    reference = format_reference({
        "app_id": "kv", "object_type": "entry", "object_id": key,
    })
    identity = parse_reference(reference)["object_id"]
    assert identity == key
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        assert _object(_call(request, "set", {"key": identity, "value": "literal"})) == {
            "key": key, "value": "literal",
        }
        assert _text(_call(request, "get", {"key": identity})) == "literal"
        assert _object(_call(request, "del", {"key": identity})) == {
            "key": key, "deleted": True,
        }


def test_object_resolution_preserves_missing_and_empty_get_results(tmp_path):
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        assert _text(_call(request, "get", {"key": "missing"})) == ""
        assert not list(tmp_path.iterdir())
        _object(_call(request, "set", {"key": "empty", "value": ""}))
        assert _text(_call(request, "get", {"key": "empty"})) == ""
        assert _text(_call(request, "get", {"key": "missing"})) == ""
        assert _object(_call(request, "dump")) == {"count": 1, "data": {"empty": ""}}


@pytest.mark.parametrize(("command", "arguments"), [
    ("get", {}),
    ("get", {"key": 42}),
    ("set", {"key": "key"}),
    ("set", {"key": "key", "value": {"not": "text"}}),
    ("set", {"key": "key", "value": "value", "session_id": "forged"}),
    ("del", {"key": None}),
    ("list", {"pattern": []}),
    ("list", {"stdin": True}),
    ("dump", {"key": "extra"}),
])
def test_public_mcp_rejects_invalid_arguments_before_storage(tmp_path, command, arguments):
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        result = _call(request, command, arguments)
        assert result["isError"] is True
        assert not list(tmp_path.iterdir())


def test_public_mcp_sees_other_writers_and_survives_restart(tmp_path):
    environment = _environment(tmp_path)
    with mcp_process(APP_DIR, env=environment) as first, mcp_process(APP_DIR, env=environment) as second:
        assert _object(_call(first, "dump")) == _object(_call(second, "dump")) == {
            "count": 0, "data": {},
        }
        _object(_call(first, "set", {"key": "left", "value": "one"}))
        assert _text(_call(second, "get", {"key": "left"})) == "one"
        _object(_call(second, "set", {"key": "right", "value": "two"}))
        assert _object(_call(first, "del", {"key": "left"}))["deleted"] is True
    with mcp_process(APP_DIR, env=environment) as restarted:
        assert _object(_call(restarted, "dump")) == {"count": 1, "data": {"right": "two"}}


def test_public_mcp_round_trips_utf8_keys_and_values(tmp_path):
    key, value = "\u043a\u043b\u044e\u0447", "\u4f60\u597d\n\u00e9"
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        assert _object(_call(request, "set", {"key": key, "value": value})) == {
            "key": key, "value": value,
        }
        assert _text(_call(request, "get", {"key": key})) == value
    contents = (tmp_path / "kv.json").read_bytes()
    assert key.encode("utf-8") in contents
    assert json.loads(contents.decode("utf-8")) == {key: value}


def test_public_mcp_concurrent_processes_preserve_all_keys(tmp_path):
    with ExitStack() as stack:
        peers = [
            stack.enter_context(mcp_process(APP_DIR, env=_environment(tmp_path)))
            for _ in range(4)
        ]
        for peer in peers:
            assert _object(_call(peer, "dump")) == {"count": 0, "data": {}}

        def write(item):
            index, peer = item
            for number in range(10):
                _object(_call(peer, "set", {
                    "key": f"{index}-{number}", "value": str(number),
                }))

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, enumerate(peers)))
        expected = {f"{index}-{number}": str(number) for index in range(4) for number in range(10)}
        for peer in peers:
            assert _object(_call(peer, "dump")) == {"count": 40, "data": expected}
    assert json.loads((tmp_path / "kv.json").read_text()) == expected


def test_public_mcp_surfaces_corruption_without_repairing_it(tmp_path):
    with mcp_process(APP_DIR, env=_environment(tmp_path)) as request:
        _object(_call(request, "set", {"key": "kept", "value": "old"}))
        store = tmp_path / "kv.json"
        store.write_bytes(b'{"kept":false}')
        for command, arguments in [("dump", {}), ("set", {"key": "new", "value": "value"})]:
            result = _call(request, command, arguments)
            assert result["isError"] is True
            assert "kv store must contain only string keys and values" in result["content"][0]["text"]
            assert store.read_bytes() == b'{"kept":false}'
