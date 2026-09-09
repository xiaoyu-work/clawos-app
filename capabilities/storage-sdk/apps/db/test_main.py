import ast
from concurrent.futures import ThreadPoolExecutor
import json
import os
import pathlib
import sqlite3
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from test_support import authenticated_mcp_params, load_local_module, mcp_process


APP_DIR = pathlib.Path(__file__).parent
MANIFEST_PATH = APP_DIR / "app.json"
SERVER_PATH = APP_DIR / "server.py"
TOOL_NAMES = [
    "db.query",
    "db.exec",
    "db.tables",
    "db.schema",
    "db.databases",
]

main = load_local_module(
    APP_DIR / "main.py",
    "claw_test_db_main",
    clear_modules=("_shared",),
)


def _server_bindings() -> dict[str, ast.FunctionDef]:
    bindings: dict[str, ast.FunctionDef] = {}
    for node in ast.parse(SERVER_PATH.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr == "tool"
                and len(decorator.args) == 1
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                bindings[decorator.args[0].value] = node
    return bindings


def _argument_contract(function: ast.FunctionDef) -> tuple[list[str], list[str]]:
    return (
        [argument.arg for argument in function.args.args],
        [
            ast.unparse(argument.annotation)
            for argument in function.args.args
            if argument.annotation is not None
        ],
    )


def _from_database(verb: str) -> list[dict[str, object]]:
    return [
        {
            "verb": verb,
            "scope": {"kind": "from-arg", "arg": "database"},
            "why": {
                "en": {
                    "data.db.read": "Read rows from the database you asked to query.",
                    "data.db.write": "Modify the database you asked to execute SQL on.",
                }[verb]
            },
        }
    ]


def test_manifest_and_handlers_are_mcp_only_and_aligned() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "operations" not in manifest

    tools = manifest["mcp"]["tools"]
    assert [tool["name"] for tool in tools] == TOOL_NAMES
    tool_map = {tool["name"]: tool for tool in tools}
    database_arg = {
        "name": "database",
        "kind": "name",
        "required": True,
        "binding": "positional",
    }
    sql_arg = {
        "name": "sql",
        "kind": "text",
        "required": True,
        "binding": "positional",
    }
    assert tool_map["db.query"]["args"] == [database_arg, sql_arg]
    assert tool_map["db.exec"]["args"] == [database_arg, sql_arg]
    assert tool_map["db.tables"]["args"] == [database_arg]
    assert tool_map["db.schema"]["args"] == [
        database_arg,
        {
            "name": "table",
            "kind": "text",
            "required": True,
            "binding": "positional",
        },
    ]
    assert tool_map["db.databases"].get("args", []) == []
    assert tool_map["db.query"]["needs"] == _from_database("data.db.read")
    assert tool_map["db.exec"]["needs"] == _from_database("data.db.write")
    assert tool_map["db.databases"]["needs"][0]["scope"] == {"kind": "wild"}

    server_source = SERVER_PATH.read_text(encoding="utf-8")
    assert "from claw_os_sdk.mcp import App" in server_source
    assert "serve_manifest_operations" not in server_source
    bindings = _server_bindings()
    assert list(bindings) == TOOL_NAMES
    assert _argument_contract(bindings["db.query"]) == (
        ["database", "sql"],
        ["str", "str"],
    )
    assert _argument_contract(bindings["db.exec"]) == (
        ["database", "sql"],
        ["str", "str"],
    )
    assert _argument_contract(bindings["db.tables"]) == (["database"], ["str"])
    assert _argument_contract(bindings["db.schema"]) == (
        ["database", "table"],
        ["str", "str"],
    )
    assert _argument_contract(bindings["db.databases"]) == ([], [])

    main_tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run"
        for node in main_tree.body
    )


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_DIR", str(tmp_path / "db"))
    with mock.patch.object(main.policy, "require") as require:
        yield require


def _create_database(name: str = "testdb", rows: int = 0) -> pathlib.Path:
    path = pathlib.Path(main._db_path(name))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)"
        )
        connection.executemany(
            "INSERT INTO items (id, val) VALUES (?, ?)",
            ((index, f"row_{index}") for index in range(rows)),
        )
    return path


