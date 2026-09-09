"""Installed Player, isolated authenticated MCP and a private broker/MPRIS fixture."""

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

ACTIONS = {"play", "pause", "stop", "next", "previous", "toggle", "status"}


def line(process, timeout=15):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout), "Media Player fixture timed out"
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
    parser.add_argument("--binary", type=Path, default=ROOT / "build/native-target/debug/cosmic-player")
    parser.add_argument("--source", type=Path, default=ROOT / "build/media-player-native")
    parser.add_argument("--fixture-binary", type=Path, default=ROOT / "build/native-target/debug/examples/media-player-mpris-fixture")
    parser.add_argument("--cos-binary", type=Path)
    options = parser.parse_args()
    fixture = ROOT / "build/player-process-fixture"
    fixture.mkdir()
    processes = []
    stopped = threading.Event()
    listener = None
    thread = None
    failures = []
    calls = []
    permissions = {"observe", "control"}
    delay = threading.Event()
    arrived = threading.Event()
    completed = threading.Event()
    try:
        installed = fixture / "installed"
        stage("media-player", installed)
        native = options.source.resolve()
        fixture_binary = options.fixture_binary.resolve()
        installation = subprocess.run([
            "just", "--justfile", str(native / "justfile"), f"rootdir={installed}",
            f"bin-src={options.binary.resolve()}", "prefix=/usr", "install",
        ], capture_output=True, text=True)
        assert installation.returncode == 0, installation.stderr
        binary = installed / "usr/bin/cosmic-player"
        assert binary.stat().st_mode & 0o777 == 0o755
        for source, target in [
            ("target/xdgen/com.clawos.Player.desktop", "applications/com.clawos.Player.desktop"),
            ("target/xdgen/com.clawos.Player.metainfo.xml", "metainfo/com.clawos.Player.metainfo.xml"),
            ("res/com.clawos.Player.thumbnailer", "thumbnailers/com.clawos.Player.thumbnailer"),
            ("res/icons/hicolor/scalable/apps/com.clawos.Player.svg", "icons/hicolor/scalable/apps/com.clawos.Player.svg"),
        ]:
            assert (installed / "usr/share" / target).read_bytes() == (native / source).read_bytes()
        desktop = (installed / "usr/share/applications/com.clawos.Player.desktop").read_text()
        assert "Exec=cosmic-player" in desktop and "Name[fr]=" in desktop
        address = f"unix:path={fixture}/bus"
        bus = subprocess.Popen([
            "dbus-daemon", "--session", "--nofork", "--nopidfile", "--nosyslog",
            f"--address={address}", "--print-address=1",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(bus)
        assert line(bus).startswith(address)
        env = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": address, "TMPDIR": str(fixture),
               "HOME": str(fixture), "DISPLAY": "", "WAYLAND_DISPLAY": ""}
        other = subprocess.Popen([str(fixture_binary), "--other"], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(other)
        assert line(other).strip() == "other-ready"
        ui = subprocess.Popen([str(fixture_binary)], env=env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(ui)
        own_name = line(ui).strip()
        assert own_name == f"org.mpris.MediaPlayer2.com.clawos.Player.pid{ui.pid}"

        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(fixture / "broker.sock"))
        listener.settimeout(0.2)

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
                        assert size < 8192
                        request = json.loads(receive(connection, size))
                        assert set(request) == {"v", "id", "command", "params"}
                        assert request["v"] == 2
                        assert request["command"] == "system.media-player.control"
                        params = request["params"]
                        assert set(params) == {"session", "action", "deadline_unix_ms"}
                        assert params["session"] == "worker-session"
                        action = params["action"]
                        assert action in ACTIONS
                        calls.append(params)
                        arrived.set()
                        while delay.is_set() and not stopped.is_set() and params["deadline_unix_ms"] > time.time() * 1000:
                            time.sleep(0.01)
                        permission = "observe" if action == "status" else "control"
                        error = None
                        result = None
                        if permission not in permissions:
                            error = f"{permission} permission denied"
                        elif params["deadline_unix_ms"] <= time.time() * 1000:
                            error = "Media Player deadline expired"
                        elif ui.poll() is not None:
                            error = "no native Media Player is running"
                        else:
                            response = subprocess.run(
                                [str(fixture_binary), "--client", own_name, action], env=env,
                                capture_output=True, text=True, timeout=8,
                            )
                            if response.returncode:
                                error = response.stderr
                            else:
                                result = json.loads(response.stdout)
                        body = {"v": 2, "id": request["id"], "ok": error is None}
                        if error:
                            body["error"] = {"code": "not_authorized", "message": error}
                        else:
                            body["result"] = result
                        data = json.dumps(body).encode()
                        connection.sendall(b"CBK1\x02\x00" + struct.pack(">I", len(data)) + data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # A cancelled client is permitted to close its private call.
                except Exception as error:
                    failures.append(error)
                    stopped.set()
                finally:
                    completed.set()

        listener.listen(8)
        thread = threading.Thread(target=serve)
        thread.start()
        cli = fixture / "cos"
        cli.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,socket,struct,sys,pathlib\n"
            "assert 'CLAW_COS_BIN' not in os.environ\n"
            "assert 'DBUS_SESSION_BUS_ADDRESS' not in os.environ\n"
            "assert not pathlib.Path('/run/cos/session-bus').exists()\n"
            "assert not pathlib.Path('/run/user').exists()\n"
            "args=sys.argv[1:];assert args[:2]==['--wire=1','__media-player']\n"
            "assert len(args)==5 and args[3]=='--deadline'\n"
            "request={'v':2,'id':'fixture-call','command':'system.media-player.control',"
            "'params':{'session':os.environ['COS_SESSION'],'action':args[2],'deadline_unix_ms':int(args[4])}}\n"
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
            "else:out.update(code='PERMISSION_DENIED',error=result['error']['message'])\n"
            "print(json.dumps(out));sys.exit(0 if result['ok'] else 1)\n"
        )
        cli.chmod(0o755)
        command = [
            "bwrap", "--die-with-parent", "--unshare-all", "--clearenv",
            "--ro-bind", "/usr/bin", "/usr/bin", "--ro-bind", "/usr/lib", "/usr/lib",
            "--ro-bind", "/usr/share", "/usr/share", "--dir", "/usr/local/bin",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/run", "--tmpfs", "/work", "--dir", "/run/cos",
            "--ro-bind", str(options.cos_binary.resolve() if options.cos_binary else cli), "/usr/local/bin/cos",
            "--ro-bind", str(binary), "/work/cosmic-player",
            "--ro-bind", str(installed / "usr/lib/cos/apps/cosmic-player/app.json"), "/work/app.json",
            "--ro-bind", str(fixture / "broker.sock"), "/run/cos/clawd.sock",
            "--chdir", "/work",
        ]
        for name, value in {
            "COS_MCP_SERVER": "1", "COS_APP_ID": "cosmic-player",
            "COS_APP_MANIFEST": "/work/app.json", "COS_SESSION": "worker-session",
            "COS_WORKER_SANDBOX": "1", "COS_RUNTIME_DIR": "/run/cos",
            "COS_DATA_DIR": "/work/data", "HOME": "/work",
            "XDG_CONFIG_HOME": "/work/config", "XDG_CACHE_HOME": "/work/cache",
            "TMPDIR": "/work", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }.items():
            command += ["--setenv", name, value]
        process = subprocess.Popen([*command, "--", "/work/cosmic-player"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        processes.append(process)
        counter = 0

        def send(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter,
                                           "method": method, "params": params}) + "\n")
            process.stdin.flush()
            return counter

        def response(identifier):
            value = json.loads(line(process))
            assert value["id"] == identifier, value
            return value

        def request(method, params):
            return response(send(method, params))

        def params(action, arguments=None, **context):
            return {
                "name": f"player.{action}", "arguments": arguments or {},
                "_meta": {"claw-os.dev/call-context": {
                    "wire_version": 1, "call_id": f"fixture-{counter}", "trace_id": "fixture",
                    "session_id": "metadata-does-not-select-broker-session", "task_id": "fixture-task",
                    "caller": {"kind": "system-agent", "id": "fixture", "owner_uid": 1000}, **context,
                }},
            }

        def call(action, arguments=None, **context):
            return request("tools/call", params(action, arguments, **context))

        def success(value):
            assert "error" not in value and not value["result"].get("isError"), value
            return json.loads(value["result"]["content"][0]["text"])

        def denied(value):
            assert "error" in value or value["result"].get("isError"), value

        request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                              "clientInfo": {"name": "media-fixture", "version": "1"}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        tools = request("tools/list", {})["result"]["tools"]
        assert {tool["name"] for tool in tools} == {f"player.{name}" for name in ACTIONS}
        wrong = json.loads((installed / "usr/lib/cos/apps/cosmic-player/app.json").read_text())
        wrong["id"] = "wrong-identity"
        (fixture / "wrong.json").write_text(json.dumps(wrong))
        wrong_identity = subprocess.run([
            *command, "--ro-bind", str(fixture / "wrong.json"), "/work/wrong.json",
            "--setenv", "COS_APP_MANIFEST", "/work/wrong.json", "--", "/work/cosmic-player",
        ], input="", capture_output=True, text=True, timeout=10)
        assert wrong_identity.returncode != 0 and "cosmic-player" in wrong_identity.stderr
        denied(request("tools/call", {"name": "player.status", "arguments": {}}))
        for action, arguments, context in [
            ("status", {"player": "org.mpris.MediaPlayer2.OtherFixture"}, {}),
            ("play", {"url": "file:///private"}, {}),
            ("open", {}, {}), ("status", {}, {"deadline_unix_ms": 1}),
        ]:
            denied(call(action, arguments, **context))
        assert calls == []
        status = success(call("status"))
        assert status == {
            "status": "Paused", "title": "Synthetic visible track 0", "artist": ["Synthetic artist"],
            "album": "Synthetic album", "length_micros": 30_000_000, "url": "file:///synthetic/track0.ogg",
        }
        for action, expected, title in [
            ("play", "Playing", "Synthetic visible track 0"),
            ("pause", "Paused", "Synthetic visible track 0"),
            ("toggle", "Playing", "Synthetic visible track 0"),
            ("next", "Playing", "Synthetic visible track 1"),
            ("previous", "Playing", "Synthetic visible track 0"),
            ("stop", "Stopped", "Synthetic visible track 0"),
        ]:
            assert success(call(action)) == {"ok": True}
            live = success(call("status"))
            assert live["status"] == expected and live["title"] == title, live
        ui.stdin.write("ui-title:Changed in native UI\n")
        ui.stdin.flush()
        assert line(ui).strip() == "updated"
        assert success(call("status"))["title"] == "Changed in native UI"
        for permission, action in [("observe", "status"), ("control", "play")]:
            permissions.remove(permission)
            denied(call(action))
            permissions.add(permission)
        delay.set()
        arrived.clear()
        completed.clear()
        cancelled = send("tools/call", params("status"))
        assert arrived.wait(5)
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                       "params": {"requestId": cancelled, "reason": "fixture cancellation"}}) + "\n")
        process.stdin.flush()
        # MCP cancellation deliberately suppresses its response. A subsequent
        # request must be served promptly, not blocked by the cancelled CLI.
        request("tools/list", {})
        delay.clear()
        assert completed.wait(5)
        delay.set()
        completed.clear()
        timed_out = send("tools/call", params("status", deadline_unix_ms=int(time.time() * 1000) + 100))
        denied(response(timed_out))
        delay.clear()
        assert completed.wait(5)
        ui.terminate()
        ui.wait(timeout=5)
        denied(call("play"))
        assert other.poll() is None, other.stderr.read()
        assert all(value["session"] == "worker-session" for value in calls)
        assert not failures, failures
        print("Player installed resources, seven live MCP tools, separate grants, cancellation and no-bus sandbox passed")
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
