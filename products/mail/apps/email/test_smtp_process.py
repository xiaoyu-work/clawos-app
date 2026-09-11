"""Public Email MCP calls use their declared endpoint and real TLS transport."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile

import pytest

from test_support import authenticated_mcp_params, mcp_process


APP = Path(__file__).resolve().parent
HOST = "mail.example.com"


@pytest.fixture
def certificate(tmp_path):
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", f"/CN={HOST}", "-addext", f"subjectAltName=DNS:{HOST}",
    ], check=True, capture_output=True, timeout=15)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return cert, context


def smtp_peer(listener, endpoint, context, implicit_tls):
    connection, _ = listener.accept()
    connection.settimeout(15)
    reader = None
    message = []
    commands = []
    try:
        head = bytearray()
        while not head.endswith(b"\r\n\r\n"):
            byte = connection.recv(1)
            assert byte and len(head) < 8192, "invalid private CONNECT frame"
            head.extend(byte)
        assert head.split(b"\r\n", 1)[0] == f"CONNECT {endpoint} HTTP/1.1".encode()
        connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        if implicit_tls:
            connection = context.wrap_socket(connection, server_side=True)
        connection.sendall(b"220 private SMTP fixture\r\n")
        reader = connection.makefile("rb")
        for _ in range(20):
            line = reader.readline(8192)
            assert line.endswith(b"\r\n"), "SMTP command did not finish"
            command = line.split(b" ", 1)[0].strip().upper()
            commands.append(command)
            if command == b"EHLO":
                feature = b"AUTH PLAIN" if isinstance(connection, ssl.SSLSocket) else b"STARTTLS"
                connection.sendall(b"250-private fixture\r\n250 " + feature + b"\r\n")
            elif command == b"STARTTLS":
                assert not implicit_tls and not isinstance(connection, ssl.SSLSocket)
                connection.sendall(b"220 upgrade now\r\n")
                reader.close()
                connection = context.wrap_socket(connection, server_side=True)
                reader = connection.makefile("rb")
            elif command == b"AUTH":
                assert isinstance(connection, ssl.SSLSocket), "credentials preceded TLS"
                assert base64.b64decode(line.split()[2]) == b"\0fixture-user\0fixture-password"
                connection.sendall(b"235 authenticated\r\n")
            elif command in (b"MAIL", b"RCPT"):
                assert isinstance(connection, ssl.SSLSocket)
                connection.sendall(b"250 accepted\r\n")
            elif command == b"DATA":
                connection.sendall(b"354 message follows\r\n")
                total = 0
                while True:
                    body = reader.readline(8192)
                    assert body.endswith(b"\r\n")
                    if body == b".\r\n":
                        break
                    total += len(body)
                    assert total <= 65536
                    message.append(body)
                connection.sendall(b"250 delivered\r\n")
            elif command == b"QUIT":
                connection.sendall(b"221 goodbye\r\n")
                return b"".join(message), commands
            else:
                raise AssertionError(f"unexpected SMTP command: {command!r}")
        raise AssertionError("SMTP fixture exceeded its command bound")
    finally:
        if reader is not None:
            reader.close()
        connection.close()


def policy_fixture(tmp_path, endpoint):
    path = tmp_path / "cos"
    log = tmp_path / "policy.jsonl"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"log = {str(log)!r}\n"
        "args = sys.argv[1:]\n"
        "if args[:3] != ['--wire=1', '__policy', 'check']:\n"
        "    print('unsupported private policy fixture route', file=sys.stderr)\n"
        "    raise SystemExit(99)\n"
        "with open(log, 'a') as out:\n"
        "    out.write(json.dumps(args) + '\\n')\n"
        f"allowed = args[3:] in [['secret.read', '--name', 'default/SMTP_PASSWORD'], ['net.dial', '--host', {endpoint!r}]]\n"
        "print(json.dumps({'ok': True, 'wire_version': 1, 'data': {\n"
        "    'decision': 'allow' if allowed else 'deny',\n"
        "    'summary': 'private endpoint scope decision'}}))\n"
    )
    path.chmod(0o755)
    return path, log


@pytest.mark.parametrize("port", [587, 465])
def test_declared_mcp_endpoint_matches_policy_and_tls_tunnel(tmp_path, certificate, port):
    cert, context = certificate
    endpoint = f"{HOST}:{port}"
    policy, policy_log = policy_fixture(tmp_path, endpoint)
    with tempfile.TemporaryDirectory(prefix="smtp-egress-", dir="/tmp") as directory:
        broker = str(Path(directory) / "egress.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(broker)
            listener.listen(1)
            listener.settimeout(15)
            env = {
                "HOME": str(tmp_path), "PATH": os.environ["PATH"],
                "PYTHONPATH": os.environ["PYTHONPATH"],
                "CLAW_COS_BIN": str(policy), "COS_EGRESS_SOCKET": broker,
                "SMTP_PORT": "2525", "SMTP_USER": "fixture-user",
                "SMTP_PASSWORD": "fixture-password", "SMTP_FROM": "sender@example.com",
                "SSL_CERT_FILE": str(cert),
            }
            with ThreadPoolExecutor(max_workers=1) as executor:
                peer = executor.submit(smtp_peer, listener, endpoint, context, port == 465)
                with mcp_process(APP, env=env) as request:
                    def send(host):
                        return request("tools/call", authenticated_mcp_params({
                            "name": "email.send",
                            "arguments": {
                                "provider": "smtp", "host": host,
                                "to": "recipient@example.com", "subject": "Private fixture",
                                "body": "Only the declared SMTP endpoint.",
                            },
                        }))

                    invalid = send(HOST)
                    assert invalid["isError"] is True
                    assert "invalid SMTP --host" in invalid["structuredContent"]["error"]
                    assert not policy_log.exists()

                    denied = send(f"{HOST}:25")
                    assert denied["isError"] is True
                    assert denied["structuredContent"]["denial"]["decision"] == "deny"

                    sent = send(endpoint)
                    assert sent.get("isError", False) is False, sent
                    assert sent["structuredContent"]["sent"] is True
                message, commands = peer.result(timeout=20)
            assert b"To: recipient@example.com\r\n" in message
            assert b"Only the declared SMTP endpoint." in message
            assert (b"STARTTLS" in commands) is (port == 587)
            assert b"AUTH" in commands and b"DATA" in commands
            checks = [json.loads(line) for line in policy_log.read_text().splitlines()]
            net = [args[3:] for args in checks if args[3] == "net.dial"]
            assert net == [["net.dial", "--host", f"{HOST}:25"], ["net.dial", "--host", endpoint]]