@pytest.mark.parametrize("row_count", [10, main.MAX_ROWS])
def test_query_returns_rows_without_truncation(row_count, isolated_database):
    _create_database(rows=row_count)

    result = main.query("testdb", "SELECT * FROM items ORDER BY id")

    assert result["count"] == row_count
    assert len(result["rows"]) == row_count
    assert "truncated" not in result
    assert "total_rows" not in result
    isolated_database.assert_called_once_with("data.db.read", name="testdb")


def test_query_limits_returned_rows_and_counts_the_remainder(isolated_database):
    total = main.MAX_ROWS + 100
    _create_database(rows=total)

    result = main.query("testdb", "SELECT * FROM items ORDER BY id")

    assert result["count"] == main.MAX_ROWS
    assert len(result["rows"]) == main.MAX_ROWS
    assert result["truncated"] is True
    assert result["total_rows"] == total
    isolated_database.assert_called_once_with("data.db.read", name="testdb")


def test_query_is_read_only(isolated_database):
    path = _create_database(rows=2)

    with pytest.raises(RuntimeError, match="database query failed"):
        main.query("testdb", "DELETE FROM items")

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    isolated_database.assert_called_once_with("data.db.read", name="testdb")


def test_query_cannot_attach_another_database(isolated_database):
    _create_database("testdb")
    other_path = _create_database("other")

    with pytest.raises(RuntimeError, match="database query failed"):
        main.query("testdb", f"ATTACH DATABASE '{other_path}' AS other")

    isolated_database.assert_called_once_with("data.db.read", name="testdb")


def test_query_does_not_create_a_missing_database(isolated_database):
    path = pathlib.Path(main._db_path("missing"))

    with pytest.raises(RuntimeError, match="database query failed"):
        main.query("missing", "SELECT 1")

    assert not path.exists()
    isolated_database.assert_called_once_with("data.db.read", name="missing")


def test_execute_and_schema_tools_use_exact_scopes(isolated_database):
    created = main.execute(
        "inventory",
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)",
    )
    inserted = main.execute(
        "inventory",
        "INSERT INTO products (name) VALUES ('camera')",
    )
    table_result = main.tables("inventory")
    schema_result = main.schema("inventory", "products")
    database_result = main.databases()

    assert created["database"] == "inventory"
    assert inserted["rows_affected"] == 1
    assert table_result == {"database": "inventory", "tables": ["products"]}
    assert schema_result["database"] == "inventory"
    assert schema_result["table"] == "products"
    assert schema_result["schema"].startswith("CREATE TABLE products")
    assert database_result["databases"][0]["name"] == "inventory"
    assert database_result["databases"][0]["tables"] == 1
    assert isolated_database.call_args_list == [
        mock.call("data.db.write", name="inventory"),
        mock.call("data.db.write", name="inventory"),
        mock.call("data.db.read", name="inventory"),
        mock.call("data.db.read", name="inventory"),
        mock.call("data.db.read", wild=True),
    ]


def test_execute_cannot_attach_another_database(isolated_database):
    _create_database("testdb")
    other_path = _create_database("other")

    with pytest.raises(RuntimeError, match="database execution failed"):
        main.execute("testdb", f"ATTACH DATABASE '{other_path}' AS other")

    isolated_database.assert_called_once_with("data.db.write", name="testdb")


def test_missing_table_is_an_error(isolated_database):
    _create_database()

    with pytest.raises(ValueError, match="table not found: missing"):
        main.schema("testdb", "missing")

    isolated_database.assert_called_once_with("data.db.read", name="testdb")


def test_corrupt_database_is_not_reported_as_empty(isolated_database):
    path = pathlib.Path(main._db_path("corrupt"))
    path.write_bytes(b"not a sqlite database")

    with pytest.raises(RuntimeError, match="database listing failed for corrupt"):
        main.databases()

    isolated_database.assert_called_once_with("data.db.read", wild=True)


@pytest.mark.parametrize(
    "database",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "/etc/passwd",
        "foo/bar",
        "foo\\bar",
        ".hidden",
        "..parent",
        ".",
        "foo\x00bar",
        "name\n",
        "",
    ],
)
def test_invalid_database_names_are_rejected_before_policy(
    database,
    isolated_database,
):
    with pytest.raises(main._InvalidName):
        main.query(database, "SELECT 1")

    isolated_database.assert_not_called()


