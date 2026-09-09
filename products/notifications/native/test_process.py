"""Installed native Notifications MCP with an isolated, fixture-only wire broker."""

import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from stage import stage  # noqa: E402

NOTIFICATION_ID = "notif-" + "a" * 32


def line(process, timeout=15):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout), "Notifications fixture timed out"
        value = process.stdout.readline()
        assert value, process.stderr.read()
        return value


def receive(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError("short broker frame")
        data.extend(chunk)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/native-target/debug/cosmic-notifications")
    parser.add_argument("--source", type=Path, default=ROOT / "build/notifications-native")
    parser.add_argument("--cos-binary", type=Path)
    options = parser.parse_args()
    fixture = ROOT / "build/nf-process"
    fixture.mkdir()
    processes = []
    listener = None
    thread = None
    stopped, delay, arrived, completed = (threading.Event() for _ in range(4))
    permitted, available = threading.Event(), threading.Event()
    permitted.set()
    available.set()
    calls, failures = [], []
    try:
        installed = fixture / "installed"
        stage("notifications", installed, ["cosmic-notifications"])
        native = options.source.resolve()
        installation = subprocess.run([
            "just", "--justfile", str(native / "justfile"), f"rootdir={installed}",
            f"bin-src={options.binary.resolve()}", "prefix=/usr", "install",
        ], capture_output=True, text=True)
        assert installation.returncode == 0, installation.stderr
        binary = installed / "usr/bin/cosmic-notifications"
        manifest = installed / "usr/lib/cos/apps/cosmic-notifications/app.json"
        assert binary.stat().st_mode & 0o777 == 0o755
        assert binary.read_bytes() == options.binary.read_bytes()
        assert manifest.read_bytes() == (ROOT / "products/notifications/apps/cosmic-notifications/app.json").read_bytes()
        assert {str(path.relative_to(installed)) for path in installed.rglob("*") if path.is_file()} == {
            "usr/bin/cosmic-notifications", "usr/lib/cos/apps/cosmic-notifications/app.json",
        }

        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(fixture / "broker.sock"))
        listener.settimeout(0.2)
        listener.listen(8)

        def serve():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                try:
                    with connection:
                        connection.settimeout(10)
                        header = receive(connection, 10)
                        assert header[:6] == b"CBK1\x01\x00"
                        size, = struct.unpack(">I", header[6:])
                        assert size <= 20_000
                        message = json.loads(receive(connection, size))
                        assert set(message) == {"v", "id", "command", "params"}
                        assert message["v"] == 2
                        assert message["command"] == "system.notification.control"
                        params = message["params"]
                        assert set(params) == {"session", "deadline_unix_ms", "request"}
                        assert params["session"] == "worker-session"
                        intent = params["request"]
                        assert intent["action"] in {"post", "close"}
                        expected = (
                            {"action", "summary", "body", "app_name", "icon", "expire_ms", "transient"}
                            if intent["action"] == "post" else {"action", "id"}
                        )
                        assert set(intent) - {"dedupe_key"} == expected
                        calls.append(params)
                        arrived.set()
                        while delay.is_set() and not stopped.is_set() and params["deadline_unix_ms"] > time.time() * 1000:
                            time.sleep(0.01)
                        error = None
                        if not permitted.is_set():
                            error = {"code": "not_authorized", "message": "ui.notify is not granted"}
                        elif not available.is_set():
                            error = {"code": "unavailable", "message": "Notification Service is unavailable"}
                        elif params["deadline_unix_ms"] <= time.time() * 1000:
                            error = {"code": "execution", "message": "notification deadline expired"}
                        elif intent["action"] == "close" and intent["id"] != NOTIFICATION_ID:
                            error = {"code": "execution", "message": "notification not found"}
                        body = {"v": 2, "id": message["id"], "ok": error is None}
                        if error:
                            body["error"] = error
                        else:
                            body["result"] = (
                                {"id": NOTIFICATION_ID} if intent["action"] == "post" else
                                {"ok": True, "id": NOTIFICATION_ID, "state": "dismissed"}
                            )
                        data = json.dumps(body).encode()
                        connection.sendall(b"CBK1\x02\x00" + struct.pack(">I", len(data)) + data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Cancellation closes only this private fixture call.
                except Exception as error:
                    failures.append(error)
                    stopped.set()
                finally:
                    completed.set()

        thread = threading.Thread(target=serve)
        thread.start()
        cli = fixture / "cos"
        cli.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,socket,struct,sys,pathlib\n"
            "assert 'DBUS_SESSION_BUS_ADDRESS' not in os.environ\n"
            "assert 'CLAW_COS_BIN' not in os.environ\n"
            "assert not pathlib.Path('/run/user').exists()\n"
            "assert not pathlib.Path('/run/cos/session-bus').exists()\n"
            "args=sys.argv[1:];assert args[:5]==['--wire=1','__notifications','request','--request-stdin','--deadline']\n"
            "assert len(args)==6\n"
            "intent=json.load(sys.stdin)\n"
            "request={'v':2,'id':'fixture-call','command':'system.notification.control',"
            "'params':{'session':os.environ['COS_SESSION'],'deadline_unix_ms':int(args[5]),'request':intent}}\n"
            "def read(s,n):\n"
            " data=b''\n"
            " while len(data)<n:\n"
            "  chunk=s.recv(n-len(data));assert chunk;data+=chunk\n"
            " return data\n"
            "with socket.socket(socket.AF_UNIX) as s:\n"
            " s.connect('/run/cos/clawd.sock');data=json.dumps(request).encode()\n"
            " s.sendall(b'CBK1\\x01\\x00'+struct.pack('>I',len(data))+data)\n"
            " header=read(s,10);assert header[:6]==b'CBK1\\x02\\x00'\n"
            " result=json.loads(read(s,struct.unpack('>I',header[6:])[0]))\n"
            "out={'wire_version':1,'ok':result['ok']}\n"
            "if result['ok']:out['data']=result['result']\n"
            "else:out.update(code='KERNEL_UNAVAILABLE' if result['error']['code']=='unavailable' else 'PERMISSION_DENIED',"
            "error=result['error']['message'])\n"
            "print(json.dumps(out));sys.exit(0 if result['ok'] else 1)\n"
        )
        cli.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-all", "--clearenv",
            "--ro-bind", "/usr/bin", "/usr/bin", "--ro-bind", "/usr/lib", "/usr/lib",
            "--ro-bind", "/usr/share", "/usr/share", "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64", "--dir", "/usr/local/bin",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/run", "--tmpfs", "/work",
            "--dir", "/run/cos",
            "--ro-bind", str(options.cos_binary.resolve() if options.cos_binary else cli), "/usr/local/bin/cos",
            "--ro-bind", str(binary), "/work/cosmic-notifications",
            "--ro-bind", str(manifest), "/work/app.json",
            "--ro-bind", str(fixture / "broker.sock"), "/run/cos/clawd.sock", "--chdir", "/work",
        ]
        for name, value in {
            "COS_MCP_SERVER": "1", "COS_APP_ID": "cosmic-notifications",
            "COS_APP_MANIFEST": "/work/app.json", "COS_SESSION": "worker-session",
            "COS_WORKER_SANDBOX": "1", "COS_RUNTIME_DIR": "/run/cos",
            "COS_DATA_DIR": "/work/data", "HOME": "/work",
            "XDG_CONFIG_HOME": "/work/config", "XDG_CACHE_HOME": "/work/cache",
            "TMPDIR": "/work", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }.items():
            command += ["--setenv", name, value]
        process = subprocess.Popen([*command, "--", "/work/cosmic-notifications"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        processes.append(process)
        counter = 0

        def send(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            return counter

        def response(identifier):
            value = json.loads(line(process))
            assert value["id"] == identifier, value
            return value

        def request(method, params):
            return response(send(method, params))

        def params(name, arguments, **context):
            return {"name": name, "arguments": arguments, "_meta": {"claw-os.dev/call-context": {
                "wire_version": 1, "call_id": f"fixture-{counter}", "trace_id": "fixture",
                "session_id": "forged-session", "task_id": "forged-task",
                "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 23456}, **context,
            }}}

        def call(name, arguments, **context):
            return request("tools/call", params(name, arguments, **context))

        def success(value):
            assert "error" not in value and not value["result"].get("isError"), value
            return json.loads(value["result"]["content"][0]["text"])

        def denied(value):
            assert "error" in value or value["result"].get("isError"), value

        request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "notification-fixture", "version": "1"}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        tools = request("tools/list", {})["result"]["tools"]
        assert {tool["name"] for tool in tools} == {"notify.post", "notify.close"}
        wrong = json.loads(manifest.read_text())
        wrong["id"] = "wrong-identity"
        (fixture / "wrong.json").write_text(json.dumps(wrong))
        refused = subprocess.run([
            *command, "--ro-bind", str(fixture / "wrong.json"), "/work/wrong.json",
            "--setenv", "COS_APP_MANIFEST", "/work/wrong.json", "--", "/work/cosmic-notifications",
        ], input="", capture_output=True, text=True, timeout=10)
        assert refused.returncode != 0 and "cosmic-notifications" in refused.stderr
        denied(request("tools/call", {"name": "notify.post", "arguments": {"summary": "No context"}}))
        for arguments in [
            {}, {"summary": ""}, {"summary": " "}, {"summary": "界" * 241},
            {"summary": "Title", "body": "x" * 4001},
            *({"summary": "Title", "icon": icon} for icon in ("/etc/shadow", "file:///private", "../icon")),
            *({"summary": "Title", "expire_ms": value} for value in (-2, 2147483648, True, "-1")),
            {"summary": "Title", "transient": "true"}, {"summary": "Title", "app_name": "line\nbreak"},
            {"summary": "Title", "dedupe_key": ""}, {"summary": "Title", "owner_uid": 0},
            {"summary": "Title", "source": "agent"}, {"summary": "Title", "actions": ["default"]},
        ]:
            denied(call("notify.post", arguments))
        for identifier in [42, "42", "notif-x", "../private"]:
            denied(call("notify.close", {"id": identifier}))
        denied(call("notify.post", {"summary": "Expired"}, deadline_unix_ms=1))
        assert calls == [], calls
        assert success(call("notify.post", {"summary": "Default"})) == {"id": NOTIFICATION_ID}
        assert calls[-1]["request"] == {
            "action": "post", "summary": "Default", "body": "", "app_name": "Claw OS Agent",
            "icon": "com.clawos.Notifications", "expire_ms": -1, "transient": False,
        }
        full = {"summary": "Title", "body": "<b>plain text stays off argv</b>", "app_name": "Label only",
                "icon": "notification-symbolic", "expire_ms": 0, "transient": True, "dedupe_key": "same"}
        assert success(call("notify.post", full)) == {"id": NOTIFICATION_ID}
        assert calls[-1]["request"] == {"action": "post", **full}
        for expiry in [1, 2147483647]:
            success(call("notify.post", {"summary": "Expiry", "app_name": "", "icon": "", "expire_ms": expiry}))
            assert calls[-1]["request"]["expire_ms"] == expiry
            assert calls[-1]["request"]["app_name"] == "Claw OS Agent"
        assert success(call("notify.close", {"id": NOTIFICATION_ID})) == {
            "ok": True, "id": NOTIFICATION_ID, "state": "dismissed",
        }
        denied(call("notify.close", {"id": "notif-" + "b" * 32}))
        permitted.clear()
        denied(call("notify.post", {"summary": "Denied"}))
        permitted.set()
        available.clear()
        refused = call("notify.post", {"summary": "Unavailable"})
        denied(refused)
        assert "unavailable" in json.dumps(refused).lower()
        available.set()
        delay.set()
        arrived.clear()
        completed.clear()
        cancelled = send("tools/call", params("notify.post", {"summary": "Cancelled"}))
        assert arrived.wait(5)
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                       "params": {"requestId": cancelled, "reason": "fixture cancellation"}}) + "\n")
        process.stdin.flush()
        request("tools/list", {})
        delay.clear()
        assert completed.wait(5)
        delay.set()
        completed.clear()
        denied(call("notify.post", {"summary": "Deadline"}, deadline_unix_ms=int(time.time() * 1000) + 400))
        delay.clear()
        assert completed.wait(5)
        assert all(value["session"] == "worker-session" for value in calls)
        assert not failures, failures
        print("Notifications installed payload, isolated MCP, exact intent/fields, errors and cancellation passed")
    finally:
        delay.clear()
        stopped.set()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if thread:
            thread.join(timeout=10)
        if listener:
            listener.close()
        shutil.rmtree(fixture)


if __name__ == "__main__":
    main()
