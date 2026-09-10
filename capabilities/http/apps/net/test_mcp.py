"""Exercise the staged HTTP client through public MCP and OS CONNECT protocols."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile

import pytest

from test_support import authenticated_mcp_params, load_local_module, mcp_process, stage_platform_python


ROOT = Path(__file__).resolve().parents[4]
URL = "http://example.test:8080/resource"
PAYLOAD = b"public HTTP fixture"


def _headers(stream):
    headers = {}
    for _ in range(100):
        line = stream.readline(8192)
        assert line and line.endswith(b"\r\n"), line
        if line == b"\r\n":
            return headers
        name, value = line.decode("latin-1").split(":", 1)
        headers[name.lower()] = value.strip()
    raise AssertionError("fixture header limit exceeded")


@contextmanager
def _http_broker():
    calls = {"connects": [], "requests": []}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            method, target, version = self.rfile.readline(1024).decode("ascii").strip().split()
            assert method == "CONNECT" and version == "HTTP/1.1"
            assert _headers(self.rfile)["host"] == target
            calls["connects"].append(target)
            if target.startswith("blocked."):
                self.wfile.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            method, path, version = self.rfile.readline(8192).decode("ascii").strip().split()
            assert version == "HTTP/1.1"
            headers = _headers(self.rfile)
            data = self.rfile.read(int(headers.get("content-length", "0")))
            calls["requests"].append({
                "target": target, "method": method, "path": path,
                "headers": headers, "data": data,
            })
            routes = {
                "/resource": ("200 OK", PAYLOAD, ""),
                "/redirect": (
                    "302 Found", b"",
                    "Location: http://other.example.test:8081/resource\r\n",
                ),
                "/exact": ("200 OK", b"x" * 32, ""),
                "/over": ("200 OK", b"x" * 33, ""),
            }
            status, body, extra = routes[path]
            response = (
                f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n{extra}\r\n"
            ).encode("ascii")
            self.wfile.write(response + body)

    class Broker(socketserver.UnixStreamServer):
        def handle_error(self, request, client_address):
            raise

    with tempfile.TemporaryDirectory(prefix="cos-net-") as temporary:
        socket_path = str(Path(temporary) / "egress.sock")
        with Broker(socket_path, Handler) as server, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(server.serve_forever, poll_interval=0.01)
            try:
                yield socket_path, calls
            finally:
                server.shutdown()
                future.result(timeout=10)


@pytest.fixture(params=["original", "private-module", "declared-entrypoint"])
def client(tmp_path, request):
    stage = load_local_module(ROOT / "tools/stage.py", "claw_http_test_stage")
    stage.stage("http", tmp_path / "stage", kind="capability")
    apps = tmp_path / "stage/usr/lib/cos/apps"
    python = stage.stage_shared(tmp_path / "stage")
    stage_platform_python(python)
    app = apps / "net"
    manifest = json.loads((app / "app.json").read_text())
    if request.param == "private-module":
        (app / "main.py").rename(app / "http_client.py")
        entry = app / manifest["mcp"]["entry"]
        entry.write_text(entry.read_text().replace("from main import ", "from http_client import "))
    elif request.param == "declared-entrypoint":
        (app / manifest["mcp"]["entry"]).rename(app / "http_mcp.py")
        manifest["mcp"]["entry"] = "http_mcp.py"
        (app / "app.json").write_text(json.dumps(manifest))
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    log = tmp_path / "policy.jsonl"
    policy = tmp_path / "cos"
    policy.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "assert sys.argv[1:4] == ['--wire=1', '__policy', 'check'], sys.argv\n"
        "args = sys.argv[4:]\n"
        "with open(os.environ['TEST_POLICY_LOG'], 'a') as output:\n"
        "    output.write(json.dumps(args) + '\\n')\n"
        "allow = (len(args) == 3 and (\n"
        "    (args[:2] == ['net.dial', '--host'] and args[2] in {\n"
        "        'example.test:8080', 'other.example.test:8081', 'blocked.example.test:8080'})\n"
        "    or (args[:2] == ['fs.write', '--path']\n"
        "        and Path(args[2]).is_relative_to(os.environ['TEST_WRITE_ROOT']))))\n"
        "print(json.dumps({'ok':True, 'wire_version':1,\n"
        "    'data':{'decision':'allow' if allow else 'deny'}}))\n"
    )
    policy.chmod(0o755)
    with _http_broker() as (socket_path, transport), mcp_process(app, env={
        "PATH": os.defpath, "PYTHONPATH": str(python),
        "COS_DATA_DIR": str(tmp_path / "data"), "COS_EGRESS_SOCKET": socket_path,
        "COS_NET_DOWNLOAD_MAX": "32", "CLAW_COS_BIN": str(policy),
        "TEST_POLICY_LOG": str(log), "TEST_WRITE_ROOT": str(downloads),
    }) as rpc:
        def call(command, arguments):
            return rpc("tools/call", authenticated_mcp_params({
                "name": f"net.{command}", "arguments": arguments,
            }))

        yield rpc, call, transport, log, downloads


def test_staged_net_catalog_and_fetch_use_public_sdk_and_os_egress(client):
    rpc, call, transport, log, _ = client
    tools = {tool["name"]: tool for tool in rpc("tools/list", {})["tools"]}
    assert set(tools) == {"net.fetch", "net.download"}
    assert tools["net.fetch"]["inputSchema"]["properties"]["header"]["type"] == "array"
    assert tools["net.download"]["inputSchema"]["required"] == ["url", "output"]
    result = call("fetch", {
        "url": URL, "method": "POST", "data": '{"value":"fixture"}',
        "header": ["X-Fixture: first", "Accept: application/json"], "timeout": 5,
    })
    assert not result.get("isError"), result
    assert result["structuredContent"] == {
        "url": URL, "status": 200,
        "headers": {"Content-Type": "text/plain", "Content-Length": str(len(PAYLOAD)),
                    "Connection": "close"},
        "body": PAYLOAD.decode(),
    }
    sent = transport["requests"][0]
    assert sent["method"] == "POST" and sent["path"] == "/resource"
    assert sent["data"] == b'{"value":"fixture"}'
    assert sent["headers"]["x-fixture"] == "first"
    assert sent["headers"]["accept"] == "application/json"
    assert sent["headers"]["content-type"] == "application/json"
    assert transport["connects"] == ["example.test:8080"]
    assert ["net.dial", "--host", "example.test:8080"] in [
        json.loads(line) for line in log.read_text().splitlines()
    ]


def test_public_mcp_unicode_url_uses_the_canonical_host_and_exact_port(client):
    _, call, transport, log, _ = client
    result = call("fetch", {"url": "http://exam\u00adple.test:8080/resource"})
    assert not result.get("isError"), result
    assert result["structuredContent"]["body"] == PAYLOAD.decode()
    assert transport["connects"] == ["example.test:8080"]
    assert transport["requests"][0]["headers"]["host"] == "example.test:8080"
    assert {tuple(json.loads(line)) for line in log.read_text().splitlines()} == {
        ("net.dial", "--host", "example.test:8080"),
    }


def test_public_mcp_redirect_authorizes_each_destination(client):
    _, call, transport, log, _ = client
    result = call("fetch", {
        "url": URL.replace("/resource", "/redirect"),
        "header": ["Authorization: fixture-only"],
    })
    assert not result.get("isError"), result
    assert result["structuredContent"]["body"] == PAYLOAD.decode()
    assert transport["connects"] == ["example.test:8080", "other.example.test:8081"]
    assert "authorization" not in transport["requests"][1]["headers"]
    scopes = {tuple(json.loads(line)) for line in log.read_text().splitlines()}
    assert scopes == {
        ("net.dial", "--host", "example.test:8080"),
        ("net.dial", "--host", "other.example.test:8081"),
    }


def test_public_mcp_invalid_args_and_policy_denial_never_reach_transport(client):
    _, call, transport, log, downloads = client
    for arguments in (
        {"url": "file:///not-an-http-resource"},
        {"url": URL, "timeout": 0},
        {"url": URL, "header": ["X-Fixture: line\nInjected: header"]},
    ):
        assert call("fetch", arguments)["isError"] is True
    assert not log.exists()
    assert call("fetch", {"url": "http://denied.example.test:8080/resource"})["isError"] is True
    assert call("download", {"url": URL, "output": str(downloads.parent / "outside")})["isError"] is True
    assert transport["connects"] == []
    assert not (downloads.parent / "outside").exists()


def test_public_mcp_download_limits_and_atomic_output_are_preserved(client):
    _, call, transport, log, downloads = client
    output = downloads / "result.bin"
    output.write_bytes(b"keep existing output")
    inode = output.stat().st_ino
    result = call("download", {"url": URL.replace("/resource", "/over"), "output": str(output)})
    assert result["isError"] is True
    assert "download exceeds size limit" in result["content"][0]["text"]
    assert output.read_bytes() == b"keep existing output"
    assert output.stat().st_ino == inode
    result = call("download", {"url": URL.replace("/resource", "/exact"), "output": str(output)})
    assert result["structuredContent"] == {
        "url": URL.replace("/resource", "/exact"), "path": str(output), "bytes": 32,
    }
    assert output.read_bytes() == b"x" * 32
    assert output.stat().st_mode & 0o777 == 0o600
    assert {path.name for path in downloads.iterdir()} == {"result.bin"}
    assert transport["connects"] == ["example.test:8080", "example.test:8080"]
    assert ["fs.write", "--path", str(output)] in [
        json.loads(line) for line in log.read_text().splitlines()
    ]


def test_public_mcp_broker_refusal_is_not_a_direct_network_fallback(client):
    _, call, transport, _, _ = client
    result = call("fetch", {"url": "http://blocked.example.test:8080/resource"})
    assert result["isError"] is True
    assert "egress broker refused" in result["content"][0]["text"]
    assert transport["connects"] == ["blocked.example.test:8080"]
    assert transport["requests"] == []