@pytest.mark.parametrize("sql", ["", "   ", None, 7])
def test_invalid_sql_is_rejected_before_policy(sql, isolated_database):
    with pytest.raises(ValueError, match="sql must be a non-empty string"):
        main.query("testdb", sql)

    isolated_database.assert_not_called()


def test_valid_database_name_resolves_under_database_directory():
    path = pathlib.Path(main._db_path("safe_name-1.test"))

    assert path.parent == pathlib.Path(main.DB_DIR).resolve()


@pytest.fixture
def sdk_app(tmp_path):
    log = tmp_path / "policy.jsonl"
    decision = tmp_path / "decision.json"
    decision.write_text('{"decision":"allow"}')
    policy = tmp_path / "cos"
    policy.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "assert sys.argv[1:4] == ['--wire=1', '__policy', 'check']\n"
        f"with open({str(log)!r}, 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[4:]) + '\\n')\n"
        f"decision = json.loads(pathlib.Path({str(decision)!r}).read_text())\n"
        "print(json.dumps({'ok': True, 'wire_version': 1, 'data': decision}))\n"
    )
    policy.chmod(0o755)
    with mcp_process(APP_DIR, env={
        **os.environ, "COS_DATA_DIR": str(tmp_path), "CLAW_COS_BIN": str(policy),
    }) as request:
        yield SimpleNamespace(request=request, log=log, decision=decision)


def _policy_calls(app):
    if not app.log.exists():
        return []
    return [json.loads(line) for line in app.log.read_text().splitlines()]


def _call(app, command, arguments):
    return app.request(
        "tools/call",
        authenticated_mcp_params({"name": f"db.{command}", "arguments": arguments}),
    )


def test_sdk_catalog_preserves_all_five_manifest_schemas(sdk_app):
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["id"] == "db"
    assert manifest["mcp"]["access"] == {"system_agent": True}
    catalog = sdk_app.request("tools/list", {})["tools"]
    assert [tool["name"] for tool in catalog] == TOOL_NAMES
    for declared, tool in zip(manifest["mcp"]["tools"], catalog, strict=True):
        args = declared.get("args", [])
        expected = {
            "type": "object",
            "properties": {arg["name"]: {"type": "string"} for arg in args},
            "additionalProperties": False,
        }
        if args:
            expected["required"] = [arg["name"] for arg in args]
        assert tool["inputSchema"] == expected
    assert _policy_calls(sdk_app) == []
    assert not pathlib.Path(main.DB_DIR).exists()


def test_sdk_dispatches_crud_schema_and_enumeration_with_separate_scopes(
    sdk_app,
):
    create = "CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT)"
    assert _call(sdk_app, "exec", {"database": "inventory", "sql": create})[
        "structuredContent"
    ] == {"database": "inventory", "statement": create, "rows_affected": -1}
    for sql in (
        "INSERT INTO items VALUES (1, 'original')",
        "UPDATE items SET value = 'updated' WHERE id = 1",
    ):
        assert _call(sdk_app, "exec", {"database": "inventory", "sql": sql})[
            "structuredContent"
        ] == {"database": "inventory", "statement": sql, "rows_affected": 1}
    assert _call(sdk_app, "query", {
        "database": "inventory", "sql": "SELECT * FROM items",
    })["structuredContent"] == {
        "database": "inventory", "columns": ["id", "value"],
        "rows": [[1, "updated"]], "count": 1,
    }
    assert _call(sdk_app, "tables", {"database": "inventory"})["structuredContent"] == {
        "database": "inventory", "tables": ["items"],
    }
    assert _call(sdk_app, "schema", {
        "database": "inventory", "table": "items",
    })["structuredContent"] == {
        "database": "inventory", "table": "items", "schema": create,
    }
    database = pathlib.Path(main.DB_DIR) / "inventory.db"
    assert _call(sdk_app, "databases", {})["structuredContent"] == {
        "databases": [{"name": "inventory", "size": database.stat().st_size, "tables": 1}],
    }
    assert _call(sdk_app, "exec", {
        "database": "inventory", "sql": "DELETE FROM items",
    })["structuredContent"]["rows_affected"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM items").fetchall() == []
    assert _policy_calls(sdk_app) == [
        *[["data.db.write", "--name", "inventory"]] * 3,
        *[["data.db.read", "--name", "inventory"]] * 3,
        ["data.db.read", "--wild"],
        ["data.db.write", "--name", "inventory"],
    ]


@pytest.mark.parametrize(("command", "arguments"), [
    ("query", {}),
    ("query", {"database": 42, "sql": "SELECT 1"}),
    ("query", {"database": "../outside", "sql": "SELECT 1"}),
    ("exec", {"database": "safe", "sql": " "}),
    ("exec", {"database": "safe", "sql": "SELECT 1", "session_id": "forged"}),
    ("tables", {"database": ""}),
    ("schema", {"database": "safe", "table": ""}),
    ("schema", {"database": "safe", "table": 4}),
    ("databases", {"database": "safe"}),
])
def test_sdk_rejects_invalid_arguments_before_policy_or_io(
    sdk_app, command, arguments,
):
    assert _call(sdk_app, command, arguments)["isError"] is True
    assert _policy_calls(sdk_app) == []
    assert not pathlib.Path(main.DB_DIR).exists()


@pytest.mark.parametrize(("command", "arguments", "scope"), [
    ("query", {"database": "safe", "sql": "SELECT 1"}, ["--name", "safe"]),
    ("exec", {"database": "safe", "sql": "CREATE TABLE items (id)"}, ["--name", "safe"]),
    ("tables", {"database": "safe"}, ["--name", "safe"]),
    ("schema", {"database": "safe", "table": "items"}, ["--name", "safe"]),
    ("databases", {}, ["--wild"]),
])
def test_sdk_policy_denial_is_explicit_before_database_creation(
    sdk_app, command, arguments, scope,
):
    sdk_app.decision.write_text('{"decision":"deny","summary":"fixture denied"}')
    result = _call(sdk_app, command, arguments)
    assert result["isError"] is True
    assert "PermissionDenied: fixture denied" in result["content"][0]["text"]
    verb = "data.db.write" if command == "exec" else "data.db.read"
    assert _policy_calls(sdk_app) == [[verb, *scope]]
    assert not pathlib.Path(main.DB_DIR).exists()


@pytest.mark.parametrize("row_count", [1000, 2101])
def test_sdk_preserves_exact_return_bound_and_full_total(sdk_app, row_count):
    assert main.MAX_ROWS == 1000
    _create_database(rows=row_count)
    result = _call(sdk_app, "query", {
        "database": "testdb", "sql": "SELECT * FROM items ORDER BY id",
    })["structuredContent"]
    assert result["rows"] == [[index, f"row_{index}"] for index in range(1000)]
    assert result["count"] == 1000
    if row_count > 1000:
        assert result["truncated"] is True
        assert result["total_rows"] == row_count
    else:
        assert "truncated" not in result
        assert "total_rows" not in result


@pytest.mark.parametrize("sql", [
    "INSERT INTO items VALUES (2, 'bad')",
    "UPDATE items SET val = 'bad'",
    "WITH target AS (SELECT 1) DELETE FROM items",
    "DROP TABLE items",
    "CREATE TEMP TABLE extra (value)",
    "PRAGMA query_only = OFF",
    "PRAGMA writable_schema = ON",
    "ATTACH DATABASE ':memory:' AS other",
])
def test_read_authorizer_refuses_sql_side_effects(sdk_app, sql):
    path = _create_database(rows=2)
    before = path.read_bytes()
    result = _call(sdk_app, "query", {"database": "testdb", "sql": sql})
    assert result["isError"] is True
    assert "database query failed" in result["content"][0]["text"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("command", ["query", "exec"])
@pytest.mark.parametrize("sql", [
    "ATTACH DATABASE '{outside}' AS other",
    "DETACH DATABASE main",
    "VACUUM INTO '{outside}'",
])
def test_sql_cannot_escape_the_authorized_database(sdk_app, tmp_path, command, sql):
    path = _create_database(rows=2)
    before = path.read_bytes()
    outside = tmp_path / "outside.db"
    result = _call(sdk_app, command, {
        "database": "testdb", "sql": sql.format(outside=outside),
    })
    assert result["isError"] is True
    assert path.read_bytes() == before
    assert not outside.exists()


@pytest.mark.parametrize(("handler", "args"), [
    (main.query, ("SELECT 1",)),
    (main.execute, ("CREATE TABLE extra (id)",)),
    (main.tables, ()),
    (main.schema, ("items",)),
])
@pytest.mark.parametrize("database", [None, 7, "a..b", "a\tb", "file:outside?mode=rw"])
def test_all_database_handlers_validate_names_before_policy(
    handler, args, database, isolated_database,
):
    with pytest.raises(main._InvalidName):
        handler(database, *args)
    isolated_database.assert_not_called()
    assert not pathlib.Path(main.DB_DIR).exists()


@pytest.mark.parametrize("command", ["query", "exec", "tables", "schema", "databases"])
def test_symlink_escape_is_refused_without_touching_the_target(sdk_app, tmp_path, command):
    outside = tmp_path / "outside.db"
    with sqlite3.connect(outside) as connection:
        connection.execute("CREATE TABLE items (id)")
    before = outside.read_bytes()
    directory = pathlib.Path(main.DB_DIR)
    directory.mkdir()
    (directory / "escape.db").symlink_to(outside)
    arguments = {} if command == "databases" else {"database": "escape"}
    if command in {"query", "exec"}:
        arguments["sql"] = "SELECT * FROM items"
    elif command == "schema":
        arguments["table"] = "items"
    result = _call(sdk_app, command, arguments)
    assert result["isError"] is True
    assert "escapes db dir" in result["content"][0]["text"]
    assert outside.read_bytes() == before


def test_schema_uses_a_bound_table_name(sdk_app):
    path = _create_database(rows=2)
    before = path.read_bytes()
    result = _call(sdk_app, "schema", {
        "database": "testdb", "table": "items'; DROP TABLE items; --",
    })
    assert result["isError"] is True
    assert "table not found" in result["content"][0]["text"]
    assert path.read_bytes() == before


@pytest.mark.parametrize(("command", "arguments"), [
    ("tables", {"database": "missing"}),
    ("schema", {"database": "missing", "table": "items"}),
])
def test_schema_reads_do_not_create_missing_databases(sdk_app, command, arguments):
    assert _call(sdk_app, command, arguments)["isError"] is True
    assert not (pathlib.Path(main.DB_DIR) / "missing.db").exists()


def test_failed_single_statement_rolls_back_and_releases_its_transaction():
    main.execute("atomic", "CREATE TABLE items (value TEXT UNIQUE)")
    with pytest.raises(RuntimeError, match="database execution failed"):
        main.execute("atomic", "INSERT OR FAIL INTO items VALUES ('same'), ('same')")
    assert main.query("atomic", "SELECT value FROM items")["rows"] == []
    with pytest.raises(RuntimeError, match="one statement"):
        main.execute("atomic", "INSERT INTO items VALUES ('bad'); DELETE FROM items")
    assert main.query("atomic", "SELECT value FROM items")["rows"] == []
    assert main.execute("atomic", "INSERT INTO items VALUES ('committed')")["rows_affected"] == 1
    assert main.query("atomic", "SELECT value FROM items")["rows"] == [["committed"]]


@pytest.mark.parametrize(("handler", "args", "error"), [
    (main.query, ("testdb", "SELECT * FROM items"), None),
    (main.query, ("testdb", "DELETE FROM items"), RuntimeError),
    (main.execute, ("testdb", "INSERT INTO items VALUES (1, 'stored')"), None),
    (main.execute, ("testdb", "INSERT INTO missing VALUES (1)"), RuntimeError),
    (main.tables, ("testdb",), None),
    (main.schema, ("testdb", "items"), None),
    (main.schema, ("testdb", "missing"), ValueError),
    (main.databases, (), None),
])
def test_connections_close_on_success_and_failure(monkeypatch, handler, args, error):
    _create_database()
    original_connect = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    if error:
        with pytest.raises(error):
            handler(*args)
    else:
        handler(*args)
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_concurrent_statements_commit_without_lost_updates():
    main.execute("counter", "CREATE TABLE counts (value INTEGER)")
    main.execute("counter", "INSERT INTO counts VALUES (0)")
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(
            lambda _: main.execute("counter", "UPDATE counts SET value = value + 1"),
            range(40),
        ))
    assert all(result["rows_affected"] == 1 for result in results)
    assert main.query("counter", "SELECT value FROM counts")["rows"] == [[40]]


def test_database_enumeration_filters_unsafe_filenames():
    _create_database("valid")
    for name in (".hidden.db", "a..b.db", "bad name.db", "unrelated.txt"):
        (pathlib.Path(main.DB_DIR) / name).write_bytes(b"not a database")
    assert [entry["name"] for entry in main.databases()["databases"]] == ["valid"]
